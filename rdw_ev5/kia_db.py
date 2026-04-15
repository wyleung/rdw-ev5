"""SQLite storage for all Kia registrations (data/kia.db)."""

import sqlite3
from pathlib import Path

DEFAULT_KIA_DB = Path(__file__).resolve().parent.parent / "data" / "kia.db"

SCHEMA = """\
CREATE TABLE IF NOT EXISTS vehicles (
    kenteken            TEXT PRIMARY KEY,
    merk                TEXT,
    handelsbenaming     TEXT,
    catalogusprijs      INTEGER,
    bpm_datum           TEXT,
    typegoedkeuringsnummer TEXT,
    datum_tenaamstelling TEXT,
    datum_eerste_toelating TEXT,
    eerste_kleur        TEXT,
    tweede_kleur        TEXT,
    uitvoering          TEXT,
    variant             TEXT,
    inrichting          TEXT,
    massa_rijklaar      INTEGER,
    aantal_zitplaatsen  INTEGER,
    aantal_deuren       INTEGER,
    bruto_bpm           INTEGER,
    first_seen          TEXT NOT NULL DEFAULT (date('now'))
);
"""


def connect(db_path: Path = DEFAULT_KIA_DB) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def upsert_vehicles(conn: sqlite3.Connection, vehicles: list[dict]) -> int:
    """Insert or ignore vehicles. Returns count of newly inserted rows."""
    new_count = 0
    for v in vehicles:
        cur = conn.execute(
            """\
            INSERT OR IGNORE INTO vehicles (
                kenteken, merk, handelsbenaming, catalogusprijs, bpm_datum,
                typegoedkeuringsnummer, datum_tenaamstelling, datum_eerste_toelating,
                eerste_kleur, tweede_kleur, uitvoering, variant, inrichting,
                massa_rijklaar, aantal_zitplaatsen, aantal_deuren, bruto_bpm
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                v["kenteken"],
                v.get("merk"),
                v.get("handelsbenaming"),
                _int_or_none(v.get("catalogusprijs")),
                v.get("registratie_datum_goedkeuring_afschrijvingsmoment_bpm_dt"),
                v.get("typegoedkeuringsnummer"),
                v.get("datum_tenaamstelling"),
                v.get("datum_eerste_toelating"),
                v.get("eerste_kleur"),
                v.get("tweede_kleur"),
                v.get("uitvoering"),
                v.get("variant"),
                v.get("inrichting"),
                _int_or_none(v.get("massa_rijklaar")),
                _int_or_none(v.get("aantal_zitplaatsen")),
                _int_or_none(v.get("aantal_deuren")),
                _int_or_none(v.get("bruto_bpm")),
            ),
        )
        if cur.rowcount > 0:
            new_count += 1
    conn.commit()
    return new_count


def extract_ev5(conn: sqlite3.Connection) -> list[dict]:
    """Extract EV5 records from the full Kia database as dicts compatible with the EV5 pipeline."""
    rows = conn.execute(
        """\
        SELECT kenteken, catalogusprijs,
               bpm_datum as registratie_datum_goedkeuring_afschrijvingsmoment_bpm_dt,
               typegoedkeuringsnummer, datum_tenaamstelling, eerste_kleur,
               handelsbenaming, uitvoering
        FROM vehicles
        WHERE UPPER(handelsbenaming) = 'EV5'
        ORDER BY kenteken"""
    ).fetchall()
    return [dict(r) for r in rows]


def get_total_count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]


def _int_or_none(val) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
