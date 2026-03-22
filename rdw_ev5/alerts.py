"""Alert when new vehicles match watch criteria."""

import subprocess
from datetime import date
from pathlib import Path

ALERT_LOG = Path(__file__).resolve().parent.parent / "data" / "alerts.log"

# Ship schedule: Pyeongtaek → Rotterdam
SHIPS = [
    ("NOCC PACIFIC V-WE610", "2026-04-11"),
    ("MIGNON V-WE611", "2026-04-17"),
    ("NOCC ADRIATIC V-WE614", "2026-05-17"),
]


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
        subprocess.run(
            ["notify-send", "--urgency=critical", "-i", "car", header, body],
            timeout=5,
        )
    except FileNotFoundError:
        pass

    # Append to log
    ALERT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(ALERT_LOG, "a") as f:
        f.write(f"\n[{date.today().isoformat()}] {header}  (next ship: {ship_info})\n")
        for line in lines:
            f.write(f"  {line}\n")
