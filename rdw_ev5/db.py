"""SQLite storage for tracking known Kia EV5 registrations."""

import sqlite3
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parent.parent / "data" / "ev5.db"

SCHEMA = """\
CREATE TABLE IF NOT EXISTS vehicles (
    kenteken       TEXT PRIMARY KEY,
    catalogusprijs INTEGER,
    bpm_datum      TEXT,
    typegoedkeuringsnummer TEXT,
    datum_tenaamstelling   TEXT,
    eerste_kleur   TEXT,
    handelsbenaming TEXT,
    first_seen     TEXT NOT NULL DEFAULT (date('now'))
);
"""


def connect(db_path: Path = DEFAULT_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def upsert_vehicles(conn: sqlite3.Connection, vehicles: list[dict]) -> list[dict]:
    """Insert new vehicles and return list of newly seen ones."""
    new = []
    for v in vehicles:
        kenteken = v["kenteken"]
        existing = conn.execute("SELECT 1 FROM vehicles WHERE kenteken = ?", (kenteken,)).fetchone()
        if existing:
            continue
        conn.execute(
            """\
            INSERT INTO vehicles (kenteken, catalogusprijs, bpm_datum,
                                  typegoedkeuringsnummer, datum_tenaamstelling,
                                  eerste_kleur, handelsbenaming)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                kenteken,
                v.get("catalogusprijs"),
                v.get("registratie_datum_goedkeuring_afschrijvingsmoment_bpm_dt"),
                v.get("typegoedkeuringsnummer"),
                v.get("datum_tenaamstelling"),
                v.get("eerste_kleur"),
                v.get("handelsbenaming"),
            ),
        )
        new.append(v)
    conn.commit()
    return new


def get_total_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
