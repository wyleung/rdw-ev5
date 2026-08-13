"""Alert when new vehicles match watch criteria."""

import os
from datetime import date
from pathlib import Path

import httpx

from . import eukor_schedule
from .report import _derive_color, _derive_trim

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
    ("MIGNON V-WE611", "Rotterdam", "2026-04-22", "eukor"),
    ("NOCC ADRIATIC V-WE614", "Rotterdam", "2026-05-19", "eukor"),
    ("MORNING CAPO V-WE615", "Rotterdam", "2026-05-23", "eukor"),
]

# Flat (name, date) list for backwards compat with _next_ship / ship_report
SHIPS = [(name, date) for name, _port, date, _src in SHIPS_DETAILED]


def _next_ship() -> str:
    """Next upcoming arrival, preferring live EUKOR schedule data.

    SHIPS_DETAILED is hand-transcribed and goes stale: it ran out on 2026-05-23,
    after which every alert reported "all ships arrived". The cached EUKOR
    schedule is merged in so this keeps working without anyone editing the list.
    Explicit sort because the merged entries do not arrive in date order.
    """
    today = date.today().isoformat()
    upcoming = list(SHIPS)
    try:
        upcoming += [(name, eta) for name, _port, eta, _src in eukor_schedule.upcoming_arrivals()]
    except Exception:
        pass  # never let a schedule-cache problem break the alert path

    for name, arrival in sorted(upcoming, key=lambda s: s[1]):
        if arrival >= today:
            return f"{name} (ETA {arrival})"
    return "all ships arrived"


def _price(v: dict) -> int:
    try:
        return int(v.get("catalogusprijs") or 0)
    except (ValueError, TypeError):
        return 0


def _colour(v: dict) -> str:
    return (v.get("eerste_kleur") or "").upper()


# uitvoering code of the EV5 GT — the 225 kW (306 pk) AWD variant, fiscale
# waarde EUR 58,950 (Kia NL prijslijst juli 2026). RDW's catalogusprijs adds the
# paint option, so a GT in any colour but the free Frost Blue lists at 59,845
# (58,950 + 895). The first one appeared in RDW on 2026-08-12.
GT_UITVOERING = "E12DX1"

# Each entry is (label, predicate). A vehicle matching any predicate alerts,
# tagged with the label so the message says which watch fired.
WATCHES: list[tuple] = [
    ("WIT >€50k", lambda v: _colour(v) == "WIT" and _price(v) > 50000),
    # Ordered car: EV5 GT in Ivory Silver. Deliberately matched on the variant
    # code alone, not on colour: RDW records only Dutch colour names, and its
    # GRIJS covers both Ivory Silver and Gravity Gray, so a colour filter could
    # not isolate the car anyway — and would silently miss it if Ivory Silver
    # turns out to register as WIT rather than GRIJS. The GT is rare enough
    # (1 nationwide so far) that every one of them is worth seeing; the alert
    # prints the colour so it is obvious at a glance whether it could be yours.
    ("EV5 GT", lambda v: v.get("uitvoering") == GT_UITVOERING),
]


def check_alerts(new_vehicles: list[dict]) -> list[dict]:
    """Return vehicles matching any watch, each tagged with `_watch`."""
    matches = []
    for v in new_vehicles:
        hits = [label for label, matches_fn in WATCHES if matches_fn(v)]
        if hits:
            tagged = dict(v)  # copy: never mutate the caller's rows
            tagged["_watch"] = ", ".join(hits)
            matches.append(tagged)
    return matches


def notify(matches: list[dict]) -> None:
    """Post matches to Slack (when configured) and append them to the alert log."""
    ship_info = _next_ship()
    lines = []
    for v in matches:
        price = _price(v)
        colour = _derive_color(v.get("eerste_kleur"), price)
        trim = _derive_trim(v.get("uitvoering"), price)
        watch = v.get("_watch", "")
        lines.append(f"{v['kenteken']}  €{price}  {trim}  {colour}  [{watch}]")

    body = "\n".join(lines)
    header = f"Kia EV5 watch — {len(matches)} match(es)!"

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
