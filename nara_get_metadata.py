#!/usr/bin/env python3

"""
nara_get_metadata.py

For each NAID specified (either by --naid <...> or via a text file --batch),
makes paginated queries to /records/search?naId_is=<NAID>, one NAID at a time.

1. For each NAID:
   a) Fetches paginated results from /records/search?naId_is=<NAID>
      (uses body.hits.total.value to determine total pages).
   b) Creates a subdirectory within --outdir, named after the NAID.
   c) Saves each page's JSON to "{NAID}-metadata-pg[page]of[totalPages]-YYYYMMdd.json"
      in that NAID subdirectory.
   d) Extracts each record's naId, title, and for each digitalObject, appends
      rows with objectUrl, objectFileSize to a CSV named
      "{NAID}-binaries-YYYYMMdd.csv" in that same subdirectory.

Requirements:
  - NARA_API_KEY in the environment (e.g. export NARA_API_KEY=...).
  - The /records/search endpoint must return JSON of the form:
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
        description=(
            "Download metadata by NAID(s). For each NAID, queries /records/search?naId_is=<NAID>, "
            "paginates all results, saves JSON pages, and extracts object info to a separate CSV "
            "under a dedicated subdirectory named after the NAID."
        )
    )
    parser.add_argument(
        "--naid",
        nargs="+",
        help="One or more NAIDs (e.g. --naid 720246 123456). Ignored if --batch is provided."
    )
    parser.add_argument(
        "--batch",
        help="Path to a text file containing a list of NAIDs, one per line, overrides --naid."
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Number of records per page (limit)."
    )
    parser.add_argument(
        "--outdir",
        default="results",
        help="Directory where each NAID subdirectory will be created."
    )
    parser.add_argument(
        "--http-debug",
        action="store_true",
        help="Enable verbose HTTP request/response logging."
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
    # Validate NARA_API_KEY
    # -------------------------------------------------------------------------
    api_key = os.getenv("NARA_API_KEY")
    if not api_key:
        log_error("NARA_API_KEY environment variable is not set.")
        sys.exit(1)

    print(f"[*] Using NARA_API_KEY={api_key}")
    session = requests.Session()
    session.headers.update({"X-Api-Key": api_key})

    # Create the main output directory if it doesn't exist
    os.makedirs(args.outdir, exist_ok=True)

    # -------------------------------------------------------------------------
    # Gather NAIDs from --batch or --naid
    # -------------------------------------------------------------------------
    naid_list = []
    if args.batch:
        # read from file
        if not os.path.isfile(args.batch):
            log_error(f"Batch file does not exist: {args.batch}")
            sys.exit(1)
        with open(args.batch, "r", encoding="utf-8") as fbatch:
            for line in fbatch:
                line = line.strip()
                if line:
                    naid_list.append(line)
        print(f"[*] Loaded {len(naid_list)} NAIDs from batch file: {args.batch}")
    else:
        # fallback to --naid
        if not args.naid:
            parser.error("You must provide either --naid or --batch.")
        naid_list = args.naid

    limit = args.limit
    now_str = datetime.datetime.now().strftime("%Y%m%d")

    # -------------------------------------------------------------------------
    # For each NAID, do the entire pagination, saving JSON pages & writing CSV
    # -------------------------------------------------------------------------
    search_url = f"{API_BASE_URL}/records/search"

    for naid in naid_list:
        print("=" * 60)
        print(f"[*] Processing NAID: {naid}")

        # Make a subdirectory under the main outdir
        naid_dir = os.path.join(args.outdir, naid)
        os.makedirs(naid_dir, exist_ok=True)

        # Step 1: Retrieve first page for this NAID
        page = 1
        params_first_page = [
            ("naId_is", naid),
            ("limit", limit),
            ("page", page),
        ]

        try:
            resp = session.get(search_url, params=params_first_page)
            resp.raise_for_status()
            data = safe_json_parse(resp)
        except Exception as e:
            log_error(f"Failed to retrieve page=1 for naId_is={naid}: {e}")
            continue  # proceed to the next NAID

        body = data.get("body", {})
        hits_section = body.get("hits", {})
        total_info = hits_section.get("total", {})
        total_records = total_info.get("value", 0)

        if total_records == 0:
            print(f"[!] No records found (total=0) for naId_is={naid}. Skipping.")
            continue

        first_page_hits = hits_section.get("hits", [])
        total_pages = math.ceil(total_records / limit)

        # Save page 1 JSON inside that NAID subdir
        page1_filename = f"{naid}-metadata-pg{page}of{total_pages}-{now_str}.json"
        page1_path = os.path.join(naid_dir, page1_filename)
        with open(page1_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[+] Saved page=1 JSON -> {page1_path}")

        all_hits = list(first_page_hits)

        print(f"[*] total_records={total_records}, total_pages={total_pages}")

        # Step 2: Retrieve subsequent pages
        for pg in range(2, total_pages + 1):
            print(f"[*] Fetching page={pg} of {total_pages} for naId_is={naid}...")

            params_this_page = [
                ("naId_is", naid),
                ("limit", limit),
                ("page", pg),
            ]

            try:
                resp_pg = session.get(search_url, params=params_this_page)
                resp_pg.raise_for_status()
                data_pg = safe_json_parse(resp_pg)
            except Exception as e:
                log_error(f"Failed to retrieve page={pg} for naId_is={naid}: {e}")
                break

            # Save the JSON
            page_filename = f"{naid}-metadata-pg{pg}of{total_pages}-{now_str}.json"
            page_filepath = os.path.join(naid_dir, page_filename)
            with open(page_filepath, "w", encoding="utf-8") as f:
                json.dump(data_pg, f, indent=2)
            print(f"[+] Saved page={pg} JSON -> {page_filepath}")

            body_pg = data_pg.get("body", {})
            hits_pg_section = body_pg.get("hits", {})
            hits_pg = hits_pg_section.get("hits", [])
            all_hits.extend(hits_pg)

        print(f"[+] Retrieved total of {len(all_hits)} hits for NAID={naid}.\n")

        # Step 3: Extract fields from each hit
        extracted_rows = []
        for hit in all_hits:
            _source = hit.get("_source", {})
            record = _source.get("record", {})

            rec_naid = record.get("naId")
            title = record.get("title", "")

            digital_objects = record.get("digitalObjects", [])
            for dobj in digital_objects:
                row = {
                    "naId": rec_naid,
                    "title": title,
                    "objectUrl": dobj.get("objectUrl"),
                    "objectFileSize": dobj.get("objectFileSize")
                }
                extracted_rows.append(row)

        # Step 4: Write extracted fields to a CSV for this NAID
        csv_filename = f"{naid}-binaries-{now_str}.csv"
        csv_path = os.path.join(naid_dir, csv_filename)

        with open(csv_path, "w", encoding="utf-8", newline="") as csvfile:
            fieldnames = ["naId", "title", "objectUrl", "objectFileSize"]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(extracted_rows)

        print(f"[+] Wrote {len(extracted_rows)} lines to CSV -> {csv_path}")
        print("[DONE]\n")


if __name__ == "__main__":
    main()
