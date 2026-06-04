import sys
from core import ServerConfig
from core import ServerConfigError
from core import SettingsFileMissing
from core import ServerRunner
from core import ServerAutomation
from bot import DiscordBot
from cli import CommandLineInterface
from utils import ServerOutput
import threading
import atexit

config = None
runner = None
automation = None
bot = None
cli = None
output_handler = ServerOutput()


def cleanup():
    """Cleanup function to ensure server and bot are shut down on exit."""
    if bot is not None:
        output_handler.add_message("stopping Discord bot before exit...", "main")
        bot.discord_bot_stop()
    if runner is not None and runner.is_running():
        output_handler.add_message("stopping server before exit...", "main")
        runner.stop()
    if automation is not None and automation.logger.running:
        output_handler.add_message("stopping logger before exit...", "main")
        automation.logger.stop()
    output_handler.add_message("exited cleanly", "main")
    # Print all output messages at once
    output_handler.print_messages()


if __name__ == "__main__":
    # Register cleanup with atexit for normal and exception-based exits
    atexit.register(cleanup)

    # Get config info, create server runner and automation instances, and create the discord bot
    try:
        config = ServerConfig()
    except SettingsFileMissing as e:
        output_handler.add_error(str(e), "config")
        sys.exit(0)
    except ServerConfigError as e:
        output_handler.add_error(str(e), "config")
        sys.exit(1)

    # Create the server runner and automation instances
    runner = ServerRunner(config)
    automation = ServerAutomation(config, runner)

    # Start the Discord bot if enabled in the config
    if config.discord_bot:
        bot = DiscordBot(config, runner, automation)
        # Start the discord bot in a separate thread
        bot_thread = threading.Thread(target=bot.discord_bot_start, daemon=True)
        bot_thread.start()

    # Create the command-line interface instance
    cli = CommandLineInterface(config, runner, automation, bot)

    # Start the server and CLI
    try:
        runner.start()
    except (FileNotFoundError, RuntimeError) as e:
        output_handler.add_error(str(e), "runner")
        sys.exit(1)
    automation.start()
    cli.start()
