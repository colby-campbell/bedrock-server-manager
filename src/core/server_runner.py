import sys
from utils import LineBroadcaster, SignalBroadcaster, process_line, custom_line, LogLevel, Platform, create_job_object, close_job_object
from contextlib import contextmanager
import subprocess
import threading
import os
import ctypes
import signal
from .server_config import ServerConfig


class ServerRunner:
    def __init__(self, config : ServerConfig):
        """
        Initialize ServerRunner with a configuration object.
        Args:
            config (ServerConfig): The server configuration instance.
        """
        self.config = config
        self.server_folder = config.server_folder
        self.shutdown_timeout = config.shutdown_timeout
        self.platform = config.platform
        self.process = None
        self._warned_no_log_file = False
        self.stdout_broadcaster = LineBroadcaster()
        self.unexpected_shutdown_broadcaster = LineBroadcaster()
        self._stdout_thread = None
        self._expected_shutdown = False
        # Windows Job Object handle, keeps bedrock_server tied to this process's lifetime
        self._job = None
        # We are using a RLock instead of a regular Lock to allow nested locking within the same thread
        self._lock = threading.RLock()


    @contextmanager
    def lock(self):
        """Context manager for acquiring and releasing the lock. This allows our special lock to be used in 'with' statements."""
        # Acquire the lock for thread-safe operations
        self._lock.acquire()
        try:
            # Code in the 'with' block runs here (the critical section)
            yield
        finally:
            # Always release, even if there is an exception
            self._lock.release()


    def start(self):
        """
        Start the Minecraft Bedrock server subprocess.
        Raises:
            RuntimeError: If the server is already running.
        """
        with self._lock:
            if self.process:
                raise RuntimeError("server is already running")

            self._expected_shutdown = False

            # Grab the current environment and the working directory for the server executable
            env = os.environ.copy()
            # TODO: make better lol
            cwd = os.path.abspath(self.server_folder)

            if self.platform == Platform.Linux:
                # On Linux we have to set the correct library path environment
                env["LD_LIBRARY_PATH"] = cwd

            # Verify that the server executable exists at the expected path
            executable_path = os.path.join(cwd, "bedrock_server" if self.platform == Platform.Linux else "bedrock_server.exe")
            if not os.path.isfile(executable_path):
                raise FileNotFoundError(f"{executable_path}: server executable not found")

            # On Linux, instruct the kernel to send SIGTERM to bedrock_server if this process dies
            preexec_fn = None
            if self.platform == Platform.Linux:
                def preexec_fn():
                    # Load the C library and call prctl to set the parent death signal to SIGTERM
                    ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)

            # Start the server process
            self.process = subprocess.Popen(
                [executable_path],
                cwd=cwd,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1,
                preexec_fn=preexec_fn,
            )

            # On Windows, bind bedrock_server to a Job Object so it is killed when this process exits
            if self.platform == Platform.Windows:
                self._job = create_job_object(int(self.process._handle))

            # Start a thread to read stdout
            self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
            self._stdout_thread.start()


    def is_running(self):
        """
        Check if the server process is currently running.
        Returns:
            bool: True if running, False otherwise.
        """
        # Verify self.process exists and the process is still active (self.process.poll() returns None while running)
        with self._lock:
            return self.process and self.process.poll() is None


    def _read_stdout(self):
        """Internal method run in a separate thread to continuously read stdout lines from the server process and enqueue them for processing."""
        for line in self.process.stdout:
            # Strip the newline from the line
            line = line.rstrip()
            # Detect and strip no log file prefix (this happens when the server is running two instances on the same port)
            if line.startswith("NO LOG FILE! - ["):
                line = line[len("NO LOG FILE! - "):]
                # Only warn about the no log file issue once
                if not self._warned_no_log_file:
                    self.stdout_broadcaster.publish(
                        *custom_line(
                            LogLevel.WARN,
                            "Detected 'NO LOG FILE!' prefix in server output. This usually means another server instance is running or the log file is locked."
                            "Log output will only appear in the console and not in a file. Subsequent messages will not show this warning."
                        )
                    )
                    self._warned_no_log_file = True
            # Process the line and publish it to stdout subscribers
            self.stdout_broadcaster.publish(*process_line(line))
            # Detect if the line is a missing server.properties error
            if "Error opening file: server.properties" in line:
                self.stdout_broadcaster.publish(
                    *custom_line(
                        LogLevel.CRITICAL,
                        "The server failed to start due to a missing server.properties file."
                        "Please ensure that server.properties exists in the server folder and is properly configured."
                    )
                )
                self.send_command("")           # Since the server is looking for an input to continue, send an empty string to prevent it from hanging
                self._expected_shutdown = True  # Prevent the unexpected shutdown message since we know why it happened
        # Clean up runner state after process exits
        self.process.stdout.close()
        self.process = None
        self._stdout_thread = None
        # If the shutdown was not expected, we alert all subscribers
        if not self._expected_shutdown:
            self.unexpected_shutdown_broadcaster.publish(
                *custom_line(LogLevel.ERROR, "The server has shut down unexpectedly.")
            )
        # Clean up the
        # Windows Job Object if it exists
        if self._job is not None:
            close_job_object(self._job)
            self._job = None


    def send_command(self, command):
        """
        Send a command string to the server's stdin.
        Args:
            command (str): Command string to send to the server.
        Raises:
            RuntimeError: If the server is not currently running.
        """
        with self._lock:
            if not self.is_running():
                raise RuntimeError("Server is not running")
            # Send a command to the server's stdin and immediately flush it
            self.process.stdin.write(command + "\n")
            self.process.stdin.flush()


    def stop(self):
        """
        Gracefully stop the server by sending a stop command and waiting for the process to exit within the configured shutdown timeout. Forces kill if unable to stop gracefully.
        Raises:
            RuntimeError: If the server is not currently running.
        """
        with self._lock:
            if not self.is_running():
                raise RuntimeError("Server is not running")
            # Indicate that this was a expected shutdown
            self._expected_shutdown = True
            # Attempt to close the process properly
            self.send_command("stop")
            try:
                # Wait for the process to exit gracefully
                self.process.wait(timeout=self.shutdown_timeout)
            except subprocess.TimeoutExpired:
                # If the process does not exit in time, kill it
                self.process.kill()
                self.process.wait()
            # Clean up
            self._stdout_thread.join()
            self.process = None
            self._stdout_thread = None
            # Clean up the Windows Job Object if it exists
            if self._job is not None:
                close_job_object(self._job)
                self._job = None


    def restart(self):
        """
        Restart the server by stopping and then starting it.
        Raises:
            RuntimeError: If stopping or starting fails.
        """
        with self._lock:
            self.stop()
            self.start()
