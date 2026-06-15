import logging
from .format_helper import process_line, LogLevel


# This could be moved to bot as it is only used there; however, I will leave it here for now.
class BroadcastHandler(logging.Handler):
    """Custom logging handler that broadcasts log messages to an OutputBroadcaster."""
    def __init__(self, broadcaster, logger):
        super().__init__()
        self.broadcaster = broadcaster
        self.logger = logger

    def emit(self, record):
        """Emit a log record by publishing it to the broadcaster."""
        msg = self.format(record)
        level, timestamp, message, line = process_line(msg)
        # Send the timestamp and the text to the CLI
        self.broadcaster.publish(level, timestamp, message, line)
        # Just combine the timestamp and the text and send it to the logger
        self.logger.log(line)
