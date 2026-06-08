# Bedrock Server Manager

A Python toolkit to automate, configure, and manage a Minecraft Bedrock Dedicated Server, with Discord integration, automated backups, and automatic updates.

It is designed to work as-is; however, the modularity of the code allows for extensibility so people can expand upon it to add features they may want (e.g. a web application to manage the software).

## Features

- **Auto-install**: Downloads and extracts Bedrock server software automatically on first run.
- **Configuration Validation**: Reads and validates all settings from `settings.toml`; missing or invalid entries are reported with clear, structured error output.
- **Automation**: Daily scheduled restarts, automated world backups, crash detection and recovery, and automatic Bedrock server updates.
- **Discord Bot Integration**: Manage and monitor your server using Discord commands (in development).
- **Logging**: All output is logged to daily `.txt` files in the configured log folder.
- **Custom CLI**: Command-line interface for sending commands and viewing logs for the server manager, internal Bedrock server software, and Discord bot.
- **Extensible Design**: Modular, publish-subscribe architecture designed for easy expansion.

## Getting Started

### Prerequisites

- Python 3.11+
- `discord.py` package
- `prompt-toolkit` package
- `requests` package

### Installation

1. Clone or download the repository.
2. Install dependencies:
   ```
   pip install discord.py prompt-toolkit requests
   ```
3. Run `main.py` to generate a `settings.toml` sample file:
   ```
   python src/main.py
   ```
4. Edit `settings.toml` as needed, then rerun `main.py`. On first run, if the server folder is empty, the Bedrock server software will be downloaded and extracted automatically.

## Configuration

Edit `settings.toml` to specify settings. Every required value is validated at startup; invalid or missing settings will be listed as follows:

```
bedrock-server:
  server_folder: must be a string representing a folder path
  restart_time: 10:60: invalid time
```

### Settings Reference

| Setting | Type | Description |
|---|---|---|
| `server_folder` | string | Path to the folder where Bedrock server files are stored. |
| `log_folder` | string | Path to the folder where log files are stored. |
| `backup_folder` | string | Path to the folder where backups are stored. |
| `backup_duration` | integer | Number of days to keep backups before pruning. |
| `shutdown_timeout` | integer | Seconds to wait for graceful shutdown before forcing termination. |
| `crash_limit` | integer | Number of crashes within 10 minutes before halting automatic restarts. |
| `restart_time` | string | Daily restart time in `HH:MM` (24-hour) format. |
| `discord_bot` | boolean | Whether to enable the Discord bot. |
| `bot_token` | string | Discord bot token. Required only if `discord_bot=true`. |
| `admin_list` | list of integers | Discord user IDs with admin privileges. Required only if `discord_bot=true`. |
| `auto_update` | boolean | Whether to automatically update the server software on each scheduled restart. |
| `update_protected_paths` | list of strings | Server files/folders to protect from being overwritten during an update. Worlds are always protected. |
| `update_backup_paths` | list of strings \| `"all"` | Server files/folders to back up before an update. Use `"all"` to back up the entire server folder. Worlds are always backed up separately. |
| `platform` | string | `"Windows"` or `"Linux"`. Auto-detected if not set. |
| `world_name` | string | World name. Auto-detected from `server.properties` if not set. |

Settings related to the internal Minecraft Bedrock server (e.g. game mode, difficulty) can be found in the `server.properties` file in the server folder.

## Usage

Start the server manager:
```
python src/main.py
```

### CLI Commands

Commands prefixed with `:` are built-in CLI commands. Any other input is forwarded directly to the Bedrock server software (e.g. `gamemode 1 fred_the_frog`).

| Command | Description |
|---|---|
| `:help` | Show all available CLI commands. |
| `:start` | Start the Minecraft Bedrock server. |
| `:stop` | Stop the server. |
| `:restart` | Restart the server. |
| `:backup` | Create a world backup (online if server is running, offline otherwise). |
| `:list` | List existing backups. |
| `:mark <backup_name \| latest \| YYYY-MM-DD>` | Protect backup(s) from automatic deletion. |
| `:unmark <backup_name \| latest \| YYYY-MM-DD>` | Unprotect backup(s) from automatic deletion. |
| `:switch <backup_name>` | Switch the world to the specified backup (server must be stopped first). |
| `:check` | Check for Bedrock server updates. |
| `:update` | Update the Bedrock server to the latest version (server must be stopped first). |
| `:exit`, `:quit` | Exit the CLI and stop the server if running. |

### Discord Bot Commands

The Discord bot uses `!` as its command prefix. Bot commands are currently in development.

| Command | Access | Description |
|---|---|---|
| `!help` | Everyone | Show all available commands. |
| `!online` | Everyone | Show who is currently online. |
| `!stop` | Admin | Stop the server. |
| `!start` | Admin | Start the server. |
| `!restart` | Admin | Restart the server. |
| `!save` | Admin | Save the world while the server is running. |
| `!check_for_update` | Admin | Check for a server software update. |
| `!difficulty` | Admin | Set the game difficulty. |
| `!coords` | Admin | Set coordinates. |
| `!god` | Bot Owner | Access the server command-line. |

## Error Handling

- All errors return Unix-standard exit code `1`.
- All errors print structured details for straightforward troubleshooting.

## Contributing

Pull requests and feedback are welcome. Please file issues for support or feature requests.
