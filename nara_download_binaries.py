#!/usr/bin/env python3
"""
nara_download_binaries.py

Reads a CSV (from nara_download_by_parentNaId.py) containing columns:
  naId,title,objectUrl,objectFileSize

Does the following:
  1) Reports total number of items and total file size in human-readable format.
  2) Creates a subdirectory under the user-specified download_path (defaults to ./downloads)
     named YYYYMMdd-N, where N increments if the directory already exists.
  3) Logs start time. Then, for each item, attempts to download the file into
     that subdirectory, logging:
       - item # out of total
       - the URL or filename
       - a progress bar for the download
  4) Logs end time, total elapsed time, # of downloads attempted, # of successes.
  5) If --test is provided, it performs steps 1 & 2 but does NOT download any files
     (just logs that it would have done so).

Usage:
  python nara_download_binaries.py --csv <path_to_csv> [--test]
  python nara_download_binaries.py --csv <path_to_csv> --download_path ./my_downloads
"""

import os
import sys
import csv
import argparse
import datetime
import requests
import logging
import math
from urllib.parse import urlsplit

# Optional: for nice debug output of requests. Not strictly needed here, but
# included for completeness if you want --http-debug in future.
import http.client

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def log(msg):
    """Print a regular log message to stdout."""
    print(msg)

def log_error(msg):
    """Print an error message to stderr with timestamp."""
    stamp = datetime.datetime.now().isoformat()
    print(f"[ERROR] [{stamp}] {msg}", file=sys.stderr)

def human_readable_size(num_bytes):
    """
    Convert an integer (bytes) to a human-readable string like '1.2K', '3.4M', etc.,
    akin to POSIX 'ls -lh' output.
    """
    if num_bytes < 1024:
        return f"{num_bytes}B"
    units = ["K","M","G","T","P","E","Z","Y"]
    size = float(num_bytes)
    idx = -1
    while size >= 1024 and idx < len(units):
        size /= 1024.0
        idx += 1
    return f"{size:.1f}{units[idx]}"

def find_download_subdir(base_download_path):
    """
    Creates/Finds a subdirectory named YYYYMMdd-N inside `base_download_path`,
    where N increments if the directory already exists.
    Returns the path to that subdirectory.
    Example: "<base_download_path>/20240203-1"
    """
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    # We'll try increments from 1 upwards
    i = 1
    while True:
        subdir_name = f"{today_str}-{i}"
        path = os.path.join(base_download_path, subdir_name)
        if not os.path.exists(path):
            # create it
            os.makedirs(path, exist_ok=True)
            return path
        i += 1

def download_with_progress(session, url, dest_path):
    """
    Downloads the file at `url` to `dest_path`, printing a progress bar.
    Returns True on success, False on failure.
    """
    try:
        with session.get(url, stream=True) as r:
            r.raise_for_status()

            # Attempt to get total file size from Content-Length header if present
            total_size = r.headers.get("Content-Length")
            total_bytes = int(total_size) if total_size else None

            downloaded_bytes = 0
            chunk_size = 8192

            # We open the file for write
            with open(dest_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=chunk_size):
                    if not chunk:
                        continue
                    f.write(chunk)
                    downloaded_bytes += len(chunk)
                    # Print progress bar
                    show_progress(downloaded_bytes, total_bytes)
            # Once done, ensure final line break
            print()  # to move to the next line
        return True
    except Exception as e:
        log_error(f"Download error for {url}: {e}")
        return False

def show_progress(downloaded, total):
    """
    Print a single-line progress bar (rsync-style).
    For example: "  45%  45.3M/100.0M"
    If total is None, just show downloaded in KB/MB/...
    """
    if total is not None and total > 0:
        fraction = downloaded / total
        percent = fraction * 100
        # Convert to a bar of length 30 (example)
        bar_len = 30
        filled = int(bar_len * fraction)
        bar = "=" * filled + "-" * (bar_len - filled)
        # Format size
        downloaded_hr = human_readable_size(downloaded)
        total_hr = human_readable_size(total)
        # Example line: "[====------] 14%  17.3M/120.0M"
        print(f"\r[{bar}] {percent:3.0f}%  {downloaded_hr}/{total_hr}", end="", flush=True)
    else:
        # unknown total
        downloaded_hr = human_readable_size(downloaded)
        print(f"\rDownloaded {downloaded_hr}", end="", flush=True)

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Download binaries from a CSV of objectUrl, objectFileSize, etc.")
    parser.add_argument("--csv", required=True,
                        help="Path to the CSV file containing columns: naId,title,objectUrl,objectFileSize")
    parser.add_argument("--download_path", default="./downloads",
                        help="Relative path where date-based subdirectories will be created. Default=./downloads")
    parser.add_argument("--test", action="store_true", help="Report stats but do not download.")
    args = parser.parse_args()

    # 1) Parse the CSV
    rows = []
    total_file_size = 0
    try:
        with open(args.csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Expect keys: naId, title, objectUrl, objectFileSize
                # objectFileSize can be blank or missing
                file_size_str = row.get("objectFileSize") or "0"
                file_size = 0
                try:
                    file_size = int(file_size_str)
                except:
                    pass
                rows.append({
                    "naId": row.get("naId"),
                    "title": row.get("title"),
                    "objectUrl": row.get("objectUrl"),
                    "objectFileSize": file_size
                })
                total_file_size += file_size
    except Exception as e:
        log_error(f"Error reading CSV: {e}")
        sys.exit(1)

    num_items = len(rows)
    hr_size = human_readable_size(total_file_size)
    log(f"Found {num_items} total binaries in CSV.")
    log(f"Sum of file sizes: {hr_size}")

    if num_items == 0:
        log("No items to process. Exiting.")
        sys.exit(0)

    # If test mode, just exit after printing stats
    if args.test:
        log("[TEST MODE] No downloads will be performed.")
        sys.exit(0)

    # 2) Make the subdirectory inside the specified download_path
    base_download_path = args.download_path
    target_subdir = find_download_subdir(base_download_path)
    log(f"Downloading to subdirectory: {target_subdir}")

    # 3) Announce start time
    start_time = datetime.datetime.now()
    log(f"Starting download at {start_time.strftime('%Y-%m-%d %H:%M:%S')}...")

    # 4) Download each item
    session = requests.Session()

    downloads_attempted = 0
    downloads_successful = 0
    total_to_download = num_items

    for i, item in enumerate(rows, start=1):
        url = item["objectUrl"]
        if not url:
            log_error(f"Item {i} has no objectUrl, skipping.")
            continue

        # Figure out a filename from the URL
        filename = os.path.basename(urlsplit(url).path)
        if not filename:
            filename = f"file_{i}"
        filename = f"{item["naId"]}_{filename}"

        dest_path = os.path.join(target_subdir, filename)

        items_left = total_to_download - i
        log(f"\n{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')} [{i}/{total_to_download}] Downloading: {filename}  (remaining: {items_left})")
        downloads_attempted += 1

        success = download_with_progress(session, url, dest_path)
        if success:
            downloads_successful += 1

    # 5) End time, summary
    end_time = datetime.datetime.now()
    elapsed = end_time - start_time

    log("\n===== DOWNLOAD SUMMARY =====")
    log(f"End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    log(f"Total time elapsed: {elapsed}")
    log(f"Downloads attempted: {downloads_attempted}")
    log(f"Downloads successful: {downloads_successful}")


if __name__ == "__main__":
    main()

