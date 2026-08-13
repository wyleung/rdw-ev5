# Changelog

Semantic versioning, `MAJOR.MINOR.PATCH`:

- **MAJOR** — incompatible change to how the app is driven or to stored data:
  a removed/renamed CLI flag, a SQLite schema change needing migration, a
  removed HTTP route or a changed JSON response shape.
- **MINOR** — backwards-compatible additions: a new CLI flag, a new dashboard
  page or API route, a new data source, new report content.
- **PATCH** — backwards-compatible fixes and anything invisible to a caller:
  bug fixes, chart/styling corrections, packaging, Docker, CI, docs.

While the version stays `0.x`, MINOR absorbs breaking changes too — the `0.`
prefix is the signal that no API stability is promised yet.

The version in `pyproject.toml` is the single source of truth. `rdw_ev5.__version__`
reads it from installed package metadata, and `scripts/build-push.sh` derives the
image tag from it, so the released image, the git tag and the package always agree.

## 0.2.0 — 2026-08-12

Everything below 0.1.0 shipped without a version bump; this release collects it
and starts real version tracking. The repo carried `0.1.0` across 15 commits,
including a whole web dashboard, so the number had stopped meaning anything.

### Added

- FastAPI dashboard (`rdw_ev5/webapp.py`) with pages for the fleet, the
  trim × colour matrix, ship arrivals and live vessel positions.
- Full-Kia-dataset sync (`--kia-sync`) into `kia.db`, with EV5 extracted into
  `ev5.db`, replacing the EV5-only scrape.
- Ship tracking: port-call scraping and AIS vessel positions
  (`port_scraper.py`, `vessel_tracker.py`, `ship_report.py`).
- `eukor_schedule.py`: forward-looking EUKOR ETAs into NW Europe, replacing the
  hand-transcribed arrival list. The endpoint only searches port-to-port, so it
  sweeps a load × discharge grid and matches vessels by name (the feed carries
  no IMO). Cached to `data/vessel_schedule.json`.
- `--report-only` to regenerate reports without hitting the API.
- HTML report with 4-quadrant charts, dark/light theming, trim-level price
  mapping and Kia's own exterior colour names.
- Slack alerting for white (`WIT`) EV5 registrations over €50 000.
- Multiple named watch criteria instead of one hard-coded rule. Alerts now say
  which watch fired and report the trim and Kia colour name, not just the plate.
- Watch for the EV5 GT (`uitvoering` `E12DX1`), the 225 kW AWD variant at
  €58 950 fiscale waarde — €59 845 in RDW once the €895 paint option is added.
- Deployment to the datafu NAS: `Dockerfile`, `.dockerignore` and
  `scripts/build-push.sh` publishing to GHCR, deployed by
  `servers/datafu-nas/rdw-ev5.yml` in the `ansible.playbooks` repo.

### Changed

- `--kia-sync` now checks alerts before writing reports, so a report failure
  can no longer swallow an alert.

### Removed

- Desktop notifications. Alerts go to `data/alerts.log` and Slack instead.
  A removal like this would be MAJOR after 1.0.0; it is allowed here only
  because the version is still `0.x`.

### Fixed

- The EV5 GT is labelled `GT` in the charts and matrix. Its `uitvoering` code
  was unrecognised, so it fell through to the price-fallback branch and showed
  up as a one-off trim called "€59845".
- The "next ship" line in alerts no longer reports "all ships arrived" whenever
  the hand-kept arrival list falls behind — it now merges the cached EUKOR
  schedule, falling back to the static list if that cache is missing or corrupt.
- Container logs are unbuffered and carry a real local timestamp — `TZ` and
  `tzdata` are set in the image, and the log header's `$(date)` is quoted so
  the shell actually expands it instead of printing the literal string.
- The `uv` version used to build the image is pinned, so rebuilding an old
  tag reproduces the image it originally produced.

## 0.1.0 — 2026-03-22

- Initial scraper: paginated RDW SODA API client, SQLite storage keyed on
  `kenteken`, and a report of newly seen vehicles on each run.
