import requests
from pathlib import Path
from .bedrock_download_link_fetcher import get_bedrock_update_info
import shutil
import zipfile
import sys


TEMPORARY_BEDROCK = ".tmp_bedrock_server"
ZIP_NAME = "server.zip"
DOWNLOAD_CONNECT_TIMEOUT_SECONDS = 10
DOWNLOAD_READ_TIMEOUT_SECONDS = 300
DOWNLOAD_CHUNK_SIZE = 1024 * 1024 # 1 MB (in binary)


def download_and_extract_bedrock(platform, server_folder):
    # Check for updates and get the download URL
    updateInfo = get_bedrock_update_info(None, platform)
    if updateInfo.error:
        raise RuntimeError(f"Update check failed; cannot proceed with update: {updateInfo.error}")
    
    # Only show the progress bar if we're running in a terminal that supports it
    show_bar = sys.stdout.isatty()

    # Download the update zip file to a temporary location with a progress bar
    try:
        temp_dir = Path(TEMPORARY_BEDROCK)
        download_path = temp_dir / ZIP_NAME
        temp_dir.mkdir(parents=True, exist_ok=True)
        headers = {
            "User-Agent": "BedrockUpdater",
            "Accept": "*/*",
            "Accept-Encoding": "identity",  # Disable compression so Content-Length is accurate
        }
        with requests.get(updateInfo.download_url, headers=headers, stream=True, timeout=(DOWNLOAD_CONNECT_TIMEOUT_SECONDS, DOWNLOAD_READ_TIMEOUT_SECONDS)) as resp:
            resp.raise_for_status()
            with open(download_path, "wb") as f:
                total = int(resp.headers.get('Content-Length', 0))
                downloaded = 0
                show_bar = sys.stdout.isatty()
                for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            percent = downloaded * 100 // total
                            mb_down = downloaded / (1024 * 1024)
                            mb_total = total / (1024 * 1024)
                            if show_bar:
                                filled = int(40 * percent / 100)
                                bar = "#" * filled + "-" * (40 - filled)
                                sys.stdout.write(f"\r  [{bar}] {percent:5.1f}%  {mb_down:.1f}/{mb_total:.1f} MB")
                                sys.stdout.flush()
                            # Log progress every 25% if not showing the progress bar
                            elif percent // 25 > last_logged // 25:
                                print(f"Downloading: {percent}% ({mb_down:.1f}/{mb_total:.1f} MB)")
                                last_logged = percent
                if show_bar:
                    print()
    except Exception as download_error:
        # If multiple errors occur during download and cleanup, we want to report them all
        errors = [f"Failed to download update: {download_error}"]
        # Clean temp if created
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as cleanup_error:
            errors.append(f"Failed to clean up temporary files ({temp_dir}): {cleanup_error}")
        raise RuntimeError("\n".join(errors))

    # If multiple errors occur during extraction and cleanup, we want to report them all
    errors = []

    # Extract the downloaded files to the server folder with a progress bar
    try:
        server_dir = Path(server_folder)
        with zipfile.ZipFile(download_path, 'r') as zf:
            files = zf.infolist()
            for i, file in enumerate(files):
                zf.extract(file, server_dir)
                percent = (i + 1) * 100 // len(files)
                if show_bar:
                    filled = int(40 * percent / 100)
                    bar = "#" * filled + "-" * (40 - filled)
                    sys.stdout.write(f"\r  [{bar}] {percent:5.1f}%  {i + 1}/{len(files)} files")
                    sys.stdout.flush()
                # Log progress every 25% if not showing the progress bar
                elif percent // 25 > last_logged // 25:
                    print(f"Extracting: {percent}% ({i + 1}/{len(files)} files)")
                    last_logged = percent
        if show_bar:
            print()
    except Exception as extract_error:
        # If multiple errors occur during download and cleanup, we want to report them all
        errors.append(f"Failed to extract update files, server may be in a non-functional state: {extract_error}")

    # Clean up the downloaded zip file and temporary directory
    try:
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception as cleanup_error:
        errors.append(f"Failed to clean up temporary files ({temp_dir}): {cleanup_error}")
    
    # If there were any errors during extraction or cleanup, raise them all together
    if errors:
        raise RuntimeError("\n".join(errors))