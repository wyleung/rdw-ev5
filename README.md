# rdw-ev5

Daily scraper that monitors new Kia EV5 registrations in the Netherlands via the [RDW open data portal](https://opendata.rdw.nl). On each run it fetches all registrations, stores them in SQLite, reports newly seen vehicles, and generates an HTML report with cumulative charts.

## Features

- Paginates through the RDW SODA API to fetch all Kia EV5 records
- Tracks vehicles by license plate (`kenteken`) in a local SQLite database
- Reports new registrations since the last run
- Alerts (desktop notification + log) when a white (`WIT`) EV5 with catalog price > €50 000 appears
- Generates a daily HTML report with 4-quadrant Chart.js charts: all-time and current-month breakdowns by color and catalog price

## Requirements

- Python 3.11+
- [uv](https://github.com/astral-sh/uv)

## Setup

```bash
uv venv && uv pip install -e .
```

## Usage

```bash
# Run with default database (data/ev5.db)
.venv/bin/python -m rdw_ev5

# Run with a custom database path
.venv/bin/python -m rdw_ev5 --db /path/to/custom.db
```

Sample output:

```
Fetching Kia EV5 registrations from RDW...
API returned 312 vehicles

=== 3 new vehicle(s) found ===
  XX-123-Y  €54990  WIT  2026-03-20
  ...

Total tracked: 312
Report: data/reports/2026-03-22.html
```

## Project structure

```
rdw_ev5/
├── __main__.py   # CLI entry point
├── scraper.py    # RDW SODA API client (paginated)
├── db.py         # SQLite storage
├── report.py     # HTML report generator
└── alerts.py     # Watch criteria + desktop notifications
data/
├── ev5.db        # SQLite database (gitignored)
├── alerts.log    # Alert history (gitignored)
└── reports/      # Daily HTML reports (gitignored)
```

## Data source

- Dataset: [`m9d7-ebf2`](https://opendata.rdw.nl/resource/m9d7-ebf2.json) — *Gekentekende voertuigen*
- API: Socrata SODA — no auth token required, but rate-limited
- Filter: `merk = Kia AND handelsbenaming = Ev5`
