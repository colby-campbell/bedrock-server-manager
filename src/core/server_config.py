import tomllib
import os
import re
import platform
from enum import Enum
from utils import Platform


# Constants
SETTINGS_FILE = "settings.toml"
SERVER_PROPERTIES_FILE = "server.properties"
LEVEL_NAME_KEY = "level-name"
DEFAULT_WORLD_NAME = "Bedrock level"
DEFAULT_DISCORD_COMMANDS = [
    "cmd", "start", "stop", "restart", "backup",
    "list", "mark", "unmark", "switch", "check",
    "update", "help", "online"
]
ROOT_LEVEL_KEYS = {
    "server_folder", "log_folder", "backup_folder", "backup_duration",
    "shutdown_timeout", "crash_limit", "restart_time", "discord_bot",
    "bot_token", "admin_list", "auto_update", "update_protected_paths",
    "update_backup_paths", "platform", "world_name"
}


class ServerConfigError(Exception):
    """Raised when the configuration file exists but is invalid."""


class SettingsFileMissing(Exception):
    """Raised when the settings file is missing and a sample was created."""


class ServerConfig:
    """
    Class to read and validate the server configuration from a TOML file.
    """

    class SettingType(Enum):
        """Enum for different setting types."""
        STRING = 1
        INTEGER = 2
        BOOLEAN = 3
        LIST_OF_INTEGERS = 4
        LIST_OF_STRINGS = 5
        LIST_OF_STRINGS_OR_ALL = 6
        FOLDER = 7
        TIME = 8
        PLATFORM = 9
        CURRENT_TABLE = 10

    class SettingContainer:
        """Container for a setting value, its name, and type."""
        def __init__(self, setting_value, setting_name, setting_type):
            self.setting_value = setting_value
            self.setting_name = setting_name
            self.setting_type = setting_type

    # A sample if no config exists
    SAMPLE_TOML = f"""\
    # Server Configuration File ({SETTINGS_FILE})

    server_folder="server"
    # The folder where the Bedrock server files are to be located.
    # Allowed Values: Any valid folder path.

    log_folder="logs"
    # The folder where log files are to be stored.
    # Allowed Values: Any valid folder path.

    backup_folder="backups"
    # The folder where backups are to be stored.
    # Allowed Values: Any valid folder path.

    backup_duration=7
    # Duration in days to keep backups.
    # Allowed Values: Any positive integer.

    shutdown_timeout=60
    # Time in seconds to wait for the server to shut down gracefully before forcing termination.
    # Allowed Values: Any positive integer.

    crash_limit=3
    # Number of crashes within a period of 10 minutes before giving up restarting.

    restart_time="03:30"
    # Time to restart the server daily in HH:MM (24-hour) format.
    # Allowed Values: "HH:MM" where HH is 00-23 and MM is 00-59

    auto_update=true
    # Whether to enable automatic updates (recommended).
    # Allowed Values: true, false

    update_protected_paths=["server.properties", "allowlist.json", "permissions.json", "profanity_filter.wlist"]
    # List of server files/folders to protect from being overwritten during an update (worlds are always protected).
    # Allowed Values: [string, string, ...]

    update_backup_paths=["server.properties", "allowlist.json", "permissions.json", "profanity_filter.wlist"]
    # List of server files/folders to back up before performing an update, must be relative to the server folder (worlds are always backed up).
    # Allowed Values: [string, string, ...] | all

    # platform (optional)
    # If not set, this is auto-detected.
    # Set manually only if auto-detection fails.
    #platform=
    # Allowed Values: "Windows", "Linux"

    # world_name (optional)
    # If not set, this is auto-detected from 'f{LEVEL_NAME_KEY}' in {SERVER_PROPERTIES_FILE}.
    # Set manually only if auto-detection fails.
    #world_name=

    discord_bot=false
    # Whether to enable the Discord bot.
    # Allowed Values: true, false

    bot_token="bot_token_here"
    # The Discord bot token from the Discord Developer Portal, keep it secret!
    # Allowed Values: Any valid Discord bot token.
    # Required only if discord_bot=true

    admin_list=[]
    # List of Discord user IDs with admin privileges.
    # Allowed Values: [integer, integer, ...]
    # Required only if discord_bot=true

    # custom_commands (optional)
    # List of custom commands to be added to the Discord bot, each with a name, command, admin requirement, and description.
    # Allowed Values: [[name=string, command=string, admin=boolean, description=string], ...]
    # Must be placed at the end of the file due to TOML array-of-tables rules.
    
    [[custom_commands]]
    name = "coordson"
    command = "gamerule showcoordinates true"
    admin = true
    description = "Enable show coordinates."

    [[custom_commands]]
    name = "coordsoff"
    command = "gamerule showcoordinates false"
    admin = true
    description = "Disable show coordinates."
    """

    def __init__(self):
        """
        Initialize ServerConfig by loading and validating the config file.
        Raises:
            SettingsFileMissing: If the settings file is missing and a sample was created.
            ServerConfigError: If the config file exists but is invalid.
        """
        # Make sure a config file exists
        if not os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                f.write(self.SAMPLE_TOML)
            raise SettingsFileMissing(f"{SETTINGS_FILE}: not found, sample created; edit it and rerun")

        # Load the config file
        with open(SETTINGS_FILE, "rb") as f:
            try:
                cfg = tomllib.load(f)
            except tomllib.TOMLDecodeError as e:
                raise ServerConfigError(f"{SETTINGS_FILE}: invalid TOML format: {e}") from e

        # Load the config settings
        self.server_folder = cfg.get("server_folder")
        self.log_folder = cfg.get("log_folder")
        self.backup_folder = cfg.get("backup_folder")
        self.backup_duration = cfg.get("backup_duration")
        self.shutdown_timeout = cfg.get("shutdown_timeout")
        self.crash_limit = cfg.get("crash_limit")
        self.restart_time = cfg.get("restart_time")
        self.auto_update = cfg.get("auto_update")
        self.update_protected_paths = cfg.get("update_protected_paths")
        self.update_backup_paths = cfg.get("update_backup_paths")
        self.discord_bot = cfg.get("discord_bot")
        self.bot_token = cfg.get("bot_token")
        self.admins = cfg.get("admin_list")
        self.custom_commands = cfg.get("custom_commands", [])

        # Determine the platform if not set
        detected_platform = platform.system()
        platform_str = cfg.get("platform", detected_platform)
        try:
            self.platform = Platform(platform_str)
        except ValueError:
            self.platform = None

        # Determine the world name from the server's properties file if not set
        settings_path = os.path.join(self.server_folder, SERVER_PROPERTIES_FILE)
        detected_world_name = self._get_world_name_from_properties(settings_path)
        self.world_name = cfg.get("world_name", detected_world_name)

        # Validate the config file settings
        errors = self._validate()
        if errors:
            raise ServerConfigError("\n".join(errors))

    def _get_world_name_from_properties(self, properties_path):
        """
        Private method to extract the world name from the server's properties file.
        Args:
            properties_path (str): Path to the server's properties file.
        Returns:
            str: The world name extracted from the properties file.
        """
        try:
            with open(properties_path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line or line.startswith("#"):
                        continue
                    if line.strip().startswith(LEVEL_NAME_KEY) and "=" in line:
                        return line.split("=", 1)[1].strip()
        except Exception:
            pass
        return DEFAULT_WORLD_NAME
            
    def _validate(self):
        """
        Private method to validate the configuration settings.
        Returns:
            list (str): A list of error messages for invalid or missing settings.
        """

        # Shoutout to Ryan for the idea to use a list of tuples for validation
        CHECK_VARIABLES = (
            self.SettingContainer(self.server_folder, "server_folder", self.SettingType.FOLDER),
            self.SettingContainer(self.log_folder, "log_folder", self.SettingType.FOLDER),
            self.SettingContainer(self.backup_folder, "backup_folder", self.SettingType.FOLDER),
            self.SettingContainer(self.backup_duration, "backup_duration", self.SettingType.INTEGER),
            self.SettingContainer(self.shutdown_timeout, "shutdown_timeout", self.SettingType.INTEGER),
            self.SettingContainer(self.crash_limit, "crash_limit", self.SettingType.INTEGER),
            self.SettingContainer(self.restart_time, "restart_time", self.SettingType.TIME),
            self.SettingContainer(self.auto_update, "auto_update", self.SettingType.BOOLEAN),
            self.SettingContainer(self.platform, "platform", self.SettingType.PLATFORM),
            self.SettingContainer(self.world_name, "world_name", self.SettingType.STRING),
            self.SettingContainer(self.update_protected_paths, "update_protected_paths", self.SettingType.LIST_OF_STRINGS),
            self.SettingContainer(self.update_backup_paths, "update_backup_paths", self.SettingType.LIST_OF_STRINGS_OR_ALL),
            self.SettingContainer(self.discord_bot, "discord_bot", self.SettingType.BOOLEAN),
            self.SettingContainer(self.bot_token, "bot_token", self.SettingType.STRING) if self.discord_bot else None,
            self.SettingContainer(self.admins, "admin_list", self.SettingType.LIST_OF_INTEGERS) if self.discord_bot else None,
            self.SettingContainer(self.custom_commands, "custom_commands", self.SettingType.CURRENT_TABLE) if self.discord_bot else None
        )

        errors = []

        # Before validating individual settings, check for any ROOT_LEVEL_KEYS that are incorrectly placed in custom_commands blocks
        misplaced = set()
        # If any of the ROOT_LEVEL_KEYS are found in the custom_commands entry
        for entry in self.custom_commands:
            misplaced.update(ROOT_LEVEL_KEYS & set(entry.keys()))
        if misplaced:
            errors.append("custom_commands: move all [[custom_commands]] blocks to the end of the file; settings found in [[custom_commands]] blocks")

        for container in CHECK_VARIABLES:
            # Skip None containers (conditional settings)
            if container is None:
                continue
            value = container.setting_value
            name = container.setting_name
            stype = container.setting_type
            # Check for missing values or values that are misplaced in custom_commands blocks
            if value is None:
                if name in misplaced:
                    errors.append(f"{name}: found in [[custom_commands]] block; move to root level")
                else:
                    errors.append(f"{name}: missing (required)")
                continue
            # Validate based on type
            match stype:
                case self.SettingType.STRING:
                    if not isinstance(value, str):
                        errors.append(f"{name}: must be a string")
                case self.SettingType.INTEGER:
                    if not isinstance(value, int):
                        errors.append(f"{name}: must be an integer")
                case self.SettingType.BOOLEAN:
                    if not isinstance(value, bool):
                        errors.append(f"{name}: must be a boolean")
                case self.SettingType.LIST_OF_INTEGERS:
                    if not isinstance(value, list):
                        errors.append(f"{name}: must be a list of integers")
                    elif not all(isinstance(item, int) for item in value):
                        errors.append(f"{name}: all items must be integers")
                case self.SettingType.LIST_OF_STRINGS:
                    if not isinstance(value, list):
                        errors.append(f"{name}: must be a list of strings")
                    elif not all(isinstance(item, str) for item in value):
                        errors.append(f"{name}: all items must be strings")
                case self.SettingType.LIST_OF_STRINGS_OR_ALL:
                    if not (isinstance(value, list) or isinstance(value, str)):
                        errors.append(f"{name}: must be a list of strings or the string 'all'")
                    elif isinstance(value, list) and not all(isinstance(item, str) for item in value):
                        errors.append(f"{name}: all items must be strings")
                    elif isinstance(value, str) and value.lower() != "all":
                        errors.append(f"{name}: if a string, must be 'all'")
                case self.SettingType.FOLDER:
                    if not isinstance(value, str):
                        errors.append(f"{name}: must be a string representing a folder path")
                    elif not os.path.exists(value):
                        os.mkdir(value)
                case self.SettingType.TIME:
                    if not isinstance(value, str):
                        errors.append(f"{name}: must be a string in HH:MM format")
                    else:
                        try:
                            pattern = r'^([01]?[0-9]|2[0-3]):([0-5][0-9])$'
                            match = re.match(pattern, value)
                            if not match:
                                errors.append(f"{name}: {value}: invalid time")
                            else:
                                # Store as [hour, minute]
                                setattr(self, name, [int(match.group(1)), int(match.group(2))])
                        except ValueError:
                            errors.append(f"{name}: {value}: cannot contain non-integer numbers")
                case self.SettingType.PLATFORM:
                    if not isinstance(value, Platform):
                        errors.append(f"{name}: must be either 'Windows' or 'Linux'")
                case self.SettingType.CURRENT_TABLE:
                    if not isinstance(value, list):
                        errors.append(f"{name}: must be a list of commands")
                    else:
                        seen_names = set()
                        for i, cmd in enumerate(value):
                            if not isinstance(cmd, dict):
                                errors.append(f"{name}[{i}]: must be a table with keys 'name', 'command', 'admin', and 'description'")
                                continue
                            if "name" not in cmd or "command" not in cmd or "admin" not in cmd or "description" not in cmd:
                                errors.append(f"{name}[{i}]: missing required keys (must have 'name', 'command', 'admin', and 'description')")
                                continue
                            # name must be a string, lowercase letters, numbers, underscores, or hyphens, unique, and cannot be a default command name
                            if not isinstance(cmd["name"], str):
                                errors.append(f"{name}[{i}]['name']: must be a string")
                                continue
                            if not re.match(r'^[a-z0-9_-]+$', cmd["name"]):
                                errors.append(f"{name}[{i}]['name']: invalid command name (only lowercase letters, numbers, underscores, and hyphens allowed)")
                            elif cmd["name"] in DEFAULT_DISCORD_COMMANDS:
                                errors.append(f"{name}[{i}]['name']: cannot be a default command name ({cmd['name']})")
                            elif cmd["name"] in seen_names:
                                errors.append(f"{name}[{i}]['name']: duplicate command name '{cmd['name']}'")
                            seen_names.add(cmd["name"])
                            # command, admin, and description must be the correct types
                            if not isinstance(cmd["command"], str):
                                errors.append(f"{name}[{i}]['command']: must be a string")
                            if not isinstance(cmd["admin"], bool):
                                errors.append(f"{name}[{i}]['admin']: must be a boolean")
                            if not isinstance(cmd["description"], str):
                                errors.append(f"{name}[{i}]['description']: must be a string")
        
        return errors
