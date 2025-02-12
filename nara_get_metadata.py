#!/usr/bin/env python3

"""
nara_download_by_parentNaId.py

1. Fetches paginated results from /records/parentNaId/{parentNaId} (using body.hits.total.value).
2. Saves each page's JSON to "[parentNaId]-pg[page]of[totalPages]-YYYYMMdd.json".
3. Extracts each record's naId, title, and for each item in record.digitalObjects,
   includes a line with objectUrl, objectFileSize.

Writes these fields to CSV:
  naId,title,objectUrl,objectFileSize

Requires:
  - NARA_API_KEY in the environment (e.g. export NARA_API_KEY=...).
  - The endpoint must return JSON of the form:
      {
        "body": {
          "hits": {
            "total": { "value": <int> },
            "hits": [
              {
                "_source": {
                  "record": {
                    "naId": ...,
                    "title": ...,
                    "digitalObjects": [
                      {
                        "objectUrl": "...",
                        "objectFileSize": <int>,
                        ...
                      },
                      ...
                    ]
                  }
                }
              },
              ...
            ]
          }
        }
      }
"""

import os
import sys
import math
import json
import csv
import argparse
import datetime
import requests
import http.client
import logging
from requests.exceptions import JSONDecodeError

API_BASE_URL = "https://catalog.archives.gov/api/v2"


def log_error(message):
    """
    Print error messages with a consistent prefix and timestamp to stderr.
    """
    import sys
    stamp = datetime.datetime.now().isoformat()
    print(f"[ERROR] [{stamp}] {message}", file=sys.stderr)


def safe_json_parse(response):
    """
    Attempt to parse the response as JSON. If it fails, print the raw text
    and re-raise the exception.
    """
    try:
        return response.json()
    except JSONDecodeError:
        print("[!] Non-JSON response received:")
        print(f"Status Code: {response.status_code}")
        print("Response Text:")
        print(response.text)
        raise


def main():
    parser = argparse.ArgumentParser(
        description="Download full pages from /records/parentNaId/{parentNaId} and extract record data."
    )
    parser.add_argument(
        "--parent-naid",
        required=True,
        help="The parentNaId to query, e.g. 720246"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Number of records per page (limit)"
    )
    parser.add_argument(
        "--outdir",
        default="results",
        help="Directory where JSON pages and CSV output will be saved"
    )
    parser.add_argument(
        "--http-debug",
        action="store_true",
        help="Enable verbose HTTP request/response logging"
    )
    args = parser.parse_args()

    # -------------------------------------------------------------------------
    # Optional HTTP debug
    # -------------------------------------------------------------------------
    if args.http_debug:
        http.client.HTTPConnection.debuglevel = 1
        logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
        requests_log = logging.getLogger("requests.packages.urllib3")
        requests_log.setLevel(logging.DEBUG)
        requests_log.propagate = True
        logging.getLogger("http.client").setLevel(logging.DEBUG)
        print("[DEBUG] HTTP debug mode enabled.\n")

    # -------------------------------------------------------------------------
    # Validate environment & create session
    # -------------------------------------------------------------------------
    api_key = os.getenv("NARA_API_KEY")
    if not api_key:
        log_error("NARA_API_KEY environment variable is not set.")
        sys.exit(1)

    print(f"[*] Using NARA_API_KEY={api_key}")
    session = requests.Session()
    session.headers.update({"X-Api-Key": api_key})

    # Create output directory
    os.makedirs(args.outdir, exist_ok=True)

    # -------------------------------------------------------------------------
    # Step 1: Get first page, read total from body.hits.total.value
    # -------------------------------------------------------------------------
    parent_naid = args.parent_naid
    limit = args.limit
    page = 1

    print(f"[*] Fetching first page for parentNaId={parent_naid}, limit={limit}")
    url = f"{API_BASE_URL}/records/parentNaId/{parent_naid}"
    params = {"page": page, "limit": limit}

    try:
        resp = session.get(url, params=params)
        resp.raise_for_status()
        data = safe_json_parse(resp)
    except Exception as e:
        log_error(f"Failed to retrieve page=1 for parentNaId={parent_naid}: {e}")
        sys.exit(1)

    body = data.get("body", {})
    hits_section = body.get("hits", {})
    total_info = hits_section.get("total", {})
    total_records = total_info.get("value", 0)

    if total_records == 0:
        print("[!] No records found (total=0). Exiting.")
        sys.exit(0)

    first_page_hits = hits_section.get("hits", [])
    total_pages = math.ceil(total_records / limit)
    now_str = datetime.datetime.now().strftime("%Y%m%d")

    # Save page 1 JSON
    page1_filename = f"{parent_naid}-metadata-pg{page}of{total_pages}-{now_str}.json"
    page1_path = os.path.join(args.outdir, page1_filename)
    with open(page1_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    print(f"[+] Saved page=1 JSON -> {page1_path}")

    all_hits = []
    all_hits.extend(first_page_hits)

    print(f"[*] total_records={total_records}, so total_pages={total_pages}.")

    # -------------------------------------------------------------------------
    # Step 2: Retrieve subsequent pages 2..total_pages
    # -------------------------------------------------------------------------
    for pg in range(2, total_pages + 1):
        print(f"[*] Fetching page={pg} of {total_pages} ...")

        try:
            resp_pg = session.get(url, params={"page": pg, "limit": limit})
            resp_pg.raise_for_status()
            data_pg = safe_json_parse(resp_pg)
        except Exception as e:
            log_error(f"Failed to retrieve page={pg} for parentNaId={parent_naid}: {e}")
            break

        # Save the JSON
        filename = f"{parent_naid}-metadata-pg{pg}of{total_pages}-{now_str}.json"
        filepath = os.path.join(args.outdir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data_pg, f, indent=2)
        print(f"[+] Saved page={pg} JSON -> {filepath}")

        body_pg = data_pg.get("body", {})
        hits_pg_section = body_pg.get("hits", {})
        hits_pg = hits_pg_section.get("hits", [])
        all_hits.extend(hits_pg)

    print(f"[+] Retrieved total of {len(all_hits)} hits across {total_pages} pages.\n")

    # -------------------------------------------------------------------------
    # Step 3: For each hit, extract "naId", "title", and each digitalObjects item
    #         "objectUrl", "objectFileSize"
    # -------------------------------------------------------------------------
    # We'll store rows like:
    #   naId, title, objectUrl, objectFileSize
    extracted_rows = []

    for hit in all_hits:
        src = hit.get("_source", {})
        record = src.get("record", {})

        naId = record.get("naId")
        title = record.get("title", "")

        # digitalObjects is presumably an array. If missing or empty -> no rows
        digital_objects = record.get("digitalObjects", [])
        for dobj in digital_objects:
            row = {
                "naId": naId,
                "title": title,
                # The script specifically wants to extract:
                "objectUrl": dobj.get("objectUrl"),
                "objectFileSize": dobj.get("objectFileSize")
            }
            extracted_rows.append(row)

    # -------------------------------------------------------------------------
    # Step 4: Write these extracted fields to CSV
    # -------------------------------------------------------------------------
    csv_filename = f"{parent_naid}-binaries-{now_str}.csv"
    csv_path = os.path.join(args.outdir, csv_filename)

    with open(csv_path, "w", encoding="utf-8", newline="") as csvfile:
        fieldnames = ["naId", "title", "objectUrl", "objectFileSize"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in extracted_rows:
            writer.writerow(row)

    print(f"[+] Wrote {len(extracted_rows)} lines to CSV -> {csv_path}")
    print("[DONE]")


if __name__ == "__main__":
    main()

