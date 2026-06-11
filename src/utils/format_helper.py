from datetime import datetime
import enum
import re

# Constants
SPACING_LENGTH = 9
PROCESS_LINE_REGEX = re.compile(r"\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[:,]\d{3}) (?P<level>\w+)\](?: (?P<message>.*))?")

class LogLevel(enum.Enum):
    INFO = "INFO"
    DEBUG = "DEBUG"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    RAW = "RAW"
    CLI = "CLI"
    UNKNOWN = "UNKNOWN"


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
    return " " * (max(SPACING_LENGTH - len(level.value), 1))


""" THIS WILL BE REMOVED
def get_prefix(level: LogLevel):
    # comment block start
    Get the formatted prefix for a given log level.
    Args:
        level (LogLevel): The log level.
    Returns:
        str: The formatted prefix string.
    # comment block end
    return f"{get_timestamp()} {level.value}{get_spacing(level)}"
"""
def get_prefix(level: LogLevel):
    """
    Get the formatted prefix for a given log level.
    Args:
        level (LogLevel): The log level.
    Returns:
        str: The formatted prefix string.
    """
    return f"{get_timestamp()} {level.value}{get_spacing(level)}"


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
    # Regex to parse log lines
    match = PROCESS_LINE_REGEX.match(line)
    if match:
        timestamp = match.group("timestamp")
        # Replace comma with colon in timestamp for consistency
        timestamp = timestamp.replace(",", ":")
        level = match.group("level")
        # Calculate spacing for alignment
        spacing = " " * (max(SPACING_LENGTH - len(level), 1))
        # Get the message part ('or ""' to handle None case)
        message = match.group("message") or ""
        # Return the formatted line
        try:
            level_enum = LogLevel[match.group("level")]
        except KeyError:
            level_enum = LogLevel.UNKNOWN
        return level_enum, timestamp, message, f"{timestamp} {level}{spacing}{message}"
    else:
        # If the line doesn't contain a timestamp, return it with a RAW level
        timestamp = get_timestamp()
        return LogLevel.RAW, timestamp, line, f"{timestamp} {LogLevel.RAW.value}{get_spacing(LogLevel.RAW)}{line}"


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
    return level, timestamp, message, f"{timestamp} {level.value}{get_spacing(level)}{message}"
