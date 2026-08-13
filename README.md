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

## Deployment (datafu NAS)

The stack runs on the Synology NAS as three containers off one image — `web`
(dashboard behind traefik), `scraper` (6-hourly RDW sync) and `tracker`
(4-hourly AIS positions) — all sharing `/volume1/docker/rdw-ev5/data`.

Ansible does the deploying; the playbook lives in the sibling
`ansible.playbooks` repo at `servers/datafu-nas/rdw-ev5.yml`. The NAS never sees
this source tree — it pulls a prebuilt image from GHCR.

### One-time setup

1. GitHub PAT with `write:packages` (to push) and `read:packages` (for the NAS):

   ```bash
   echo "$GHCR_TOKEN" | docker login ghcr.io -u wyleung --password-stdin
   ```

2. In `ansible.playbooks`, fill in and encrypt the secrets:

   ```bash
   cp secrets/rdw-ev5.yml.example secrets/rdw-ev5.yml
   $EDITOR secrets/rdw-ev5.yml          # ghcr token, Slack webhook, aisstream key
   ansible-vault encrypt secrets/rdw-ev5.yml
   ```

3. Point `ev5.e-sensei.nl` at the NAS in DNS. Traefik's existing wildcard
   `*.e-sensei.nl` certificate already covers it, so no new ACME order runs.

### Each release

```bash
# 1. build and push (from this repo)
./scripts/build-push.sh 0.1.0

# 2. bump docker_image in servers/datafu-nas/rdw-ev5.yml to the tag you pushed,
#    then deploy (from the root of the ansible.playbooks repo)
ansible-playbook servers/datafu-nas/rdw-ev5.yml -i inventory.ini \
  --vault-password-file ~/.ssh/ansible_vault_password_datafu
```

The first deploy copies the local `data/*.db` and `vessel_*.json` up to the NAS
so registration history and first-seen timestamps carry over. That step is
`force: false`, so later re-runs never overwrite the live databases — the NAS
copy is authoritative from then on.

## Data source

- Dataset: [`m9d7-ebf2`](https://opendata.rdw.nl/resource/m9d7-ebf2.json) — *Gekentekende voertuigen*
- API: Socrata SODA — no auth token required, but rate-limited
- Filter: `merk = Kia AND handelsbenaming = Ev5`
