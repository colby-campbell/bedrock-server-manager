# System Architecture

## Overview
This project consists of four main packages: `core`, `bot`, `cli`, and `utils`, each encapsulating a distinct part of the system's functionality.

## Package Responsibilities
- **core**: Contains the server process management (`server_runner`), configuration (`server_config`), and automation (`server_automation`).
- **bot**: Manages the Discord bot integration allowing remote server control and notifications.
- **cli**: Provides a command-line interface subscribing to server output for local user interaction.
- **utils**: Helper modules including logging, output formatting, broadcasting, and Windows Job Object management.

## Dependency Chain (bottom to top)
```
ServerConfig (reads settings.toml)
    ↓
ServerRunner (manages server process)
    ↓
ServerAutomation (scheduled tasks, crash detection, logging)
    ↓
DiscordBot (Discord interface)
    ↓
CommandLineInterface (CLI with prompt_toolkit)
```

## Communication Patterns
The project uses a publish-subscribe model via two broadcaster classes in `utils`:

- **`LineBroadcaster`** — publishes a 4-tuple `(level: LogLevel, timestamp: str, message: str, line: str)` to all subscribers. Used for server stdout, unexpected shutdown events, and automation output.

All subscriber callbacks must match the signature of the broadcaster they subscribe to. Thread safety is ensured by copying the subscriber list under a lock before iterating, so subscribe/unsubscribe calls during publish do not cause issues.

## Output Flow
1. `server_runner._read_stdout` reads lines from the server process stdout.
2. Each line is passed through `process_line()` which returns a `(LogLevel, timestamp, message, full_line)` 4-tuple.
3. The 4-tuple is published via `runner.stdout_broadcaster`.
4. `server_automation.handle_server_output` receives it, logs the full line to `BufferedDailyLogger`, and scrapes the message for the server version string.
5. `cli` and `discord_bot` subscribe to `automation.automation_output_broadcaster` for automation-generated messages (backups, restarts, etc.) and to `runner.stdout_broadcaster` for raw server output.

Custom messages (not from server stdout) are generated with `custom_line(level, message)` which returns the same 4-tuple format, keeping all subscribers consistent.

## LogLevel Enum
`LogLevel` is a multi-value enum defined in `format_helper.py`:
```python
class LogLevel(enum.Enum):
    INFO     = ("INFO",     "\033[34m")
    DEBUG    = ("DEBUG",    "\033[36m")
    WARN     = ("WARN",     "\033[33m")
    ERROR    = ("ERROR",    "\033[31m")
    CRITICAL = ("CRITICAL", "\033[1;31m")
    RAW      = ("RAW",      "\033[32m")  # Unformatted server lines
    CLI      = ("CLI",      "\033[35m")  # CLI-generated messages
    UNKNOWN  = ("UNKNOWN",  "\033[1;33m") # Unrecognised log level from server
```
Each member exposes `level.label` (the string name) and `level.ansi_code` (the ANSI escape code for colour). `level.value` returns the raw tuple and should not be used for display.

`RAW` is assigned to server lines that do not match the Bedrock log format `[timestamp LEVEL] message`. `UNKNOWN` is assigned when the level string in a matched line does not correspond to a known `LogLevel` member.

## Logging
`BufferedDailyLogger` in `utils` buffers log lines in memory and flushes them to a daily rotating log file. It accepts an `on_error` callback which is invoked if a flush fails (e.g. encoding error, disk full), allowing the error to be surfaced through the broadcaster without creating a dependency loop. Log files are written as UTF-8.

Debug-level messages from automation are filtered by the `automation_debug` config flag inside `log_print()` before reaching the logger or broadcaster.

## Thread Safety
`ServerRunner` uses `threading.RLock()` for all access to the server process. The re-entrant lock allows `stop()` to call `send_command()` without deadlocking. The lock is also exposed via a `lock()` context manager, allowing `ServerAutomation` to perform multi-step atomic operations (e.g. stop → backup → update → start) without race conditions.

`LineBroadcaster` use its own `threading.Lock()` to protect the subscriber list, separate from the runner lock.

## Crash Detection and Auto-Restart
`ServerRunner` publishes to `unexpected_shutdown_broadcaster` when the server process exits without `stop()` being called first. `ServerAutomation.handle_unexpected_shutdown` receives this signal, records the crash timestamp, and automatically restarts the server unless the number of crashes within `CRASH_DETECTION_WINDOW_MINUTES` minutes exceeds `crash_limit` from config.

## Scheduled Restart
`ServerAutomation._scheduled_restart` runs on a daemon thread. Each cycle it calculates the seconds until the configured daily restart time, sleeps, warns players in-game, then stops the server, performs an offline world backup, optionally runs an update check, and restarts.

## Online World Backup
Online backups use the Bedrock `save hold` / `save query` / `save resume` sequence. During a backup, `_backup_world_online` subscribes a temporary `queue.Queue` callback to `stdout_broadcaster` to capture the server's responses to these commands. The subscription is always removed in a `try/finally` block to prevent leaking subscribers if an error occurs mid-backup.

## Windows Process Lifecycle
On Windows, `ServerRunner` assigns the `bedrock_server.exe` process to a Windows Job Object with `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`. This ensures the server process is terminated if the manager exits unexpectedly (e.g. killed via Task Manager), preventing orphaned server processes. The Job Object handle is kept alive in `self._job` and closed during `stop()`. Implementation is in `utils/windows_job.py` using `ctypes`.

On Linux, `prctl(PR_SET_PDEATHSIG, SIGTERM)` is set as a `preexec_fn` so the server receives SIGTERM if the manager process dies.

## Checking for Bedrock Server Updates
The `bedrock_download_link_fetcher` module in `utils` fetches the latest Bedrock server version and download URL from the official Minecraft API. The API format as of 2026-05-04:
```json
{
    "result": {
        "links": [
            { "downloadType": "serverBedrockWindows", "downloadUrl": "https://..." },
            { "downloadType": "serverBedrockLinux",   "downloadUrl": "https://..." }
        ]
    }
}
```
Constants are defined for all key strings and expected `downloadType` values. If Mojang changes the API structure, only `bedrock_download_link_fetcher` needs to be updated.
