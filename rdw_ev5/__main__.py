"""CLI entry point: fetch latest Kia EV5 data and report new registrations."""

import argparse
from pathlib import Path

from . import alerts, db, kia_db, kia_scraper, port_scraper, report, ship_report


def _kia_sync(args) -> None:
    """Sync all Kia vehicles from RDW into kia.db, then refresh ev5.db from it."""
    print(f"Fetching all Kia registrations since {args.since} from RDW...")
    vehicles = kia_scraper.fetch_all(since=args.since)
    print(f"API returned {len(vehicles)} vehicles")

    kia_conn = kia_db.connect(args.kia_db)
    new_count = kia_db.upsert_vehicles(kia_conn, vehicles)
    kia_total = kia_db.get_total_count(kia_conn)
    print(f"Kia DB: {new_count} new, {kia_total} total")

    # Scrape vessel port calls from MyShipTracking
    print("Scraping vessel port calls...")
    port_scraper.scrape_all()

    # Ship arrivals report (from full Kia DB)
    ship_path = ship_report.generate_ship_report(kia_conn)
    print(f"Ship report: {ship_path}")

    # Extract EV5 records and feed into ev5.db
    ev5_records = kia_db.extract_ev5(kia_conn)
    kia_conn.close()

    ev5_conn = db.connect(args.db)
    new_ev5 = db.upsert_vehicles(ev5_conn, ev5_records)
    ev5_total = db.get_total_count(ev5_conn)

    if new_ev5:
        print(f"\n=== {len(new_ev5)} new EV5 vehicle(s) found ===")
        for v in new_ev5:
            price = v.get("catalogusprijs", "?")
            color = v.get("eerste_kleur", "?")
            bpm_date = v.get("registratie_datum_goedkeuring_afschrijvingsmoment_bpm_dt", "")[:10]
            print(f"  {v['kenteken']}  €{price}  {color}  {bpm_date}")

        matches = alerts.check_alerts(new_ev5)
        if matches:
            alerts.notify(matches)
            print(f"\n*** ALERT: {len(matches)} WIT >€50k vehicle(s) matched! ***")
            for m in matches:
                print(f"  >>> {m['kenteken']}  €{m.get('catalogusprijs', '?')}")
    else:
        print("\nNo new EV5 vehicles since last run.")

    print(f"EV5 tracked: {ev5_total}")

    report_path = report.generate_report(ev5_conn)
    ev5_conn.close()
    print(f"Report: {report_path}")


def _ev5_only(args) -> None:
    """Legacy mode: scrape only EV5 directly from the API."""
    from . import scraper

    print("Fetching Kia EV5 registrations from RDW...")
    vehicles = scraper.fetch_all()
    print(f"API returned {len(vehicles)} vehicles")

    conn = db.connect(args.db)
    new_vehicles = db.upsert_vehicles(conn, vehicles)
    total = db.get_total_count(conn)

    if new_vehicles:
        print(f"\n=== {len(new_vehicles)} new vehicle(s) found ===")
        for v in new_vehicles:
            price = v.get("catalogusprijs", "?")
            color = v.get("eerste_kleur", "?")
            date = v.get("registratie_datum_goedkeuring_afschrijvingsmoment_bpm_dt", "")[:10]
            print(f"  {v['kenteken']}  €{price}  {color}  {date}")
    else:
        print("\nNo new vehicles since last run.")

    print(f"\nTotal tracked: {total}")

    if new_vehicles:
        matches = alerts.check_alerts(new_vehicles)
        if matches:
            alerts.notify(matches)
            print(f"\n*** ALERT: {len(matches)} WIT >€50k vehicle(s) matched! ***")
            for m in matches:
                print(f"  >>> {m['kenteken']}  €{m.get('catalogusprijs', '?')}")

    report_path = report.generate_report(conn)
    conn.close()
    print(f"Report: {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Track Kia EV5 registrations in NL")
    parser.add_argument(
        "--db",
        type=Path,
        default=db.DEFAULT_DB,
        help="Path to EV5 SQLite database (default: data/ev5.db)",
    )
    parser.add_argument(
        "--kia-db",
        type=Path,
        default=kia_db.DEFAULT_KIA_DB,
        help="Path to full Kia SQLite database (default: data/kia.db)",
    )
    parser.add_argument(
        "--report-only",
        action="store_true",
        help="Regenerate the HTML report from existing DB data without fetching",
    )
    parser.add_argument(
        "--kia-sync",
        action="store_true",
        help="Sync all Kia vehicles from RDW into kia.db, then extract EV5",
    )
    parser.add_argument(
        "--since",
        default="2025-01-01",
        help="Start date for Kia sync (default: 2025-01-01)",
    )
    args = parser.parse_args()

    if args.report_only:
        conn = db.connect(args.db)
        report_path = report.generate_report(conn)
        conn.close()
        print(f"Report: {report_path}")
        kia_conn = kia_db.connect(args.kia_db)
        ship_path = ship_report.generate_ship_report(kia_conn)
        kia_conn.close()
        print(f"Ship report: {ship_path}")
        return

    if args.kia_sync:
        _kia_sync(args)
        return

    _ev5_only(args)


if __name__ == "__main__":
    main()
