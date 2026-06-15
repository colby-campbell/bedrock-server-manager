from prompt_toolkit import print_formatted_text, ANSI, PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.history import FileHistory
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.auto_suggest import AutoSuggest, Suggestion
from utils import get_spacing, custom_line, LogLevel
import os
import json

# Blocked commands that should not be sent to the server if typed without the prefix, and instead should prompt the user to use the built-in CLI command with the prefix
BLOCKED_COMMANDS = {
    'stop': 'stop',
    'start': 'start',
    'restart': 'restart',
    'exit': 'exit',
    'quit': 'quit',
    'save': 'backup'
}

_CLI_COMMANDS = [
    ':help', ':online', ':start', ':stop', ':restart',
    ':backup', ':list', ':mark', ':unmark', ':switch',
    ':check', ':update', ':exit', ':quit',
]


def _load_commands():
    """Load bedrock_commands.json and return (commands dict, categories dict)."""
    commands_file = os.path.join(os.path.dirname(__file__), "bedrock_commands.json")
    try:
        with open(commands_file, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("commands", {}), data.get("categories", {})
    except (FileNotFoundError, json.JSONDecodeError):
        return {}, {}


def _tokenize(text):
    """Return (tokens, trailing_space) for the given input text."""
    tokens = text.split()
    trailing_space = bool(text) and text[-1] == ' '
    return tokens, trailing_space


def _navigate(commands, tokens, trailing_space):
    """
    Navigate the command tree given the current token list and whether the
    input ends with a space.  Returns (node, arg_index, current_word):
      - node       — the deepest matching command node
      - arg_index  — positional index within node.completions for the next completion
      - current_word — the partial token being typed ('' when trailing_space is True)
    Returns (None, 0, '') when the root command is not recognised.
    """
    if not tokens or tokens[0] not in commands:
        return None, 0, ''

    node = commands[tokens[0]]
    args = tokens[1:]

    if trailing_space:
        args_to_process, current_word = args, ''
    else:
        args_to_process, current_word = args[:-1], (args[-1] if args else '')

    arg_index = 0
    for token in args_to_process:
        children = node.get('children', {})
        if children and token in children:
            node = children[token]
            arg_index = 0
        else:
            arg_index += 1

    return node, arg_index, current_word


class BedrockCompleter(Completer):
    def __init__(self, commands, get_players):
        self._commands = commands
        self._get_players = get_players

    def get_completions(self, document, _complete_event):
        text = document.text_before_cursor
        tokens, trailing_space = _tokenize(text)

        # CLI built-in commands (start with ':')
        if text.startswith(':'):
            word = tokens[0] if tokens else ':'
            for cmd in _CLI_COMMANDS:
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(word))
            return

        # Complete the command name itself
        if not trailing_space and len(tokens) <= 1:
            word = tokens[0] if tokens else ''
            for cmd in self._commands:
                if cmd.startswith(word):
                    yield Completion(cmd, start_position=-len(word))
            return

        node, arg_index, current_word = _navigate(self._commands, tokens, trailing_space)
        if node is None:
            return

        # Offer child subcommand names first
        children = node.get('children', {})
        if children and arg_index == 0:
            for name in children:
                if name.startswith(current_word):
                    yield Completion(name, start_position=-len(current_word))
            return

        # Offer typed completions (enum values or online player names)
        comp_list = node.get('completions', [])
        if arg_index < len(comp_list):
            comp = comp_list[arg_index]
            if comp['type'] == 'players':
                for player in self._get_players():
                    if player.lower().startswith(current_word.lower()):
                        yield Completion(player, start_position=-len(current_word))
            elif comp['type'] == 'enum':
                for value in comp['values']:
                    if value.startswith(current_word):
                        yield Completion(value, start_position=-len(current_word))


class BedrockAutoSuggest(AutoSuggest):
    def __init__(self, commands):
        self._commands = commands

    def get_suggestion(self, _buffer, document):
        text = document.text_before_cursor
        if not text.strip() or text.startswith(':'):
            return None

        tokens, trailing_space = _tokenize(text)
        if not tokens or tokens[0] not in self._commands:
            return None

        node, arg_index, current_word = _navigate(self._commands, tokens, trailing_space)
        if node is None:
            return None

        args_syntax = node.get('args', [])
        if not args_syntax:
            return None

        # When mid-word on a children node let the dropdown handle it; no ghost text needed
        is_children_node = bool(node.get('children')) and arg_index == 0
        mid_word = bool(current_word) and not trailing_space

        if mid_word and not is_children_node:
            # Show args after the one currently being typed
            remaining = args_syntax[arg_index + 1:]
            if not remaining:
                return None
            return Suggestion(' ' + ' '.join(remaining))
        else:
            remaining = args_syntax[arg_index:]
            if not remaining:
                return None
            # Add a leading space when the user hasn't yet typed a space after the command
            prefix = ' ' if not trailing_space else ''
            return Suggestion(prefix + ' '.join(remaining))


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
        history_path = os.path.join(self.config.log_folder, "cli_history")
        commands, _ = _load_commands()
        session = PromptSession(
            history=FileHistory(history_path),
            completer=BedrockCompleter(commands, lambda: self.automation.online_players),
            auto_suggest=BedrockAutoSuggest(commands),
        )
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
                    result = self.automation.smart_backup()
                    self.log_print(result)
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
