import threading
import queue
from .format_helper import LogLevel


class LineBroadcaster:
    """Class to broadcast server output lines to multiple subscribers via a background dispatch thread."""
    def __init__(self, on_error = None):
        """
        Initialize the LineBroadcaster with an empty list of subscribers and start its background dispatch thread.
        Args:
            on_error (callable, optional): A function to call when an error occurs during logging. It should accept a single argument, which is the error message. Defaults to None.
        """
        self.on_error = on_error
        self.subscribers = []
        self._lock = threading.Lock()
        self._queue = queue.Queue()
        self._dispatch_thread = threading.Thread(target=self._dispatch_loop, daemon=True)
        self._dispatch_thread.start()

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

    def publish(self, level: LogLevel, timestamp: str, message: str, line: str):
        """
        Send the level, timestamp, message, and complete line of output to all registered subscribers using their callback function.
        Args:
            level (LogLevel): The log level.
            timestamp (str): The timestamp.
            message (str): The message.
            line (str): The complete formatted line.
        """
        self._queue.put((level, timestamp, message, line))

    def flush(self):
        """Block until every message enqueued so far has been dispatched to all subscribers."""
        done = threading.Event()
        self._queue.put(done)
        done.wait()

    def _dispatch_loop(self):
        """
        Send messages from the queue to all subscribers, running on a separate thread to avoid blocking the main thread
        and act as an isolation layer between the broadcaster and the subscribers.
        """
        while True:
            item = self._queue.get()
            # If the item is a threading.Event, it is a signal that the queue has been flushed, so we unblock the flush() thread
            if isinstance(item, threading.Event):
                item.set()
                continue
            level, timestamp, message, line = item
            # Create a shallow copy of the subscriber list to avoid issues if subscribers are added or removed during iteration
            with self._lock:
                callbacks = self.subscribers.copy()
            for callback in callbacks:
                try:
                    callback(level, timestamp, message, line)
                except Exception as e:
                    # A subscriber failing cannot affect the broadcaster or other subscribers, so we catch and log the exception
                    if self.on_error:
                        self.on_error(f"Error in subscriber callback {callback}: {str(e)}")
