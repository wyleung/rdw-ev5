"""Alert when new vehicles match watch criteria."""

import os
import subprocess
import sys
from datetime import date
from pathlib import Path

import httpx

ALERT_LOG = Path(__file__).resolve().parent.parent / "data" / "alerts.log"

# Ship arrivals at Rotterdam/Zeebrugge — (name, port, date, source)
# Sources: "eukor" = EUKOR schedule screenshot, "mst" = MyShipTracking, "rdw" = RDW wave analysis
SHIPS_DETAILED = [
    # Estimated from RDW registration wave analysis (pre-2026, vessel names unknown)
    ("Unknown ship", "Rotterdam", "2025-10-18", "rdw"),
    ("Unknown ship", "Rotterdam", "2025-11-14", "rdw"),
    ("Unknown ship", "Rotterdam", "2025-11-21", "rdw"),
    ("Unknown ship", "Rotterdam", "2025-12-02", "rdw"),
    ("Unknown ship", "Rotterdam", "2025-12-07", "rdw"),  # first EV5s
    ("Unknown ship", "Rotterdam", "2025-12-12", "rdw"),
    ("Unknown ship", "Rotterdam", "2025-12-19", "rdw"),
    ("Unknown ship", "Rotterdam", "2025-12-26", "rdw"),
    # Confirmed from EUKOR schedule + MyShipTracking
    ("MORNING LYNN V-WE602", "Rotterdam", "2026-02-28", "eukor"),
    ("MORNING CALM V-WE608", "Rozenburg", "2026-03-27", "mst"),
    ("MORNING CALM V-WE608", "Zeebrugge", "2026-03-31", "mst"),
    # Upcoming (EUKOR schedule, updated 2026-04-11)
    ("NOCC PACIFIC V-WE610", "Rotterdam", "2026-04-12", "eukor"),
    ("MIGNON V-WE611", "Rotterdam", "2026-04-18", "eukor"),
    ("NOCC ADRIATIC V-WE614", "Rotterdam", "2026-05-19", "eukor"),
    ("MORNING CAPO V-WE615", "Rotterdam", "2026-05-23", "eukor"),
]

# Flat (name, date) list for backwards compat with _next_ship / ship_report
SHIPS = [(name, date) for name, _port, date, _src in SHIPS_DETAILED]


def _next_ship() -> str:
    today = date.today().isoformat()
    for name, arrival in SHIPS:
        if arrival >= today:
            return f"{name} (ETA {arrival})"
    return "all ships arrived"


def check_alerts(new_vehicles: list[dict]) -> list[dict]:
    """Return vehicles matching the watch criteria: WIT + catalogusprijs > 50000."""
    matches = []
    for v in new_vehicles:
        color = (v.get("eerste_kleur") or "").upper()
        try:
            price = int(v.get("catalogusprijs", 0))
        except (ValueError, TypeError):
            continue
        if color == "WIT" and price > 50000:
            matches.append(v)
    return matches


def notify(matches: list[dict]) -> None:
    """Send desktop notification and append to alert log."""
    ship_info = _next_ship()
    lines = []
    for v in matches:
        kenteken = v["kenteken"]
        price = v.get("catalogusprijs", "?")
        line = f"{kenteken}  €{price}  WIT"
        lines.append(line)

    body = "\n".join(lines)
    header = f"Kia EV5 WIT >€50k — {len(matches)} match(es)!"

    # Desktop notification
    try:
        if sys.platform == "darwin":
            escaped_header = header.replace('"', '\\"')
            escaped_body = body.replace('"', '\\"')
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display notification "{escaped_body}" with title "{escaped_header}"',
                ],
                timeout=5,
            )
        elif sys.platform.startswith("linux"):
            subprocess.run(
                ["notify-send", "--urgency=critical", "-i", "car", header, body],
                timeout=5,
            )
    except FileNotFoundError:
        pass

    # Slack webhook (set SLACK_WEBHOOK_URL env var to enable)
    slack_url = os.environ.get("SLACK_WEBHOOK_URL")
    if slack_url:
        try:
            httpx.post(
                slack_url,
                json={
                    "text": f"🚗 *{header}*\n```\n{body}\n```\n_Next ship: {ship_info}_",
                },
                timeout=10,
            )
        except Exception:
            pass  # don't fail the run if Slack is unreachable

    # Append to log
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERT_LOG, "a") as f:
        f.write(f"\n[{date.today().isoformat()}] {header}  (next ship: {ship_info})\n")
        for line in lines:
            f.write(f"  {line}\n")
