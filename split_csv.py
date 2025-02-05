#!/usr/bin/env python3

"""
split_csv.py

Reads a CSV file (with a header row) and splits the data rows into
N separate CSV files of roughly equal size. Each output file retains
the same header row.

Usage:
  python split_csv.py --input path/to/records.csv [--parts 5]
Output:
  records_part1.csv, records_part2.csv, ..., records_partN.csv
(or adapt naming as needed).
"""

import csv
import math
import argparse

def main():
    parser = argparse.ArgumentParser(
        description="Split an input CSV into N separate files of roughly equal size."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to the CSV file to split"
    )
    parser.add_argument(
        "--parts",
        type=int,
        default=3,
        help="Number of output CSV files to create (default=3)"
    )
    args = parser.parse_args()

    # Read all rows from the input CSV
    with open(args.input, "r", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames  # capture header columns
        rows = list(reader)            # load all rows into memory

    total_rows = len(rows)
    print(f"Total data rows found (excluding header): {total_rows}")

    if total_rows == 0:
        print("No rows to split. Exiting.")
        return

    if args.parts < 1:
        print("Number of parts must be at least 1. Exiting.")
        return

    # Compute how many rows each part should (roughly) contain
    chunk_size = math.ceil(total_rows / args.parts)

    # We will slice the rows for each part
    start_idx = 0

    for part_index in range(1, args.parts + 1):
        outfile_name = f"records_part{part_index}.csv"
        end_idx = start_idx + chunk_size

        # For the last part, ensure we go to the end of the list
        if part_index == args.parts:
            end_idx = total_rows

        chunk = rows[start_idx:end_idx]
        chunk_len = len(chunk)

        if chunk_len == 0:
            # If a chunk is empty, we can still write just the header,
            # or skip writing the file. Here, let's write an empty file with header.
            print(f"Writing empty chunk to {outfile_name}")
        else:
            print(f"Writing {chunk_len} rows to {outfile_name}")

        # Write chunk to CSV
        with open(outfile_name, "w", encoding="utf-8", newline="") as f_out:
            writer = csv.DictWriter(f_out, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(chunk)

        start_idx = end_idx

    print("Done splitting CSV into parts.")

if __name__ == "__main__":
    main()

