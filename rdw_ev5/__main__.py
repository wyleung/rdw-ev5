"""CLI entry point: fetch latest Kia EV5 data and report new registrations."""

import argparse
import sys
from pathlib import Path

from . import scraper, db


def main() -> None:
    parser = argparse.ArgumentParser(description="Track Kia EV5 registrations in NL")
    parser.add_argument(
        "--db",
        type=Path,
        default=db.DEFAULT_DB,
        help="Path to SQLite database (default: data/ev5.db)",
    )
    args = parser.parse_args()

    print("Fetching Kia EV5 registrations from RDW...")
    vehicles = scraper.fetch_all()
    print(f"API returned {len(vehicles)} vehicles")

    conn = db.connect(args.db)
    new_vehicles = db.upsert_vehicles(conn, vehicles)
    total = db.get_total_count(conn)
    conn.close()

    if new_vehicles:
        print(f"\n=== {len(new_vehicles)} new vehicle(s) found ===")
        for v in new_vehicles:
            price = v.get("catalogusprijs", "?")
            color = v.get("eerste_kleur", "?")
            date = v.get(
                "registratie_datum_goedkeuring_afschrijvingsmoment_bpm_dt", ""
            )[:10]
            print(f"  {v['kenteken']}  €{price}  {color}  {date}")
    else:
        print("\nNo new vehicles since last run.")

    print(f"\nTotal tracked: {total}")


if __name__ == "__main__":
    main()
