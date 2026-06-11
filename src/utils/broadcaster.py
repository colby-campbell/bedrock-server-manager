from enum import Enum
import threading
from .format_helper import LogLevel


class Broadcaster:
    """Class to broadcast server output to multiple subscribers."""
    def __init__(self):
        """Initialize the Broadcaster with an empty list of subscribers."""
        self.subscribers = []
        self._lock = threading.Lock()

    def subscribe(self, callback):
        """
        Register a new subscriber to be called upon.
        Args:
            callback (func): Function to add to the subscribe list.
        """
        with self._lock:
            self.subscribers.append(callback)

    def unsubscribe(self, callback):
        """
        Remove a subscriber from the subscriber list.
        Args:
            callback (func): Function to remove from the subscribe list.
        """
        with self._lock:
            self.subscribers.remove(callback)

class LineBroadcaster(Broadcaster):
    def publish(self, level: LogLevel, timestamp: str, message: str, line: str):
        """
        Send the level, timestamp, message, and complete line of output to all registered subscribers using their callback function.
        Args:
            level (LogLevel): The log level.
            timestamp (str): The timestamp.
            message (str): The message.
            line (str): The complete formatted line.
        """
        # Create a shallow copy of the subscriber list so the lock can be released before calling callback functions
        with self._lock:
            callbacks = self.subscribers.copy()
        for callback in callbacks:
            callback(level, timestamp, message, line)

class SignalBroadcaster(Broadcaster):
    def publish(self):
        """Send an alert to all registered subscribers using their callback function."""
        # Create a shallow copy of the subscriber list so the lock can be released before calling callback functions
        with self._lock:
            callbacks = self.subscribers.copy()
        for callback in callbacks:
            callback()
