# Bedrock Server Manager

The README.md has not been completed; this version is temporary and will be updated once all the features have been fully implemented.

A robust Python toolkit to automate, configure, and manage your Minecraft Bedrock Server, featuring Discord integration, validation, and automation capabilities.

It is designed to work as is; however, the modularity of the code should allow for extensibility, allowing people to expand upon this code to add features they may want (e.g. a web application to manage the software).

## Features

- **Configuration Validation**: Reads and validates all settings from `settings.toml`; missing or invalid entries are reported with clear, Unix-style error outputs.
- **Discord Bot Integration**: Manage and monitor your server using Discord commands, supporting essential functions like start, stop, restart, save, and access to server info.
- **Logging**: All output is logged into .txt files
- **Automation**: Daily restarts, automated backups, Bedrock server updates, etc.
- **Custom CLI**: Use the command-line interface to send commands and view logs for the bedrock-server-manager, internal Bedrock server software, and discord bot.
- **Extensible Design**: Modular codebase that is designed for easy expansion.

## Getting Started

### Prerequisites

- Python 3.11+
- discord package
- prompt-toolkit package
- requests package

### Installation

Download or clone the repository and run main.py to generate the `settings.toml` file. If no settings need to be changed, rerun main.py to download the Minecraft Bedrock server software and start the server manager.

## Configuration

Edit `settings.toml` to specify settings. Every required value is validated at startup; invalid or missing settings will be listed as follows:

```
bedrock-server:
  server_folder: must be a string representing a folder path
  backup_duration: must be an integer
  restart_time: 10:60: invalid time
```

Refer to the generated sample for all possible options.

Settings related to the internal Minecraft Bedrock server can be found in the `server.properties` file in the server directory.

## Usage

- Start the server and use the following commands to interact with the CLI:
- `:help`: Show all available CLI commands
- `:start`: Start the Minecraft Bedrock server
- `:stop`: Stop the server
- `:restart`: Restart the server
- `:backup` Create a world backup
- `:list` List existing backups
- `:mark <backup_name | latest | YYYY-MM-DD>`: Protect backup(s) from automatic deletion
- `:unmark <backup_name | latest | YYYY-MM-DD>`: Unprotect backup(s) from automatic deletion
- `:switch <backup_name>`: Switch the world to the specified backup (You must stop the server before running this command)
- `:check`: Check for Bedrock server updates
- `:update`: Update the Bedrock server to the latest version
- `:exit`, `:quit`: Exit the CLI (and stop the server if running)
- Any command not starting with `:` will be sent to the internal Minecraft Bedrock Server software (e.g. `gamemode 1 fred_the_frog`).

## Error Handling

- All errors return Unix-standard exit code `1`.
- All errors should print structured details for straightforward troubleshooting.

## Contributing

Pull requests and feedback are welcome! Please file issues for support or feature requests.
