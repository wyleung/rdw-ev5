FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY rdw_ev5/ rdw_ev5/

RUN uv pip install --system -e .

# Data volume mount point
VOLUME /app/data

EXPOSE 8000
