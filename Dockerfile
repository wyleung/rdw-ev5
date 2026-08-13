FROM python:3.12-slim

WORKDIR /app

# tzdata so the timestamps in the scraper/tracker log loops read as local time
# rather than UTC; python:slim ships without a zoneinfo database.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Europe/Amsterdam \
    PYTHONUNBUFFERED=1

# Install uv for fast dependency management. Pinned rather than :latest so a
# rebuild of an old tag reproduces the image it originally produced.
COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY rdw_ev5/ rdw_ev5/

# -e is load-bearing, not a dev convenience: every data path in the package is
# derived from Path(__file__).parent.parent (see db.py, kia_db.py, report.py,
# webapp.py, vessel_tracker.py, alerts.py). An editable install keeps __file__
# under /app/rdw_ev5/, so those resolve to /app/data — the volume below. A
# regular install moves the package into site-packages and they would resolve
# somewhere under /usr/local instead, silently writing the databases outside
# the mount.
RUN uv pip install --system -e .

# Data volume mount point
VOLUME /app/data

EXPOSE 8000
