import requests
from utils import BufferedDailyLogger, LineBroadcaster, custom_line, LogLevel, UpdateInfo, get_bedrock_update_info
from datetime import datetime, timedelta
from pathlib import Path
from time import sleep, strftime, time
import threading
import shutil
import zipfile
import queue
import re

# Constants
RESTART_WARNING_MINUTES = 5
CRASH_DETECTION_WINDOW_MINUTES = 10
OFFLINE_BACKUP_PREFIX = "offline_world_backup"  # eg. "offline_world_backup_YYYY-MM-DD_HH-MM-SS"
ONLINE_BACKUP_PREFIX = "online_world_backup"    # eg. "online_world_backup_YYYY-MM-DD_HH-MM-SS"
PROTECTED_BACKUP_PREFIX = "protected"           # eg. "protected_offline_world_backup_YYYY-MM-DD_HH-MM-SS"
TEMPORARY_PREFIX = ".tmp"                       # eg. ".tmp_offline_world_backup_YYYY-MM-DD_HH-MM-SS"
BACKUP_TIMESTAMP_FORMAT = "%Y-%m-%d_%H-%M-%S"
SUCCESS_PATTERN = re.compile(r"Data saved. Files are now ready to be copied.", re.IGNORECASE)
FAIL_PATTERN = re.compile(r"A previous save has not been completed.", re.IGNORECASE)
DATE_PATTERN = re.compile(r'^\d{4}-\d{2}-\d{2}$')
PLAYERS_ONLINE_PATTERN = re.compile(r"There are (\d+)\/(\d+) players online:")
SAVE_QUERY_TIMEOUT_SECONDS = 10
DOWNLOAD_CONNECT_TIMEOUT_SECONDS = 10
DOWNLOAD_READ_TIMEOUT_SECONDS = 300
DOWNLOAD_CHUNK_SIZE = 1024 * 1024 # 1MB (in binary)
SERVER_BACKUP_PREFIX = "server_backup"
WORLDS_FOLDER_NAME = "worlds"


class ServerAutomation:
    def __init__(self, config, runner):
        self.config = config
        self.server_folder = config.server_folder
        self.world_name = config.world_name
        self.backup_folder = config.backup_folder
        self.backup_duration = config.backup_duration
        self.crash_limit = config.crash_limit
        self.restart_time = config.restart_time
        self.runner = runner
        # Subscribe to the stdout broadcaster and unexpected shutdown broadcaster
        self.runner.stdout_broadcaster.subscribe(self.handle_server_output)
        self.runner.unexpected_shutdown_broadcaster.subscribe(self.handle_unexpected_shutdown)
        # Create a broadcaster to broadcast outputs to the CLI
        self.automation_output_broadcaster = LineBroadcaster()
        # Create logger
        self.logger = BufferedDailyLogger(self.config.log_folder)
        # Create a list of crashes
        self.recent_crashes = []
        self.current_version = None


    def log_print(self, level: LogLevel, message: str):
        """
        Logs and broadcasts a line with the given log level.
        Args:
            level (LogLevel): The log level of the message.
            message (str): The message to log and broadcast.
        """
        lvl, ts, msg, line = custom_line(level, message)
        self.logger.log(line)
        self.automation_output_broadcaster.publish(lvl, ts, msg, line)


    def start(self):
        """Start the server automation tasks that require threads."""
        # Start the scheduled restart thread
        scheduled_restart_thread = threading.Thread(target=self._scheduled_restart, daemon=True)
        scheduled_restart_thread.start()
        # Prune old backups on startup
        self._prune_old_backups(Path(self.backup_folder))


    def handle_server_output(self, _level: LogLevel, _timestamp: str, message: str, line: str):
        """
        Process server output lines for automation triggers.
        Args:
            _level (LogLevel): The log level of the output line (unused).
            _timestamp (str): The timestamp of the output line (unused).
            message (str): The message of the output line.
            line (str): The output line from the server.
        """
        # Scrape the line for the version number to use in update checks
        if (message.startswith("Version:")):
            self.current_version = message.split("Version:")[1].strip()
        self.logger.log(line)


    def handle_unexpected_shutdown(self, level: LogLevel, timestamp: str, message: str, line: str):
        """
        Handle unexpected server shutdowns.
        Args:
            level (LogLevel): The log level of the output line.
            timestamp (str): The timestamp of the output line.
            message (str): The message of the output line.
            line (str): The output line from the server.
        """
        # Log the unexpected shutdown
        self.logger.log(line)
        self.automation_output_broadcaster.publish(level, timestamp, message, line)
        # Add the crash time to the list of crashes
        now = datetime.now()
        self.recent_crashes.append(now)
        crash_detection_window = now - timedelta(minutes=CRASH_DETECTION_WINDOW_MINUTES)
        # If any of the timestamps are older than the CRASH_DETECTION_WINDOW_MINUTES minutes, remove them
        self.recent_crashes = [t for t in self.recent_crashes if t >= crash_detection_window]
        # If the length is larger than the crash limit, send an error and do not restart the server
        if len(self.recent_crashes) >= self.crash_limit:
            self.log_print(LogLevel.CRITICAL, "Repeated unexpected shutdowns detected. Crash limit exceeded. Server restart attempts halted until manual intervention.")
        else:
            self.log_print(LogLevel.INFO, "Automatic restart triggered due to unexpected server shutdown.")
            self.runner.start()
    

    def _scheduled_restart(self):
        """Internal method to handle scheduled restarts. Ran in a separate thread."""
        while True:
            # Get current time and today's restart time
            now = datetime.now()
            restart_date = now.replace(hour=self.restart_time[0], minute=self.restart_time[1], second=0, microsecond=0)

            # If today's restart time has passed, schedule for tomorrow
            if now >= restart_date:
                restart_date += timedelta(days=1)

            # Calculate seconds until restart
            seconds_until_restart = (restart_date - now).total_seconds()

            self.log_print(LogLevel.INFO, f"Scheduled server restart in {int(seconds_until_restart // 60)} minutes.")

            # Subtract RESTART_WARNING_MINUTES for the warning period
            restart_date = restart_date - timedelta(minutes=RESTART_WARNING_MINUTES)
            seconds_until_restart = (restart_date - now).total_seconds()

            sleep(seconds_until_restart)

            # Warn users about the restart
            self.log_print(LogLevel.INFO, f"Server will restart in {RESTART_WARNING_MINUTES} minutes. Please prepare to log out.")
            with self.runner.lock():
                if self.runner.is_running():
                    self.runner.send_command(f"say Server will restart in {RESTART_WARNING_MINUTES} minutes. Please prepare to log out.")

            # Sleep for the warning period
            sleep(RESTART_WARNING_MINUTES * 60)

            # Perform the restart
            self.log_print(LogLevel.INFO, "Performing scheduled server restart now.")

            with self.runner.lock():
                try:
                    # Stop the server if it running
                    if self.runner.is_running():
                        self.runner.stop()
                    # Perform a world backup
                    self._backup_world_offline()
                    # If auto-update is enabled in config, check for a server update (skipping the world backup)
                    self.update_server(skip_world_backup=True)
                    # Start the server again
                    self.runner.start()
                except Exception as e:
                    self.log_print(LogLevel.ERROR, f"Scheduled restart failed: {e}")

    
    def get_online_players(self):
        """Get the list of online players from the server."""
        if not self.runner.is_running():
            return "No online players (server is offline)."

        stdout_queue = queue.Queue()
        def queue_server_output(level, _ts, message, _line):
            stdout_queue.put((level, message))
        self.runner.stdout_broadcaster.subscribe(queue_server_output)

        try:
            try:
                self.runner.send_command("list")
            except RuntimeError:
                self.log_print(LogLevel.ERROR, "Failed to send 'list' command: server is not running.")
                return "No online players (server is offline)."

            players = []
            player_count = 0
            max_players = 0
            while True:
                try:
                    level, message = stdout_queue.get(timeout=5.0)
                except queue.Empty:
                    self.log_print(LogLevel.WARN, "Timed out waiting for response to 'list' command.")
                    return "Failed to get online players: no response from server."
                # Look for the "There are X/Y players online" header
                if player_count == 0:
                    match = PLAYERS_ONLINE_PATTERN.search(message)
                    if match:
                        player_count = int(match.group(1))
                        max_players = int(match.group(2))
                        if player_count == 0:
                            return f"There are 0/{max_players} players online."
                # Player names follow the header, one per RAW line
                elif level == LogLevel.RAW:
                    players.append(message.strip())
                    if len(players) >= player_count:
                        break
        finally:
            self.runner.stdout_broadcaster.unsubscribe(queue_server_output)

        return f"There are {player_count}/{max_players} players online: {', '.join(players)}"


    def _prune_old_backups(self, backup_root: Path):
        """
        Internal method to delete old backups based on the backup duration setting.
        Args:
            backup_root (Path): The root directory where backups are stored.
        """
        self.log_print(LogLevel.INFO, "Pruning old backups...")
        cutoff_time = datetime.now() - timedelta(days=self.backup_duration)
        pruned = []
        for backup in backup_root.iterdir():
            try:
                backup_time = datetime.fromtimestamp(backup.stat().st_mtime)
            except Exception as e:
            # TODO: Improve error message with exception details
                self.log_print(LogLevel.ERROR, f"Failed to get backup timestamp for backup {backup.name}: {e}")
                continue
            if backup_time < cutoff_time:
                # Skip protected backups, temporary backups, and only delete valid backups
                if backup.name.startswith(PROTECTED_BACKUP_PREFIX) or backup.name.startswith(TEMPORARY_PREFIX):
                    continue
                elif not (backup.name.startswith(OFFLINE_BACKUP_PREFIX) or backup.name.startswith(ONLINE_BACKUP_PREFIX)):
                    continue
                try:
                    if backup.is_dir():
                        shutil.rmtree(backup)
                    else:
                        backup.unlink()
                    pruned.append(backup.name)
                except Exception as e:
                    # TODO: Improve error message with exception details
                    self.log_print(LogLevel.ERROR, f"Failed to prune backup {backup.name}: {e}")
        if pruned:
            self.log_print(LogLevel.INFO, f"Pruned old backups: {', '.join(pruned)}")
        else:
            self.log_print(LogLevel.INFO, "No old backups to prune.")


    def _backup_world_offline(self, skip_pruning: bool = False):
        """
        Perform a backup of the world when the server is offline.
        Args:
            skip_pruning (bool): If True, skip pruning old backups after creating the backup.
        """
        # Use the runner's lock to ensure atomic operation
        with self.runner.lock():
            # Refuse to backup if the server is running
            if self.runner.is_running():
                self.log_print(LogLevel.ERROR, "Cannot perform offline backup while server is running.")
                return None
            
            # Prepare paths to backup
            world_dir = Path(self.server_folder) / WORLDS_FOLDER_NAME / self.world_name
            backup_root = Path(self.backup_folder)
            backup_root.mkdir(parents=True, exist_ok=True)

            timestamp = strftime(BACKUP_TIMESTAMP_FORMAT)
            dest_dir = backup_root / f"{OFFLINE_BACKUP_PREFIX}_{timestamp}"
            temp_dir = backup_root / f"{TEMPORARY_PREFIX}_{OFFLINE_BACKUP_PREFIX}_{timestamp}"

            self.log_print(LogLevel.INFO, f"Initiating offline backup to '{dest_dir.name}'")

            # Copy the world directory to a temporary location first so incomplete backups are not stored
            try:
                shutil.copytree(world_dir, temp_dir)
                temp_dir.rename(dest_dir)
            except Exception as e:
                # Remove the temporary directory if the backup fails
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                # Log an error message if the backup fails
                # TODO: Improve error message with exception details
                self.log_print(LogLevel.ERROR, f"Offline backup failed: {e}")
                return None

            # Compress the backup directory
            final_path = dest_dir
            try:
                # Compress the backup directory
                shutil.make_archive(str(dest_dir), 'zip', root_dir=backup_root, base_dir=dest_dir.name)
                # Remove the uncompressed backup directory
                shutil.rmtree(dest_dir, ignore_errors=True)
                final_path = dest_dir.with_suffix('.zip')
            except Exception as e:
                self.log_print(LogLevel.WARN, f"Offline backup compression failed, keeping folder backup: {e}")

            self.log_print(LogLevel.INFO, f"Successfully completed offline world backup: {final_path.name}")

            # Prune old backups from the backup directory
            if not skip_pruning:
                self._prune_old_backups(backup_root)

            # Return the final backup path for further processing if needed
            return final_path


    def _backup_world_online(self, skip_pruning: bool = False):
        """
        Perform a backup of the world while the server remains online.
        Args:
            skip_pruning (bool): Default is False, if True, skip pruning old backups after creating the backup.
        """
        # Use the runner's lock to ensure atomic operation
        with self.runner.lock():
            # Refuse to backup if the server is not running
            if not self.runner.is_running():
                self.log_print(LogLevel.ERROR, "Cannot perform online backup: server is not running.")
                return None

            # Prepare paths to backup
            world_dir = Path(self.server_folder) / WORLDS_FOLDER_NAME / self.world_name
            backup_root = Path(self.backup_folder)
            backup_root.mkdir(parents=True, exist_ok=True)

            timestamp = strftime(BACKUP_TIMESTAMP_FORMAT)
            dest_dir = backup_root / f"{ONLINE_BACKUP_PREFIX}_{timestamp}"
            temp_dir = backup_root / f"{TEMPORARY_PREFIX}_{ONLINE_BACKUP_PREFIX}_{timestamp}"

            self.log_print(LogLevel.INFO, f"Initiating online backup to '{dest_dir.name}'; expect ERROR messages indicating a previous save has not been completed.")

            # Step 1: save hold
            try:
                self.runner.send_command("save hold")
            except RuntimeError:
                self.log_print(LogLevel.ERROR, f"Failed to send 'save hold': server is not running.")
                return None

            # Step 2: save query
            hold_confirmed = False
            hold_deadline = time() + SAVE_QUERY_TIMEOUT_SECONDS
            file_list_line = None

            # Temporarily subscribe to stdout to monitor for the success or failure of the save query command
            stdout_queue = queue.Queue()
            def queue_server_output(level, _ts, message, _line):
                stdout_queue.put((level, message))
            self.runner.stdout_broadcaster.subscribe(queue_server_output)

            try:
                while time() < hold_deadline and not hold_confirmed:
                    # Run the save query command
                    try:
                        self.runner.send_command("save query")
                    except RuntimeError:
                        self.log_print(LogLevel.ERROR, f"Failed to send 'save query': server is not running.")
                        return None
                    # Read lines from the queue until we see the success or failure pattern, or until we hit the timeout
                    while True:
                        try:
                            _level, message = stdout_queue.get(timeout=max(0.01, hold_deadline - time()))
                            if SUCCESS_PATTERN.match(message):
                                hold_confirmed = True
                                break
                            elif FAIL_PATTERN.match(message):
                                # If we get a failure message, drain the queue and break to retry the save query command
                                while not stdout_queue.empty():
                                    stdout_queue.get_nowait()
                                break
                        except queue.Empty:
                            break

                # If hold was not confirmed, send save resume and abort
                if not hold_confirmed:
                    self.log_print(LogLevel.WARN, "Save query timed out; aborting backup.")
                    try:
                        self.runner.send_command("save resume")
                    except RuntimeError:
                        self.log_print(LogLevel.ERROR, "Save resume failed, server may still be in hold state.")
                    return None

                # The file list arrives on the line immediately after the success message
                try:
                    while True:
                        level, message = stdout_queue.get(timeout=1.0)
                        if level == LogLevel.RAW:
                            file_list = message
                            break
                except queue.Empty:
                    self.log_print(LogLevel.WARN, "Timed out waiting for file list after save query.")
                    try:
                        self.runner.send_command("save resume")
                    except RuntimeError:
                        self.log_print(LogLevel.ERROR, "Save resume failed, server may still be in hold state.")
                    return None
            finally:
                self.runner.stdout_broadcaster.unsubscribe(queue_server_output)

            # Extract file list from the line following the success message
            files = []
            entries = file_list.split(', ')
            for entry in entries:
                if ':' in entry:
                    path, size = entry.rsplit(':', 1)
                    files.append((path, int(size)))

            # Step 3: copy the necessary files to a temporary location
            self.log_print(LogLevel.INFO, "Copying necessary files for online backup...")
            try:
                # Copy each file reported by the save query
                for file_path, file_size in files:
                    # Create source and destination paths for each file
                    source = world_dir / file_path.replace(f"{world_dir.name}/", "")
                    dest = temp_dir / file_path.replace(f"{world_dir.name}/", "")
                    # Ensure the destination directory exists and copy the file
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, dest)
                    # Truncate the file to the requested size
                    with open(dest, "r+b") as f:
                        f.truncate(file_size)
                # Rename the temporary directory to the final destination
                temp_dir.rename(dest_dir)
                # Resume server writes
                try:
                    self.runner.send_command("save resume")
                except RuntimeError:
                    self.log_print(LogLevel.ERROR, "Save resume failed, server may still be in hold state.")
            except Exception as e:
                # Remove the temporary directory if the backup fails
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                self.log_print(LogLevel.ERROR, f"Online world backup failed during copy: {e}")
                # Resume before returning
                try:
                    self.runner.send_command("save resume")
                except RuntimeError:
                    self.log_print(LogLevel.ERROR, "Save resume failed, server may still be in hold state.")
                return None

            # Step 4: Compress the backup directory
            final_path = dest_dir
            try:
                # Compress the backup directory
                shutil.make_archive(str(dest_dir), 'zip', root_dir=backup_root, base_dir=dest_dir.name)
                # Remove the uncompressed backup directory
                shutil.rmtree(dest_dir, ignore_errors=True)
                final_path = dest_dir.with_suffix('.zip')
            except Exception as e:
                self.log_print(LogLevel.WARN, f"Online backup compression failed, keeping folder backup: {e}")

            self.log_print(LogLevel.INFO, f"Successfully completed online world backup: {final_path.name}")

            # Prune old backups
            if not skip_pruning:
                self._prune_old_backups(backup_root)

            return final_path


    def smart_backup(self):
        """Perform a backup of the world, choosing online or offline based on server state."""
        with self.runner.lock():
            if self.runner.is_running():
                self._backup_world_online()
            else:
                self._backup_world_offline()


    def list_backups(self):
        """List existing backups in the backup directory."""
        backup_root = Path(self.backup_folder)

        backups = []
        if backup_root.exists() and backup_root.is_dir():
            for backup in backup_root.iterdir():
                # Only list valid backups
                if backup.name.startswith(OFFLINE_BACKUP_PREFIX) or backup.name.startswith(ONLINE_BACKUP_PREFIX) or backup.name.startswith(PROTECTED_BACKUP_PREFIX):
                    backups.append(backup.name)
        if backups:
            # TODO: Format output better
            return f"Existing backups: {', '.join(backups)}"
        else:
            return "No backups found."


    def mark_backup(self, identifier):
        """
        Mark a backup as protected from automatic deletion.
        Args:
            identifier (str): The name of the backup to mark, "latest" for the latest backup, or a date in YYYY-MM-DD format to mark all backups from that date.
        """
        backup_root = Path(self.backup_folder)
        if identifier.lower() == "latest":
            # Find the latest backup
            latest_backup = None
            latest_time = None
            for backup in backup_root.iterdir():
                if backup.name.startswith(OFFLINE_BACKUP_PREFIX) or backup.name.startswith(ONLINE_BACKUP_PREFIX):
                    backup_time = datetime.fromtimestamp(backup.stat().st_mtime)
                    if latest_time is None or backup_time > latest_time:
                        latest_time = backup_time
                        latest_backup = backup
            if latest_backup is not None:
                protected_name = PROTECTED_BACKUP_PREFIX + "_" + latest_backup.name
                latest_backup.rename(backup_root / protected_name)
                self.log_print(LogLevel.INFO, f"Marked latest backup as protected: {protected_name}")
                return f"Marked latest backup as protected: {protected_name}"
            else:
                self.log_print(LogLevel.WARN, "No backups found to mark as protected.")
                return "No backups found to mark as protected."
        elif DATE_PATTERN.match(identifier):
            # Mark all backups from the given date
            date_str = identifier
            marked_backups = []
            for backup in backup_root.iterdir():
                if backup.name.startswith(OFFLINE_BACKUP_PREFIX) or backup.name.startswith(ONLINE_BACKUP_PREFIX):
                    backup_time = datetime.fromtimestamp(backup.stat().st_mtime)
                    if backup_time.strftime("%Y-%m-%d") == date_str:
                        protected_name = PROTECTED_BACKUP_PREFIX + "_" + backup.name
                        backup.rename(backup_root / protected_name)
                        marked_backups.append(protected_name)
            if marked_backups:
                self.log_print(LogLevel.INFO, f"Marked backups from {date_str} as protected: {', '.join(marked_backups)}")
                return f"Marked backups from {date_str} as protected: {', '.join(marked_backups)}"
            else:
                self.log_print(LogLevel.WARN, f"No backups found from date {date_str} to mark as protected.")
                return f"No backups found from date {date_str} to mark as protected."
        else:
            # Mark a specific backup by name
            backup_path = backup_root / identifier
            if backup_path.exists() and (backup_path.name.startswith(OFFLINE_BACKUP_PREFIX) or backup_path.name.startswith(ONLINE_BACKUP_PREFIX)):
                protected_name = PROTECTED_BACKUP_PREFIX + "_" + backup_path.name
                backup_path.rename(backup_root / protected_name)
                self.log_print(LogLevel.INFO, f"Marked backup as protected: {protected_name}")
                return f"Marked backup as protected: {protected_name}"
            else:
                self.log_print(LogLevel.WARN, f"Backup '{identifier}' not found to mark as protected.")
                return f"Backup '{identifier}' not found to mark as protected."


    def unmark_backup(self, identifier):
        """
        Unmark a backup from being protected from automatic deletion.
        Args:
            identifier (str): The name of the backup to unmark, "latest" for the latest backup, or a date in YYYY-MM-DD format to unmark all backups from that date.
        """
        backup_root = Path(self.backup_folder)
        if identifier.lower() == "latest":
            # Find the latest backup
            latest_backup = None
            latest_time = None
            for backup in backup_root.iterdir():
                if backup.name.startswith(PROTECTED_BACKUP_PREFIX + "_" + OFFLINE_BACKUP_PREFIX) or backup.name.startswith(PROTECTED_BACKUP_PREFIX + "_" + ONLINE_BACKUP_PREFIX):
                    backup_time = datetime.fromtimestamp(backup.stat().st_mtime)
                    if latest_time is None or backup_time > latest_time:
                        latest_time = backup_time
                        latest_backup = backup
            if latest_backup is not None:
                unprotected_name = latest_backup.name[len(PROTECTED_BACKUP_PREFIX) + 1:]
                latest_backup.rename(backup_root / unprotected_name)
                self.log_print(LogLevel.INFO, f"Unmarked latest backup as protected: {unprotected_name}")
                return f"Unmarked latest backup as protected: {unprotected_name}"
            else:
                self.log_print(LogLevel.WARN, "No backups found to unmark as protected.")
                return "No backups found to unmark as protected."
        elif DATE_PATTERN.match(identifier):
            # Unmark all backups from the given date
            date_str = identifier
            unmarked_backups = []
            for backup in backup_root.iterdir():
                if backup.name.startswith(PROTECTED_BACKUP_PREFIX + "_" + OFFLINE_BACKUP_PREFIX) or backup.name.startswith(PROTECTED_BACKUP_PREFIX + "_" + ONLINE_BACKUP_PREFIX):
                    backup_time = datetime.fromtimestamp(backup.stat().st_mtime)
                    if backup_time.strftime("%Y-%m-%d") == date_str:
                        unprotected_name = backup.name[len(PROTECTED_BACKUP_PREFIX) + 1:]
                        backup.rename(backup_root / unprotected_name)
                        unmarked_backups.append(unprotected_name)
            if unmarked_backups:
                self.log_print(LogLevel.INFO, f"Unmarked backups from {date_str} as protected: {', '.join(unmarked_backups)}")
                return f"Unmarked backups from {date_str} as protected: {', '.join(unmarked_backups)}"
            else:
                self.log_print(LogLevel.WARN, f"No backups found from date {date_str} to unmark as protected.")
                return f"No backups found from date {date_str} to unmark as protected."
        else:
            # Unmark a specific backup by name
            backup_path = backup_root / identifier
            if backup_path.exists() and (backup_path.name.startswith(PROTECTED_BACKUP_PREFIX + "_" + OFFLINE_BACKUP_PREFIX) or backup_path.name.startswith(PROTECTED_BACKUP_PREFIX + "_" + ONLINE_BACKUP_PREFIX)):
                unprotected_name = backup_path.name[len(PROTECTED_BACKUP_PREFIX) + 1:]
                backup_path.rename(backup_root / unprotected_name)
                self.log_print(LogLevel.INFO, f"Unmarked backup as protected: {unprotected_name}")
                return f"Unmarked backup as protected: {unprotected_name}"
            else:
                self.log_print(LogLevel.WARN, f"Backup '{identifier}' not found to unmark as protected.")
                return f"Backup '{identifier}' not found to unmark as protected."


    def switch_to_backup_world(self, backup_name):
        """
        Switch the server's world to the specified backup.
        Args:
            backup_name (str): The name of the backup to switch to.
        """
        with self.runner.lock():
            # Refuse to switch if the server is running
            if self.runner.is_running():
                self.log_print(LogLevel.ERROR, "Cannot switch world while server is running.")
                return "Cannot switch world while server is running."

            # Prepare paths
            world_dir = Path(self.server_folder) / WORLDS_FOLDER_NAME / self.world_name
            backup_path = Path(self.backup_folder) / backup_name

            # Check if the backup exists
            if not backup_path.exists():
                self.log_print(LogLevel.ERROR, f"Backup '{backup_name}' does not exist.")
                return f"Backup '{backup_name}' does not exist."

            # Make an offline backup of the current world before switching and skip pruning to avoid deleting this backup (edge case)
            self.log_print(LogLevel.INFO, "Creating offline backup of current world before switching...")
            self._backup_world_offline(skip_pruning=True)

            # Remove the current world directory
            self.log_print(LogLevel.INFO, f"Removing current world directory '{world_dir.name}'...")
            try:
                shutil.rmtree(world_dir)
            except Exception as e:
                self.log_print(LogLevel.ERROR, f"Failed to remove current world directory: {e}")
                return f"Failed to remove current world directory: {e}"

            # Restore the backup to the world directory
            self.log_print(LogLevel.INFO, f"Restoring backup '{backup_name}' to world directory '{world_dir.name}'...")
            try:
                if backup_path.suffix == '.zip':
                    # Extract the zip archive if the backup is compressed
                    shutil.unpack_archive(backup_path, extract_dir=world_dir.parent)
                    # The zip's internal folder uses the original name, so strip any "protected_" prefix
                    stem = backup_path.stem
                    if stem.startswith(PROTECTED_BACKUP_PREFIX + "_"):
                        stem = stem[len(PROTECTED_BACKUP_PREFIX) + 1:]
                    extracted_dir = world_dir.parent / stem
                    extracted_dir.rename(world_dir)
                else:
                    # Copy the backup directory if it is not compressed
                    shutil.copytree(backup_path, world_dir)
            except Exception as e:
                self.log_print(LogLevel.ERROR, f"Failed to restore backup '{backup_name}': {e}")
                return f"Failed to restore backup '{backup_name}': {e}"

            self.log_print(LogLevel.INFO, f"Successfully switched world to backup '{backup_name}'.")
            return f"Successfully switched world to backup '{backup_name}'."


    def check_for_updates(self):
        """
        Check for Bedrock server updates, uses the platform to determine the correct download type.
        """
        if self.current_version is None:
            self.log_print(LogLevel.WARN, "Current server version unknown, cannot check for updates.")
            return "Current server version unknown, cannot check for updates."
        updateInfo = get_bedrock_update_info(self.current_version, self.config.platform)
        if updateInfo.error:
            self.log_print(LogLevel.ERROR, f"Update check failed: {updateInfo.error}")
            return "Update check failed."
        elif updateInfo.update_available:
            return f"Update available: {self.current_version} -> {updateInfo.latest_version}."
        else:
            return f"No update available, you are running the latest version: {updateInfo.latest_version}."
    

    def _backup_server_files(self, skip_pruning: bool = False):
        """
        Backup the server files specified in the config file before updating.
        Args:
            skip_pruning (bool): If True, skip pruning old backups after creating the backup.
        """
        # Use the runner's lock to ensure atomic operation
        with self.runner.lock():
            # Refuse to backup if the server is running
            if self.runner.is_running():
                self.log_print(LogLevel.ERROR, "Cannot perform server files backup while server is running.")
                return None
            
            # Prepare paths to backup
            server_dir = Path(self.server_folder)
            server_dir.mkdir(parents=True, exist_ok=True)
            backup_root = Path(self.backup_folder)
            backup_root.mkdir(parents=True, exist_ok=True)

            timestamp = strftime(BACKUP_TIMESTAMP_FORMAT)
            dest_dir = backup_root / f"{SERVER_BACKUP_PREFIX}_{timestamp}"
            temp_dir = backup_root / f"{TEMPORARY_PREFIX}_{SERVER_BACKUP_PREFIX}_{timestamp}"
            
            self.log_print(LogLevel.INFO, f"Backing up server files to '{dest_dir.name}'")

            # Copy the server files to a temporary location first so incomplete backups are not stored
            try:
                temp_dir.mkdir(parents=True, exist_ok=True)
                # Copy all files and folders except the worlds inside the worlds folder
                if self.config.update_backup_paths == "all":
                    for entry in server_dir.iterdir():
                        target = temp_dir / entry.name
                        if entry.name == WORLDS_FOLDER_NAME:
                            target.mkdir(parents=True, exist_ok=True)
                        elif entry.is_dir():
                            shutil.copytree(entry, target, dirs_exist_ok=True)
                        else:
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(entry, target)
                # Copy only the specified paths in the config
                else:
                    for relative_path in self.config.update_backup_paths:
                        source = server_dir / relative_path
                        target = temp_dir / relative_path
                        if source.name == WORLDS_FOLDER_NAME:
                            self.log_print(LogLevel.WARN, f"Skipping worlds folder in server files backup: {source}")
                        elif source.is_dir():
                            shutil.copytree(source, target, dirs_exist_ok=True)
                        elif source.exists():
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(source, target)
                        else:
                            self.log_print(LogLevel.WARN, f"Specified backup path does not exist, skipping: {source}")
                temp_dir.rename(dest_dir)
            except Exception as e:
                # Remove the temporary directory if the backup fails
                if temp_dir.exists():
                    shutil.rmtree(temp_dir, ignore_errors=True)
                # Log an error message if the backup fails
                # TODO: Improve error message with exception details
                self.log_print(LogLevel.ERROR, f"Server files backup failed: {e}")
                return None
            
            # Compress the backup directory
            final_path = dest_dir
            try:
                # Compress the backup directory
                shutil.make_archive(str(dest_dir), 'zip', root_dir=backup_root, base_dir=dest_dir.name)
                # Remove the uncompressed backup directory
                shutil.rmtree(dest_dir, ignore_errors=True)
                final_path = dest_dir.with_suffix('.zip')
            except Exception as e:
                self.log_print(LogLevel.WARN, f"Server files backup compression failed, keeping folder backup: {e}")

            self.log_print(LogLevel.INFO, f"Successfully completed server files backup: {final_path.name}")

            # Prune old backups from the backup directory
            if not skip_pruning:
                self._prune_old_backups(backup_root)

            # Return the final backup path for further processing if needed
            return final_path

    
    def _extract_update_files(self, download_path):
        """
        Extract the downloaded update zip directly into the server folder, skipping protected paths.
        Args:
            download_path (Path): The path to the downloaded update zip file.
        """
        self.log_print(LogLevel.INFO, "Extracting update files to server folder...")
        server_dir = Path(self.server_folder)
        try:
            with zipfile.ZipFile(download_path, 'r') as zf:
                # Grab all files in the zip
                files = [x for x in zf.infolist() if not x.is_dir()]
                total = len(files)
                last_logged = -1
                # For every file, check if it is protected before extracting, and log progress every 25%
                for i, file in enumerate(files):
                    relative_path = Path(file.filename)

                    # Check if the file or any of its parent directories are protected
                    is_protected = any(
                        relative_path == Path(p) or Path(p) in relative_path.parents
                        for p in self.config.update_protected_paths
                    )
                    if is_protected:
                        self.log_print(LogLevel.INFO, f"Skipping protected file: {relative_path}")
                        continue

                    dest = server_dir / relative_path
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(file) as src, open(dest, 'wb') as dst:
                        shutil.copyfileobj(src, dst)

                    # Log progress every 25%
                    percent = (i + 1) * 100 // total
                    if percent // 25 > last_logged // 25 and percent != 100:
                        self.log_print(LogLevel.INFO, f"Extracting update files: {percent}% ({i + 1}/{total} files)")
                        last_logged = percent
                # Log completion at 100%
                self.log_print(LogLevel.INFO, f"Extracting update files: 100% ({total}/{total} files)")
        except Exception as e:
            self.log_print(LogLevel.CRITICAL, f"Failed to extract update files, server may be in a non-functional state: {e}")
            return False

        self.log_print(LogLevel.INFO, "Update files extracted successfully.")
        return True


    def update_server(self, skip_world_backup: bool = False):
        """
        Update the Bedrock server to the latest version.
        Uses:
            _get_bedrock_update_info: to check for updates and get the download URL.
            _backup_server_files: to backup server files before updating.
            _extract_update_files: to extract the downloaded update files to the server folder.
        Args:
            skip_world_backup (bool): If True, skip creating a backup of the world before updating. Not recommended, use with caution.
        Returns:
            bool: True if a world backup was created before the update attempt, False otherwise.
        """

        with self.runner.lock():
            # Refuse to update if the server is running
            if self.runner.is_running():
                self.log_print(LogLevel.ERROR, "Cannot update server while it is running.")
                return "Cannot update server while it is running."
            
            # Verify the current version is known before proceeding with an update
            server_dir = Path(self.server_folder)
            if self.current_version is None:
                self.log_print(LogLevel.ERROR, "Cannot check for updates: server version is unknown. Ensure the server has started successfully.")
                return "Cannot check for updates: server version is unknown. Ensure the server has started successfully."

            # Check for updates and get the download URL
            updateInfo = get_bedrock_update_info(self.current_version, self.config.platform)
            if updateInfo.error:
                self.log_print(LogLevel.ERROR, f"Update check failed: {updateInfo.error}")
                return "Update check failed."
            elif not updateInfo.update_available:
                self.log_print(LogLevel.INFO, f"No update available, you are running the latest version: {updateInfo.latest_version}.")
                return "No update available."

            self.log_print(LogLevel.INFO, f"Updating server from version {self.current_version} to {updateInfo.latest_version}...")

            # Backup the world and server files before updating
            if not skip_world_backup:
                if not self._backup_world_offline(skip_pruning=True):
                    self.log_print(LogLevel.ERROR, "Failed to create world backup before update.")
                    return "Failed to create world backup before update."

            if not self._backup_server_files(skip_pruning=True):
                self.log_print(LogLevel.ERROR, "Failed to create server backup before update.")
                return "Failed to create server backup before update."

            # Prepare paths to update the bedrock server
            temp_dir = Path(f"{TEMPORARY_PREFIX}_bedrock_update")
            download_path = temp_dir / "update.zip"

            # Download the new server files
            self.log_print(LogLevel.INFO, f"Downloading update from {updateInfo.download_url}...")
            try:
                temp_dir.mkdir(parents=True, exist_ok=True)
                headers = {
                    "User-Agent": "BedrockUpdater",
                    "Accept": "*/*",
                    "Accept-Encoding": "identity",  # Disable compression so Content-Length is accurate
                }
                with requests.get(updateInfo.download_url, headers=headers, stream=True, timeout=(DOWNLOAD_CONNECT_TIMEOUT_SECONDS, DOWNLOAD_READ_TIMEOUT_SECONDS)) as resp:
                    resp.raise_for_status()
                    with open(download_path, "wb") as f:
                        total = int(resp.headers.get('Content-Length', 0))
                        downloaded = 0
                        last_logged = -1
                        for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total:
                                    percent = downloaded * 100 // total
                                    # Log progress every 25% or on completion
                                    if percent // 25 > last_logged // 25:
                                        self.log_print(LogLevel.INFO, f"Downloading update zip: {percent}% ({downloaded // DOWNLOAD_CHUNK_SIZE}MB / {total // DOWNLOAD_CHUNK_SIZE}MB)")
                                        last_logged = percent
            except Exception as e:
                # Clean temp if created
                shutil.rmtree(temp_dir, ignore_errors=True)
                self.log_print(LogLevel.ERROR, f"Failed to download update: {e}")
                return "Failed to download update."
            self.log_print(LogLevel.INFO, "Download completed.")

            # Extract the downloaded files to the server folder (overwrite existing files)
            success = self._extract_update_files(download_path)

            # Clean up the downloaded zip file and temporary directory
            self.log_print(LogLevel.INFO, "Cleaning up temporary files...")
            shutil.rmtree(temp_dir, ignore_errors=True)

            # If the extraction failed, return an error message (log message is handled in the extraction method)
            if not success:
                return "Failed to extract update files. Server may be in a non-functional state, manual intervention may be required."

            # Update the current version to the new version after a successful update
            self.current_version = updateInfo.latest_version
            self.log_print(LogLevel.INFO, f"Server updated successfully to version {updateInfo.latest_version}.")
            return "Server updated successfully."