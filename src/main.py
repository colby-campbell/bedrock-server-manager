import sys
import os
from pathlib import Path
from core import ServerConfig, ServerConfigError, SettingsFileMissing, ServerRunner, ServerAutomation
from utils import ServerOutput, Platform, download_and_extract_bedrock
from cli import CommandLineInterface
from bot import DiscordBot
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
    if bot is not None and bot.running:
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

    try:
        # Get config info, create server runner and automation instances, and create the discord bot
        try:
            config = ServerConfig()
        except SettingsFileMissing as e:
            output_handler.add_error(str(e), "config")
            sys.exit(0)
        except ServerConfigError as e:
            output_handler.add_error(str(e), "config")
            sys.exit(1)

        # Auto-download server files on fresh install
        executable_name = "bedrock_server" if config.platform == Platform.Linux else "bedrock_server.exe"
        if not os.path.isfile(os.path.join(config.server_folder, executable_name)):
            folder_is_empty = not any(Path(config.server_folder).iterdir())
            if not folder_is_empty:
                output_handler.add_error(
                    f"server executable not found in '{config.server_folder}'; "
                    f"if this is a fresh install, ensure the server folder is empty",
                    "main"
                )
                sys.exit(1)
            print("bedrock-server:\n  main:\n    server files not found, downloading and extracting Bedrock server software...")
            try:
                download_and_extract_bedrock(config.platform, config.server_folder)
                print()
            except RuntimeError as e:
                output_handler.add_error(str(e), "downloader")
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

    except KeyboardInterrupt:
        output_handler.add_message("keyboard interrupt received, shutting down...", "main")
        sys.exit(0)
