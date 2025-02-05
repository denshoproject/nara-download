# NARA NextGen Catalog Scripts

This repository contains Python 3 scripts for interacting with the [NARA NextGen Catalog API 2.0](https://catalog.archives.gov/api/v2/api-docs/), downloading metadata and associated binaries, and splitting CSV outputs. In the NARA NextGen catalog system, every record group, series, item and even subject cataloging term has a unique identifier called an `NAID`. For our purposes, a series `NAID` can be used to retrieve metadata about the series, including metadata about each individual child item record and related digital objects, if available. The Catalog API 2.0 will return these files as JSON data; see the example on the [API help page](https://www.archives.gov/research/catalog/help/api). 



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

This script queries the NARA NextGen Catalog API endpoint:
```
GET /records/parentNaId/{parentNaId}?page={...}&limit={...}
```
It:

- **Discovers** how many pages of results exist (via `body.hits.total.value`).  
- **Fetches** each page in JSON format and saves it to a file named:
  ```
  [parentNaId]-pg[#]of[#]-[YYYYMMdd].json
  ```
- **Extracts** each record’s `naId`, `title`, and `digitalObjects` array (if any), and creates a **single CSV** of the form:
  ```
  naId,title,objectUrl,objectFileSize
  ```
- **Usage**:
  ```bash
  python nara_get_metadata.py --parent-naid 720246 [--limit 100] [--outdir results]
  ```
  - `--parent-naid`: The parent NaId you want to query.  
  - `--limit`: How many records to fetch per page (default=100).  
  - `--outdir`: Where JSON pages and the final CSV are saved (default=`results`).

The resulting CSV can then be passed to `nara_download_binaries.py` for downloading the actual files.

### 2. `nara_download_binaries.py`

Reads the CSV produced by `nara_get_metadata.py`, which has columns:
```
naId,title,objectUrl,objectFileSize
```
It:

1. Reports the **total number** of binaries and **sum** of file sizes in a **human-readable** format.  
2. Creates a date-based subdirectory (e.g., `downloads/20240203-1`) to store the downloaded files.  
   - This location can be overridden via `--download_path`.  
3. Logs the **start time**.  
4. **Downloads** each `objectUrl`, showing a **progress bar** for each file.  
5. Logs the **end time**, **elapsed time**, **downloads attempted**, and **downloads successful**.

**Usage**:
```bash
python nara_download_binaries.py --csv my_records.csv [--test] [--download_path ./downloads]
```
- `--csv`: The CSV from `nara_get_metadata.py`.  
- `--test`: If provided, no downloads happen; only stats are shown.  
- `--download_path`: Relative path where date-based subdirectories will be created (default=`./downloads`).

### 3. `split_csv.py`

Takes a CSV (e.g., the one produced by `nara_get_metadata.py`) and **splits** it into **N** parts of roughly equal size. Each part has the same **header** as the original CSV.

**Usage**:
```bash
python split_csv.py --input my_records.csv [--parts 5]
```
- `--input`: The input CSV to split.  
- `--parts`: Number of output CSV files (default=3).

The script produces:
```
records_part1.csv
records_part2.csv
...
records_partN.csv
```
Each containing the same header row and a portion of the data rows.

---

## Usage Examples

1. **Get metadata for parent NaId**  
   ```bash
   export NARA_API_KEY="YOUR_VALID_API_KEY"
   python nara_get_metadata.py --parent-naid 720246 --limit 50 --outdir results
   ```
   This fetches and saves JSON pages to `results/720246-pg[#]of[#]-YYYYMMdd.json` and creates `results/720246-records-YYYYMMdd.csv`.

2. **Download files from the resulting CSV**  
   ```bash
   python nara_download_binaries.py --csv results/720246-records-20250101.csv
   ```
   Creates a folder like `./downloads/20250101-1` and downloads all `objectUrl`s to that folder, showing a progress bar.

3. **Split a large CSV into multiple parts**  
   ```bash
   python split_csv.py --input results/720246-records-20250101.csv --parts 4
   ```
   Produces:
   ```
   records_part1.csv
   records_part2.csv
   records_part3.csv
   records_part4.csv
   ```

---

## License

This project is provided “as is” under the terms of your chosen license. Feel free to adapt and extend for your use case. We make no guarantees about data completeness, correctness, or performance.  

For more details, refer to the [NARA NextGen Catalog API docs](https://catalog.archives.gov/api/v2/api-docs/) and abide by any relevant usage policies.
