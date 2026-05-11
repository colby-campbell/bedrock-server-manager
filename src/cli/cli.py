from prompt_toolkit import prompt, print_formatted_text, ANSI, PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from utils import get_timestamp
import re


def add_colour(prefix, message):
    """Process a line from the server."""
    # Regex to parse log lines
    pattern = re.compile(r"(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[:,]\d{3}) (?P<level>\w+)")
    match = pattern.match(prefix)
    if match:
        timestamp = match.group("timestamp")
        level = match.group("level")
        # ANSI color codes based on log level
        match level:
            case "RAW":
                ansi_code = "\033[32m"  # Green for raw
            case "DEBUG":
                ansi_code = "\033[36m"  # Cyan for debug
            case "INFO":
                ansi_code = "\033[34m"  # Blue for info
            case "WARN":
                ansi_code = "\033[33m"  # Yellow for warning
            case "ERROR":
                ansi_code = "\033[31m"  # Red for error
            case "CRITICAL":
                ansi_code = "\033[1;31m"  # Bold red for critical
            case _:
                ansi_code = "\033[33m"  # Default to yellow for unrecognized levels
        # Calculate spacing for alignment
        spacing = " " * (max(9 - len(level), 1))
        # Return the formatted line with ANSI codes
        return f"\033[1;90m{timestamp} {ansi_code}{level}\033[0m{spacing}{message}"
    else:
        # If the line's timestamp fails the regular expression, return it with an error
        return f"Failed to format line: {prefix}{message}"


class CommandLineInterface:
    """
    Command-Line Interface for interacting with the Minecraft Bedrock server.
    """

    BLOCKED_COMMANDS = {'stop', 'start', 'restart', 'exit', 'quit'}

    def __init__(self, config, runner, automation, bot):
        """
        Initialize the Command-Line Interface with configuration, server runner, automation, and bot instances.
        Args:
            config (ServerConfig): The server configuration instance.
            runner (ServerRunner): The server runner instance.
            automation (ServerAutomation): The server automation instance.
            bot (DiscordBot): The Discord bot instance.
        """
        self.config = config
        self.discord_bot = config.discord_bot
        self.runner = runner
        # Subscribe to the stdout broadcaster and unexpected shutdown broadcaster
        self.runner.stdout_broadcaster.subscribe(self.handle_server_output)
        self.automation = automation
        self.automation.automation_output_broadcaster.subscribe(self.handle_automation_ouput)
        self.bot = bot
        # Subscribe to the discord bot broadcaster if bot is provided
        if self.bot is not None:
            self.bot.broadcaster.subscribe(self.handle_discord_output)
        # TODO: Should I replace this with a unsubscribe?
        # Running variable so as to know when to stop printing to the screen
        self.running = True


    def handle_server_output(self, timestamp, line):
        """Handle server output lines by printing them to the CLI."""
        if self.running:
            print_formatted_text(ANSI(add_colour(timestamp, line)))


    def handle_automation_ouput(self, timestamp, line):
        """Handle automation output by printing it to the CLI."""
        if self.running:
            print_formatted_text(ANSI(add_colour(timestamp, line)))


    def handle_discord_output(self, timestamp, line):
        """Handle discord output log messages by printing them to the CLI."""
        if self.running:
            print_formatted_text(ANSI(add_colour(timestamp, line)))


    def log_print(self, line):
        """Prints to the screen with colour codes, and prints to the log without colour codes"""
        timestamp = get_timestamp()
        print_formatted_text(ANSI(f"\033[1;90m{timestamp} \033[35mCLI\033[0m      {line}"))
        self.automation.logger.log(f"{timestamp} CLI      {line}")
    

    def just_print(self, line):
        """Just prints to the screen with colour codes"""
        print_formatted_text(ANSI(f"\033[1;90m{get_timestamp()} \033[35mCLI\033[0m      {line}"))


    def start(self):
        """Start the command-line interface loop."""
        session = PromptSession()
        # Starting print messages for CLI

        self.log_print("Type ':help' for a list of built-in commands.")
        self.log_print(f"Discord bot is {'ENABLED' if self.discord_bot else 'DISABLED'}")
        # Main input loop
        while True:
            # Prompt for input
            try:
                with patch_stdout():
                    input_text = session.prompt('bedrock-server> ').strip()
            except EOFError:
                # If the bot is not running or is fully started or fully stopped, allow exit
                if self.bot is None or self.bot is not None and self.bot.bot.is_ready() or self.bot is not None and self.bot.bot.is_closed():
                    self.log_print("EOF received, forcefully exiting CLI...")
                    self.running = False
                    break
                else:
                    self.log_print("Cannot forcefully exit the CLI while the Discord bot is still starting.")
                    continue
            except KeyboardInterrupt:
                # Handle Ctrl+C gracefully
                self.just_print("KeyboardInterrupt received, ignoring input.")
                continue
            
            # Built-in CLI commands
            if input_text.startswith(':'):
                # Process CLI built-in command
                cmd = input_text[1:].lower().strip()
                # Help
                if cmd == 'help':
                    help_text = """
                    Built-in commands (prefix with ':'):
                    :help          Show this help message
                    :start         Start the Minecraft Bedrock server
                    :stop          Stop the server
                    :restart       Restart the server
                    :backup        Create a world backup
                    :list          List existing backups
                    :mark <backup_name | latest | YYYY-MM-DD>
                                   Protect backup(s) from automatic deletion
                    :unmark <backup_name | latest | YYYY-MM-DD>
                                   Unprotect backup(s) from automatic deletion
                    :switch <backup_name>
                                   Switch the world to the specified backup
                    :check         Check for Bedrock server updates
                    :update        Update the Bedrock server to the latest version
                    :exit, :quit   Exit the CLI (and stop the server if running)
                    """
                    self.just_print(help_text.strip())
                # Stop
                elif cmd == 'stop':
                    if self.runner.is_running():
                        self.log_print("Stopping server...")
                        self.runner.stop()
                    else:
                        self.log_print("Server is not running.")
                # Start
                elif cmd == 'start':
                    if self.runner.is_running():
                        self.log_print("Server is already running.")
                    else:
                        self.log_print("Starting server...")
                        self.runner.start()
                # Restart
                elif cmd == 'restart':
                    if self.runner.is_running():
                        self.log_print("Restarting server...")
                        self.runner.restart()
                    else:
                        self.log_print("Server is not running, starting server...")
                        self.runner.start()
                # Backup
                elif cmd == 'backup':
                    self.log_print("Starting world backup...")
                    self.automation.smart_backup()
                # List
                elif cmd == 'list':
                    self.automation.list_backups()
                # Mark
                elif cmd.startswith('mark'):
                    args = cmd.split(maxsplit=1)
                    if len(args) == 2:
                        backup_identifier = args[1].strip()
                        self.automation.mark_backup(backup_identifier)
                    else:
                        self.just_print("Usage: :mark <backup_name | latest | YYYY-MM-DD>")
                # Unmark
                elif cmd.startswith('unmark'):
                    args = cmd.split(maxsplit=1)
                    if len(args) == 2:
                        backup_identifier = args[1].strip()
                        self.automation.unmark_backup(backup_identifier)
                    else:
                        self.just_print("Usage: :unmark <backup_name | latest | YYYY-MM-DD>")
                # Switch to backup
                elif cmd.startswith('switch'):
                    if self.runner.is_running():
                        self.just_print("Cannot switch world while server is running, please stop the server first.")
                        continue
                    args = cmd.split(maxsplit=1)
                    if len(args) == 2:
                        backup_name = args[1].strip()
                        self.automation.switch_to_backup_world(backup_name)
                    else:
                        self.just_print("Usage: :switch <backup_name>")
                # Check for updates
                elif cmd == 'check':
                    self.log_print("Checking for Bedrock server updates...")
                    result = self.automation.check_for_updates()
                    self.log_print(result)
                # Update
                elif cmd == 'update':
                    if self.runner.is_running():
                        self.just_print("Cannot update the server while it is running, please stop the server first.")
                        continue
                    self.log_print("Updating Bedrock server to the latest version...")
                    self.automation.update_server()
                # Exit
                elif cmd == 'exit' or cmd == 'quit':
                    # If the bot is not running or is fully started or fully stopped, allow exit
                    if self.bot is None or self.bot is not None and self.bot.bot.is_ready() or self.bot is not None and self.bot.bot.is_closed():
                        if self.runner.is_running():
                            self.log_print("Stopping server before exit...")
                            self.runner.stop()
                        self.log_print("Exiting CLI...")
                        self.running = False
                        break
                    else:
                        self.just_print("Cannot exit the CLI while the Discord bot is still starting.")
                else:
                    self.just_print(f"Unknown command '{cmd}'.")

            # Normal server command input
            else:
                # Block blocked CLI commands without prefix
                words = input_text.lower().split()
                if words and words[0] in self.BLOCKED_COMMANDS:
                    self.just_print(f"Command '{words[0]}' is blocked. Use built-in CLI command ':{words[0]}' instead.")
                # Special case of giving a hint for the 'help' command if the user types it without the prefix
                elif len(words) == 1 and words[0] == "help":
                    self.just_print("You are passing input for the bedrock server itself, if you want to see the CLI built-in commands, type ':help'.")
                    self.runner.send_command("help")
                # Otherwise send it as normal server input
                elif words and self.runner.is_running():
                    self.runner.send_command(input_text)
                else:
                    self.just_print("Server is not running, start the server to send commands.")
