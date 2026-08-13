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

# Build and push the deployment image to GHCR
./scripts/build-push.sh 0.1.0
```

## Architecture

- **`rdw_ev5/scraper.py`** — Fetches all Kia EV5 records from `opendata.rdw.nl/resource/m9d7-ebf2.json` using SoQL queries with pagination (1000 records/batch).
- **`rdw_ev5/db.py`** — SQLite storage. Tracks vehicles by `kenteken` (license plate) as primary key. `upsert_vehicles()` returns only newly seen vehicles.
- **`rdw_ev5/__main__.py`** — CLI entry point that ties scraper and db together, prints new registrations.
- **`data/ev5.db`** — Default SQLite database location (gitignored).

Every data path in the package is derived from `Path(__file__).resolve().parent.parent / "data"`.
This is why the Dockerfile installs with `uv pip install --system -e .` — the editable
install keeps `__file__` under `/app/rdw_ev5/`, so the paths land in `/app/data`, the
volume mount. A regular (non-editable) install moves the package into `site-packages`
and the databases silently get written outside the mount.

## Versioning

Semantic versioning; the policy and the release history live in `CHANGELOG.md`.
`pyproject.toml` holds the only copy of the version — `rdw_ev5.__version__` reads
it back from installed package metadata and `scripts/build-push.sh` derives the
image tag from it. Do not hardcode a version anywhere else.

Releasing: bump `pyproject.toml`, add a `CHANGELOG.md` entry, commit, tag
`vX.Y.Z`, run `./scripts/build-push.sh`, then bump `docker_image` in the
playbook and deploy. The build script refuses to push from a dirty tree, since
the resulting tag could not be reconstructed from any commit.

## Deployment

Runs on the Synology NAS (`datafu`, 192.168.0.50) as three containers off one GHCR
image: `web` (dashboard behind traefik at `ev5.e-sensei.nl`), `scraper` (6-hourly RDW
sync), `tracker` (4-hourly AIS positions). The NAS pulls a prebuilt image and never
sees this source tree.

The playbook lives in the sibling repo `../ansible.playbooks`:

- `servers/datafu-nas/rdw-ev5.yml` — playbook, image tag, intervals, seeding
- `servers/datafu-nas/templates/rdw-ev5/docker-compose.yml` — compose template
- `secrets/rdw-ev5.yml` — vaulted GHCR token, Slack webhook, aisstream key

Deploy flow: `./scripts/build-push.sh <tag>`, bump `docker_image` in the playbook,
then run it. See the Deployment section of `README.md` for the full commands.

Containers run as uid 1028 (`artoo`) / gid 100 so the SQLite databases stay readable
from DSM. That uid is set in two places in the playbook — `rdw_ev5_uid`, which the
compose template reads, and the `chown` on the data directory — and they must agree
or the app gets `EACCES` and crash-loops.

## Data Source

- Dataset: `m9d7-ebf2` on `opendata.rdw.nl` (Gekentekende voertuigen)
- API: Socrata SODA — no auth token needed, but rate-limited
- Filter: `merk=Kia AND handelsbenaming=Ev5`
- Key fields: `kenteken`, `catalogusprijs`, `eerste_kleur`, `registratie_datum_goedkeuring_afschrijvingsmoment_bpm_dt`
