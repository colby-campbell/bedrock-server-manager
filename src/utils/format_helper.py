from datetime import datetime
import enum
import re
from webbrowser import get

# Constants
SPACING_LENGTH = 9

class LogLevel(enum.Enum):
    INFO = "INFO"
    DEBUG = "DEBUG"
    WARN = "WARN"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
    RAW = "RAW"
    CLI = "CLI"


def get_timestamp():
    """Get the current timestamp in the format YYYY-MM-DD HH:MM:SS:MMM"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S") + f":{datetime.now().microsecond // 1000:03d}"


def get_spacing(level: LogLevel):
    """
    Get spacing for log level alignment.
    Args:
        level (LogLevel): The log level.
    Returns:
        str: The spacing string.
    """
    return " " * (max(SPACING_LENGTH - len(level.value), 1))


def get_prefix(level: LogLevel):
    """
    Get the formatted prefix for a given log level.
    Args:
        level (LogLevel): The log level.
    Returns:
        str: The formatted prefix string.
    """
    return f"{get_timestamp()} {level.value}{get_spacing(level)}"


def process_line(line):
    """
    Process a line from the server.
    Args:
        line (str): The line to process.
    Returns:
        list[str]: A list containing the formatted prefix and the message.
    """
    # Regex to parse log lines
    pattern = re.compile(r"\[(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}[:,]\d{3}) (?P<level>\w+)\](?: (?P<message>.*))?")
    match = pattern.match(line)
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
        return [f"{timestamp} {level}{spacing}", message]
    else:
        # If the line doesn't contain a timestamp, return it with an 'RAW' level
        return [f"{get_timestamp()} RAW{get_spacing(LogLevel.RAW)}", line]
