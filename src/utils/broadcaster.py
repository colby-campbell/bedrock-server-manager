from enum import Enum
import threading


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
    def publish(self, timestamp, line):
        """
        Send a line of output to all registered subscribers using their callback function.
        Args:
            line (str): Line to send to all subscribers
        """
        # Create a shallow copy of the subscriber list so the lock can be released before calling callback functions
        with self._lock:
            callbacks = self.subscribers.copy()
        for callback in callbacks:
            callback(timestamp, line)

class SignalBroadcaster(Broadcaster):
    def publish(self):
        """Send an alert to all registered subscribers using their callback function."""
        # Create a shallow copy of the subscriber list so the lock can be released before calling callback functions
        with self._lock:
            callbacks = self.subscribers.copy()
        for callback in callbacks:
            callback()
