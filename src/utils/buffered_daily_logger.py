import os
import datetime
import threading
import time


# Buffer size between flushes
BUFFER_SIZE = 20
# Seconds between flushes
FLUSH_INTERVAL = 10


class BufferedDailyLogger:
    """A custom logger class for use in the server manager"""
    def __init__(self, log_dir, on_error=None):
        """
        Buffered logger that changes the log file daily
        Args:
            log_dir (str): The path to the log directory
            on_error (callable, optional): A function to call when an error occurs during logging. It should accept a single argument, which is the error message. Defaults to None.
        """
        self.log_dir = log_dir
        self.on_error = on_error
        self.buffer = []
        # Mutex
        self.lock = threading.Lock()
        self.current_date = datetime.date.today()
        self.log_file_path = self._get_log_file_path(self.current_date)
        self.running = True

        # We want to start the background thread responsible for flushing the buffer to the file
        self._wait_event = threading.Event()
        self._flush_thread = threading.Thread(target=self._periodic_flush, daemon=True)
        self._flush_thread.start()

    def _get_log_file_path(self, date):
        """Join the log directory with the name of the log file"""
        return os.path.join(self.log_dir, f"log_{date.isoformat()}.txt")
    
    def log(self, message):
        """Log the message into the buffer and write to the log file if the buffer is full"""
        if self.running:
            # Lock the critical section of log()
            with self.lock:
                self.buffer.append(message)
                # Flush if the buffer size is exceeded
                if len(self.buffer) >= BUFFER_SIZE:
                    self._flush_buffer()
        else:
            raise RuntimeError("Logger not running")
    
    def _flush_buffer(self):
        """Flush the buffer into the file, change the file if the date has changed"""
        # If the buffer is empty, just return
        if not self.buffer:
            return
        # Rotate the log file if the day has changed
        today = datetime.date.today()
        if self.current_date != today:
            self.current_date = today
            self.log_file_path = self._get_log_file_path(today)
        try:
            # Append the entire buffer to the file
            with open(self.log_file_path, "a", encoding="utf-8") as f:
                f.write("\n".join(self.buffer) + "\n")
            # Clear the buffer
            self.buffer.clear()
        except Exception as e:
            # Call the error callback if it exists
            if self.on_error:
                self.on_error(str(e))
            # This is a last resort, drop logs to prevent the buffer from growing indefinitely
            if len(self.buffer) > BUFFER_SIZE * 10:
                self.buffer.clear()

        
    def _periodic_flush(self):
        """Function that runs on a separate thread to periodically flush the """
        while self.running:
            self._wait_event.wait(FLUSH_INTERVAL)
            with self.lock:
                self._flush_buffer()

    def stop(self):
        """Stop the logger and flushes the current buffer"""
        self.running = False
        # Wake up the thread if it is sleeping
        self._wait_event.set()
        self._flush_thread.join()
        with self.lock:
            self._flush_buffer()
