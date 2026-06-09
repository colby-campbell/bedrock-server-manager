from enum import Enum


class Broadcaster:
    """Class to broadcast server output to multiple subscribers."""
    def __init__(self):
        """Initialize the Broadcaster with an empty list of subscribers."""
        self.subscribers = []

    def subscribe(self, callback):
        """
        Register a new subscriber to be called upon.
        Args:
            callback (func): Function to add to the subscribe list.
        """
        self.subscribers.append(callback)

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
