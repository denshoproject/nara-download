# NARA NextGen Catalog Scripts

This repository contains Python 3 scripts for interacting with the [NARA NextGen Catalog API 2.0](https://catalog.archives.gov/api/v2/api-docs/), downloading metadata and associated binaries, and splitting CSV outputs. In the NARA NextGen catalog system, every record group, series, item, and subject cataloging term has a unique identifier called an `NAID`. For our purposes, we can use one or more `NAID`s to retrieve metadata about each record, including any available digital objects. The Catalog API 2.0 returns data as JSON; see examples on the [API help page](https://www.archives.gov/research/catalog/help/api).

---

## Table of Contents

1. [Prerequisites](#prerequisites)  
2. [Scripts Overview](#scripts-overview)  
   - [nara_get_metadata.py](#1-nara_get_metadatapy)  
   - [nara_download_binaries.py](#2-nara_download_binariespy)  
   - [split_csv.py](#3-split_csvpy)  
3. [Usage Examples](#usage-examples)  
4. [License](#license)  

---

## Prerequisites

- **Python 3.7+** (or higher)  
- [Requests](https://pypi.org/project/requests/) library (usually installed via `pip install requests`).  
- A valid **NARA_API_KEY** (placed in your environment as `NARA_API_KEY=...`).  
  - See NARA’s [API help page](https://www.archives.gov/research/catalog/help/api) and [API Docs](https://catalog.archives.gov/api/v2/api-docs/) for how to obtain an API key.

Before running the scripts, confirm your environment:
```bash
export NARA_API_KEY="YOUR_VALID_API_KEY"
```

## Scripts Overview
### 1. nara_get_metadata.py

This script queries the NARA NextGen Catalog with two approaches to retrieve child digital objects for each NAID, one NAID at a time:

Primary:
Calls /records/search with ?naId_is=<NAID> to retrieve pages.
If digital objects are found in the returned data (`digitalObjects` arrays), it saves JSON pages and creates a CSV.

Fallback:
If the first approach returns no digital objects, it discards those results and calls `/records/parentNaId/<NAID>` with `?page=...&limit=...`.
If that call also has zero digital objects, it prints a warning to stdout that no child digital objects exist for the NAID, and produces no CSV or JSON output for it.

Behavior:

For each NAID:
* Attempt `GET /records/search?naId_is=<NAID>` in a paginated manner.
* If that yields zero objects, try `GET /records/parentNaId/<NAID>` in the same paginated style.
* If both yield zero, prints a warning that no digital objects are returned, and does not produce files.
* Otherwise, saves JSON pages and produces `<NAID>-binaries-YYYYMMdd.csv` in an `outdir/NAID/` subdirectory.

**Usage:**
```bash
python nara_get_metadata.py \
  --naid 720246 123456 \
  --limit 50 \
  --outdir results
```
or via a batch file:
```bash
python nara_get_metadata.py \
  --batch naids.txt \
  --limit 50 \
  --outdir results
```
    --naid: One or more NAIDs on the command line. Ignored if --batch is used.
    --batch: A text file with one NAID per line.
    --limit: Number of child records to fetch per page (default=100).
    --outdir: Directory in which each NAID subdirectory is created.
    --http-debug: Logs verbose HTTP request and response details.

**Output Layout:**
```
results/
  ├─ 720246/
  │   ├─ 720246-metadata-pg1of4-YYYYMMdd.json
  │   ├─ 720246-metadata-pg2of4-YYYYMMdd.json
  │   └─ 720246-binaries-YYYYMMdd.csv
  └─ 123456/
      ├─ 123456-parentNaId-pg1of2-YYYYMMdd.json
      └─ 123456-binaries-YYYYMMdd.csv
```
(The naming varies slightly depending on whether the fallback approach was used.)
### 2. nara_download_binaries.py

Reads a CSV (from nara_get_metadata.py) with columns:

`naId,title,objectUrl,objectFileSize`

It:
* Reports total number of items and cumulative file size (human-readable).
* Creates a date-based subdirectory (e.g., `./downloads/20250217-1`) to store downloaded files.
* Logs start time, attempts a progress bar for each file, optionally waiting a back-off time (`--backoff <ms>`) after each download.
* Logs end time, total downloads attempted, how many succeeded, and prints the CSV line numbers of any failed downloads.

**Usage:**
```bash
python nara_download_binaries.py \
  --csv results/720246/720246-binaries-YYYYMMdd.csv \
  --download_path ./downloads \
  --backoff 500

    --csv: Path to the CSV.
    --test: If present, no downloads are made; only stats are shown.
    --download_path: Base directory for date-based subfolders (default=./downloads).
    --backoff: Integer milliseconds to pause after each download (default=0).
```
### 3. split_csv.py

Takes any CSV and splits it into N parts (default=3). Each part has the same header row. 

**Usage:**
```bash
python split_csv.py --input big.csv --parts 4
```
**Produces:**
```
records_part1.csv
records_part2.csv
records_part3.csv
records_part4.csv
```
## Usage Examples

### Get Metadata
```bash
export NARA_API_KEY="YOUR_VALID_API_KEY"
python nara_get_metadata.py --naid 720246 987654 --outdir meta_out
```
If `720246` has digital objects via search, they’re saved to `meta_out/720246/`.
If `987654` does not have any objects in search, the script tries `parentNaId/987654`. If that also yields none, it logs a warning message.

### Download Binaries
```bash
python nara_download_binaries.py \
    --csv meta_out/720246/720246-binaries-YYYYMMdd.csv \
    --download_path ./downloads \
    --backoff 1000
```
Creates subfolder `./downloads/20250217-1` for the files, waiting 1 second between each download.

### Split a Large CSV
```bash
    python split_csv.py \
      --input meta_out/720246/720246-binaries-YYYYMMdd.csv \
      --parts 3
```
Produces `records_part1.csv`, `records_part2.csv`, `records_part3.csv`.

## License

This project is provided “as is” under the terms of your chosen license. Feel free to adapt and extend for your use case. We make no guarantees about data completeness, correctness, or performance.

For more details, refer to the NARA NextGen Catalog API docs and abide by any relevant usage policies.
