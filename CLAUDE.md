# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Daily scraper that monitors new Kia EV5 registrations in the Netherlands via the RDW (Rijksdienst voor het Wegverkeer) open data portal. It queries the SODA API, stores results in SQLite, and reports newly seen vehicles on each run.

## Commands

```bash
# Setup
uv venv && uv pip install -e .

# Run the scraper
.venv/bin/python -m rdw_ev5

# Run with custom database path
.venv/bin/python -m rdw_ev5 --db /path/to/custom.db
```

## Architecture

- **`rdw_ev5/scraper.py`** — Fetches all Kia EV5 records from `opendata.rdw.nl/resource/m9d7-ebf2.json` using SoQL queries with pagination (1000 records/batch).
- **`rdw_ev5/db.py`** — SQLite storage. Tracks vehicles by `kenteken` (license plate) as primary key. `upsert_vehicles()` returns only newly seen vehicles.
- **`rdw_ev5/__main__.py`** — CLI entry point that ties scraper and db together, prints new registrations.
- **`data/ev5.db`** — Default SQLite database location (gitignored).

## Data Source

- Dataset: `m9d7-ebf2` on `opendata.rdw.nl` (Gekentekende voertuigen)
- API: Socrata SODA — no auth token needed, but rate-limited
- Filter: `merk=Kia AND handelsbenaming=Ev5`
- Key fields: `kenteken`, `catalogusprijs`, `eerste_kleur`, `registratie_datum_goedkeuring_afschrijvingsmoment_bpm_dt`
