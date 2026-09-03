import datetime
import sys


def backup_error_log(message):
    """
    Used as a last resort to log errors to a file if unable to use the BufferedDailyLogger to 
    """
    try:
        with open(f"error_log_{datetime.datetime.now().strftime('%Y-%m-%d')}.txt", "a", encoding="utf-8") as f:
            f.write(f"{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} CRITICAL {message}\n")
    except Exception as e:
        print(f"Failed to write a backup error log: {e}. Original message: {message}", file=sys.stderr)
