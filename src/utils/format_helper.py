from datetime import datetime
import enum
import re

# Constants
SPACING_LENGTH = 9
PROCESS_LINE_REGEX = re.compile(r"\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[:,]\d{3}) (?P<level>\w+)\](?: (?P<message>.*))?")

class LogLevel(enum.Enum):
    INFO = ("INFO", "\033[34m") # Blue
    DEBUG = ("DEBUG", "\033[36m") # Cyan
    WARN = ("WARN", "\033[33m") # Yellow
    ERROR = ("ERROR", "\033[31m") # Red
    CRITICAL = ("CRITICAL", "\033[1;31m") # Bold Red
    RAW = ("RAW", "\033[32m") # Green
    CLI = ("CLI", "\033[35m") # Magenta
    UNKNOWN = ("UNKNOWN", "\033[1;33m") # Bold Yellow

    def __init__(self, label, ansi_code):
        self.label = label
        self.ansi_code = ansi_code


def get_timestamp():
    """Get the current timestamp in the format YYYY-MM-DD HH:MM:SS:MMM"""
    now = datetime.now()
    return now.strftime("%Y-%m-%d %H:%M:%S") + f":{now.microsecond // 1000:03d}"


def get_spacing(level: LogLevel):
    """
    Get spacing for log level alignment.
    Args:
        level (LogLevel): The log level.
    Returns:
        str: The spacing string.
    """
    return " " * (max(SPACING_LENGTH - len(level.label), 1))


def get_prefix(level: LogLevel):
    """
    Get the formatted prefix for a given log level.
    Args:
        level (LogLevel): The log level.
    Returns:
        str: The formatted prefix string.
    """
    return f"{get_timestamp()} {level.label}{get_spacing(level)}"


def process_line(line: str):
    """
    Process a line from the server.
    Args:
        line (str): The line to process.
    Returns:
        level (LogLevel): The log level.
        timestamp (str): The timestamp.
        message (str): The message.
        line (str): The complete formatted line.
    """
    match = PROCESS_LINE_REGEX.match(line)
    if match:
        timestamp = match.group("timestamp")
        # Replace comma with colon in timestamp for consistency
        timestamp = timestamp.replace(",", ":")
        level = match.group("level")
        message = match.group("message") or ""
        try:
            level_enum = LogLevel[level]
        except KeyError:
            level_enum = LogLevel.UNKNOWN
        spacing = get_spacing(level_enum)
        return level_enum, timestamp, message, f"{timestamp} {level}{spacing}{message}"
    else:
        timestamp = get_timestamp()
        return LogLevel.RAW, timestamp, line, f"{timestamp} {LogLevel.RAW.label}{get_spacing(LogLevel.RAW)}{line}"


def custom_line(level: LogLevel, message: str):
    """
    Process a custom line that doesn't come from the server.
    Args:
        message (str): The message to process.
        level (LogLevel): The log level to use for this line.
    Returns:
        level (LogLevel): The log level.
        timestamp (str): The timestamp.
        message (str): The message.
        line (str): The complete formatted line.
    """
    timestamp = get_timestamp()
    return level, timestamp, message, f"{timestamp} {level.label}{get_spacing(level)}{message}"
