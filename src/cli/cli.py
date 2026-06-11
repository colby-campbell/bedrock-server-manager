from prompt_toolkit import prompt, print_formatted_text, ANSI, PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from utils import get_spacing, custom_line, LogLevel

# Constants
BLOCKED_COMMANDS = {
        'stop': 'stop',
        'start': 'start',
        'restart': 'restart',
        'exit': 'exit',
        'quit': 'quit',
        'save': 'backup'
    }


def add_colour(level, timestamp, message):
    """Add ANSI colour codes to a line based on the log level."""
    return f"\033[1;90m{timestamp} {level.ansi_code}{level.label}\033[0m{get_spacing(level)}{message}"


class CommandLineInterface:
    """
    Command-Line Interface for interacting with the Minecraft Bedrock server.
    """

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
        self.automation.automation_output_broadcaster.subscribe(self.handle_automation_output)
        self.bot = bot
        # Subscribe to the discord bot broadcaster if bot is provided
        if self.bot is not None:
            self.bot.broadcaster.subscribe(self.handle_discord_output)
        # TODO: Should I replace this with a unsubscribe?
        # Running variable so as to know when to stop printing to the screen
        self.running = True


    def handle_server_output(self, level, timestamp, message, _line):
        """Handle server output lines by printing them to the CLI."""
        if self.running:
            print_formatted_text(ANSI(add_colour(level, timestamp, message)))


    def handle_automation_output(self, level, timestamp, message, _line):
        """Handle automation output by printing it to the CLI."""
        if self.running:
            print_formatted_text(ANSI(add_colour(level, timestamp, message)))


    def handle_discord_output(self, level, timestamp, message, _line):
        """Handle discord output log messages by printing them to the CLI."""
        if self.running:
            print_formatted_text(ANSI(add_colour(level, timestamp, message)))


    def log_print(self, message):
        """Prints to the screen with colour codes, and prints to the log without colour codes"""
        lvl, ts, msg, line = custom_line(LogLevel.CLI, message)
        print_formatted_text(ANSI(add_colour(lvl, ts, msg)))
        self.automation.logger.log(line)
    

    def just_print(self, message):
        """Just prints to the screen with colour codes"""
        lvl, ts, msg, _line = custom_line(LogLevel.CLI, message)
        print_formatted_text(ANSI(add_colour(lvl, ts, msg)))


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
                if self.bot is None or self.bot.bot.is_ready() or self.bot.bot.is_closed():
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
                parts = input_text[1:].strip().split(maxsplit=1)
                cmd = parts[0].lower()
                arg = parts[1] if len(parts) > 1 else ""

                # Help
                if cmd == 'help':
                    help_text = """
                    Built-in commands (prefix with ':'):
                    :help          Show this help message
                    :online        Show online players
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
                # Online
                elif cmd == 'online':
                    if self.runner.is_running():
                        result = self.automation.get_online_players()
                        self.just_print(result)
                    else:
                        self.log_print("Server is not running.")
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
                    result = self.automation.list_backups()
                    self.just_print(result)
                # Mark
                elif cmd == 'mark':
                    if arg:
                        self.automation.mark_backup(arg)
                    else:
                        self.just_print("Usage: :mark <backup_name | latest | YYYY-MM-DD>")
                # Unmark
                elif cmd == 'unmark':
                    if arg:
                        self.automation.unmark_backup(arg)
                    else:
                        self.just_print("Usage: :unmark <backup_name | latest | YYYY-MM-DD>")
                # Switch to backup
                elif cmd == 'switch':
                    if self.runner.is_running():
                        self.just_print("Cannot switch world while server is running, please stop the server first.")
                        continue
                    if arg:
                        self.automation.switch_to_backup_world(arg)
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
                    if self.bot is None or self.bot.bot.is_ready() or self.bot.bot.is_closed():
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
                if words and words[0] in BLOCKED_COMMANDS:
                    self.just_print(f"Command '{words[0]}' is blocked. Use built-in CLI command ':{BLOCKED_COMMANDS[words[0]]}' instead.")
                # Special case of giving a hint for the 'help' command if the user types it without the prefix
                elif len(words) == 1 and words[0] == "help":
                    self.just_print("You are passing input for the bedrock server itself, if you want to see the CLI built-in commands, type ':help'.")
                    self.runner.send_command("help")
                # Otherwise send it as normal server input
                elif self.runner.is_running():
                    self.runner.send_command(input_text)
                else:
                    self.just_print("Server is not running, start the server to send commands.")
