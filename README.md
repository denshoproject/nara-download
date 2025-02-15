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

Make sure your environment is set up properly before running the scripts:
```bash
export NARA_API_KEY="YOUR_VALID_API_KEY"
```

---

## Scripts Overview

### 1. `nara_get_metadata.py`

This script queries the **NARA NextGen Catalog `/records/search` endpoint** with `?naId_is=<NAID>`, making **one call per NAID**. It accepts NAIDs from either the command line (`--naid 720246 123456`) or from a text file (`--batch my_naids.txt`) containing one NAID per line.  

**What It Does**:

1. **Iterates** over each NAID specified.  
2. **Fetches** the total number of records (`body.hits.total.value`), then retrieves JSON pages for that NAID (`page=1..N`), saving them to:
   ```
   outdir/
     └─ <NAID>/
        ├─ <NAID>-metadata-pg1ofN-YYYYMMdd.json
        ├─ <NAID>-metadata-pg2ofN-YYYYMMdd.json
        ...  
   ```
3. **Extracts** each record’s `naId`, `title`, and any `digitalObjects` (with `objectUrl`, `objectFileSize`) into a CSV named:
   ```
   <NAID>-binaries-YYYYMMdd.csv
   ```
   inside that same `<NAID>/` subdirectory.

**Usage**:
```bash
python nara_get_metadata.py \
  --naid 720246 123456 \
  --limit 50 \
  --outdir metadata_results
```
or using a batch file:
```bash
python nara_get_metadata.py \
  --batch naids.txt \
  --limit 50 \
  --outdir metadata_results
```

**Key Arguments**:
- `--naid`: One or more NAIDs to query; ignored if `--batch` is set.  
- `--batch`: Path to a text file listing NAIDs (one per line).  
- `--limit`: Number of records per page (default=100).  
- `--outdir`: Directory in which each NAID gets its own subdirectory for JSON pages and CSV output (default=`results`).  
- `--http-debug`: Enables verbose HTTP logs for debugging.

### 2. `nara_download_binaries.py`

Reads a CSV (typically produced by `nara_get_metadata.py`) with columns:
```
naId,title,objectUrl,objectFileSize
```
It:

1. **Reports** the total number of binaries and the sum of their file sizes in a **human-readable** format.  
2. Creates a **date-based** subdirectory under a specified or default path (`./downloads`), for example:
   ```
   20250203-1
   ```
   If rerun on the same date, increments the suffix (`20250203-2`, etc.).  
3. **Logs** the start time, then for **each** row in the CSV:
   - Downloads the file from `objectUrl`, showing a **progress bar**.  
   - **Optionally** waits a back-off time (in milliseconds) between downloads (via `--backoff`).  
4. **Logs** the end time, total time elapsed, number of downloads attempted/successful.  
5. **Prints** any failures by **CSV line number** and URL, so you can re-attempt those downloads if needed.

**Usage**:
```bash
python nara_download_binaries.py \
  --csv my_metadata/720246-binaries-20250101.csv \
  --download_path ./downloads \
  --backoff 500
```

**Key Arguments**:
- `--csv`: Path to the CSV with `objectUrl` columns to download.  
- `--download_path`: Base directory for date-based subfolders (default=`./downloads`).  
- `--test`: Prints stats but does **not** download anything.  
- `--backoff <ms>`: Optional integer specifying how many milliseconds to wait after each file completes. (Default=0).  

**What’s New**:  
- **Back-off** time support (`--backoff`).  
- **Line Number Failures**: If a file fails to download, the script logs a summary at the end, e.g.  
  ```
  [*] The following 2 items failed to download:

    CSV line 3: http://example.com/badfile.pdf
    CSV line 10: http://another.com/badimage.jpg
  ```
- **Filename** includes the NAID if available, e.g. `720246_filename.pdf`.

### 3. `split_csv.py`

Takes a CSV (e.g., produced by `nara_get_metadata.py`) and **splits** it into **N** parts of roughly equal size. Each split includes the **same header** row as the original.

**Usage**:
```bash
python split_csv.py --input my_records.csv --parts 4
```
- `--input`: The input CSV to split.  
- `--parts`: Number of output CSV files (default=3).  

Produces something like:
```
records_part1.csv
records_part2.csv
records_part3.csv
records_part4.csv
```
Each file has the same header and a share of the data rows.

---

## Usage Examples

### 1. Get Metadata by NAID

```bash
export NARA_API_KEY="YOUR_VALID_API_KEY"

# Multiple NAIDs from command line
python nara_get_metadata.py \
  --naid 720246 123456 \
  --limit 50 \
  --outdir metadata_results

# Or from a batch file
python nara_get_metadata.py \
  --batch naids.txt \
  --outdir metadata_results
```
Creates subdirectories:
```
metadata_results/
  ├─ 720246/
  │   ├─ 720246-metadata-pg1of4-20250101.json
  │   └─ 720246-binaries-20250101.csv
  └─ 123456/
      ├─ 123456-metadata-pg1of6-20250101.json
      └─ 123456-binaries-20250101.csv
```

### 2. Download Files from the Resulting CSV

```bash
python nara_download_binaries.py \
  --csv metadata_results/720246/720246-binaries-20250101.csv \
  --download_path my_downloads \
  --backoff 1000
```
Waits 1 second between each file download and logs any failures by CSV line number.

### 3. Split a Large CSV

```bash
python split_csv.py \
  --input metadata_results/720246/720246-binaries-20250101.csv \
  --parts 4
```
Produces:
```
records_part1.csv
records_part2.csv
records_part3.csv
records_part4.csv
```
Each containing the same header row and a portion of the original data.

---

## License

This project is provided “as is” under the terms of your chosen license. Feel free to adapt and extend for your use case. We make no guarantees about data completeness, correctness, or performance.  

For more details, refer to the [NARA NextGen Catalog API docs](https://catalog.archives.gov/api/v2/api-docs/) and abide by any relevant usage policies.