from enum import Enum


class Broadcaster:
    """Class to broadcast server output to multiple subscribers."""
    def __init__(self):
        """Initialize the Broadcaster with an empty list of subscribers."""
        self.subscribers = []

    class Priority(Enum):
        """Priority levels for subscribers."""
        HIGH = 1
        MEDIUM = 2
        LOW = 3

    def subscribe(self, callback, priority = Priority.MEDIUM):
        """
        Register a new subscriber to be called upon.
        Args:
            callback (func): Function to add to the subscribe list.
        """
        self.subscribers.append(callback)
        # Sort subscribers based on priority
        self.subscribers.sort(key=lambda x: priority.value)

    def unsubscribe(self, callback):
        """
        Remove a subscriber from the subscriber list.
        Args:
            callback (func): Function to remove from the subscribe list.
        """
        self.subscribers.remove(callback)

class LineBroadcaster(Broadcaster):
    def publish(self, timestamp, line):
        """
        Send a line of output to all registered subscribers using their callback function.
        Args:
            line (str): Line to send to all subscribers
        """
        for callback in self.subscribers:
            callback(timestamp, line)

class SignalBroadcaster(Broadcaster):
    def publish(self):
        """Send an alert to all registered subscribers using their callback function."""
        for callback in self.subscribers:
            callback()
