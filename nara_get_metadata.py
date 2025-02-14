#!/usr/bin/env python3

"""
nara_get_metadata.py

1. Fetches paginated results from /records/search (using body.hits.total.value).
   - Accepts one or more NAIDs via --naid, e.g. --naid 720246 123456
     OR via a file specified by --batch, containing one NAID per line.
   - Passes them as repeated naId=... query parameters to the /records/search endpoint
     (actually uses a comma-separated string of NAIDs).
2. Saves each page's JSON to "searchNaid-metadata-pg[page]of[totalPages]-YYYYMMdd.json".
3. Extracts each record's naId, title, and for each item in record.digitalObjects,
   includes a line with objectUrl, objectFileSize.

Writes these fields to CSV:
  naId,title,objectUrl,objectFileSize

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
    """
    Print error messages with a consistent prefix and timestamp to stderr.
    """
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
            "Download full pages from /records/search, specifying one or more "
            "naId values. You can pass them via --naid or via a text file with "
            "--batch (one NAID per line)."
        )
    )
    parser.add_argument(
        "--naid",
        nargs="+",
        help=(
            "One or more NAIDs (e.g. --naid 720246 123456). "
            "Ignored if --batch is provided."
        )
    )
    parser.add_argument(
        "--batch",
        help=(
            "Path to a text file containing a list of NAIDs, "
            "one per line. Overrides --naid."
        )
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
        help="Directory where JSON pages and CSV output will be saved."
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
    # Determine NAIDs to query
    #   1) If --batch provided, read from file
    #   2) Else, use --naid
    #   3) If neither, error
    # -------------------------------------------------------------------------
    naid_list = []
    if args.batch:
        # read lines from text file, one per line
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

    # We'll pass the entire list as a single comma-separated value to 'naId' param.
    naid_param = ",".join(naid_list)
    print(f"[*] Using naId(s): {naid_list}")

    limit = args.limit
    page = 1

    # -------------------------------------------------------------------------
    # Step 1: Retrieve first page, to get totalRecords from body.hits.total.value
    # -------------------------------------------------------------------------
    # Build the query parameters for page=1
    params_first_page = [
        ("naId", naid_param),
        ("limit", limit),
        ("page", page),
    ]

    print(f"[*] Fetching first page, limit={limit}")
    search_url = f"{API_BASE_URL}/records/search"

    try:
        resp = session.get(search_url, params=params_first_page)
        resp.raise_for_status()
        data = safe_json_parse(resp)
    except Exception as e:
        log_error(f"Failed to retrieve page=1 for naId(s)={naid_list}: {e}")
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
    page1_filename = f"searchNaid-metadata-pg{page}of{total_pages}-{now_str}.json"
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

        # Build new param list for this page
        params_this_page = [
            ("naId", naid_param),
            ("limit", limit),
            ("page", pg),
        ]

        try:
            resp_pg = session.get(search_url, params=params_this_page)
            resp_pg.raise_for_status()
            data_pg = safe_json_parse(resp_pg)
        except Exception as e:
            log_error(f"Failed to retrieve page={pg} for naId(s)={naid_list}: {e}")
            break

        # Save the JSON
        filename = f"searchNaid-metadata-pg{pg}of{total_pages}-{now_str}.json"
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
    # Step 3: For each hit, extract "naId", "title", and digitalObjects:
    #   "objectUrl", "objectFileSize"
    # -------------------------------------------------------------------------
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

    # -------------------------------------------------------------------------
    # Step 4: Write these extracted fields to CSV
    # -------------------------------------------------------------------------
    csv_filename = f"searchNaid-binaries-{now_str}.csv"
    csv_path = os.path.join(args.outdir, csv_filename)

    with open(csv_path, "w", encoding="utf-8", newline="") as csvfile:
        fieldnames = ["naId", "title", "objectUrl", "objectFileSize"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(extracted_rows)

    print(f"[+] Wrote {len(extracted_rows)} lines to CSV -> {csv_path}")
    print("[DONE]")


if __name__ == "__main__":
    main()
