"""Fetch forward-looking EUKOR sailing schedules (ETAs into NW Europe).

Complements port_scraper.py, which reads *past* port calls from MyShipTracking.
This module reads *future* ETAs, which is what the arrival list in alerts.py
previously needed transcribing from screenshots by hand.

The public eukor.com page is a shell around a third-party app on
m.eclipsocean.com. The real call is a form-encoded POST returning an HTML table
fragment — there is no JSON API, no auth, no cookie and no CSRF token, so the
endpoint can be called statelessly.

Two constraints from the endpoint drive the shape of this module:

  * There is no search by vessel, voyage or IMO. The only query is
    port-of-loading -> port-of-discharge, and both are mandatory. To answer
    "where are my vessels heading" we sweep a grid of load x discharge ports
    and filter the returned rows by vessel *name*.
  * The response carries no IMO, so vessels can only be matched on name.
    Names get reused and ships get renamed, so treat a name match as a hint and
    cross-check against the IMO map in port_scraper.EUKOR_VESSELS.

Note on use: eukor.com/robots.txt does not disallow these paths and no auth or
bot protection is involved, but EUKOR's Terms of Use grant *non-commercial* use
only. Fine for personal tracking; get sign-off before any commercial use.
"""

import json
import time
from datetime import date
from html.parser import HTMLParser
from pathlib import Path

import httpx

from .port_scraper import EUKOR_VESSELS

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SCHEDULE_FILE = DATA_DIR / "vessel_schedule.json"

BASE = "https://m.eclipsocean.com/ek/otsd/homepage/01_ShippingService"
SEARCH_URL = f"{BASE}/otsdPortScheduleSearch.do"
FORM_URL = f"{BASE}/otsdPortSchedule.do"

HEADERS = {
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": FORM_URL,
    "User-Agent": "Mozilla/5.0",
}

# Discharge ports for the NL/BE market. Rozenburg and Europoort have no LOCODE
# of their own — they are part of the Rotterdam complex and arrive under NLRTM.
NW_EUROPE_PORTS = ["NLRTM", "BEANR", "BEZEE", "NLVLI"]

# Korean load ports the Kia car carriers sail from. Not exhaustive: the vessels
# also run non-Korean origins, so a sweep finding nothing is not proof that a
# vessel is not Europe-bound. Widen this if a run keeps coming back empty.
KR_LOAD_PORTS = ["KRPTK", "KRUSN", "KRKAN", "KRMAS", "KRPUS"]

WATCHED_VESSELS = {name.upper() for name, _imo in EUKOR_VESSELS.values()}

# Politeness delay between POSTs; a full sweep is load x discharge requests.
REQUEST_DELAY = 0.5


class _ScheduleTableParser(HTMLParser):
    """Collect <tr> rows as lists of cell text from the results fragment.

    Uses the stdlib parser rather than BeautifulSoup so the container picks up
    no new dependency. Cells are read positionally, not by header label, since
    the fragment's headers span two rows and are not tied to the data columns.
    """

    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._cell is not None and name == "nbsp":
            self._cell.append(" ")


def _split_voyage(vessel_voyage: str) -> tuple[str, str, str]:
    """'ELEKTRA V-WE623' -> ('ELEKTRA', 'V-WE623', 'WE').

    The service code is not always WE: Zeebrugge calls turn up as V-IF607. The
    endpoint cannot filter on it, so parse it rather than assume it.
    """
    if " V-" not in vessel_voyage:
        return vessel_voyage.strip(), "", ""
    name, _, code = vessel_voyage.rpartition(" V-")
    service = code[:2] if len(code) >= 2 and code[:2].isalpha() else ""
    return name.strip(), f"V-{code}".strip(), service


def _is_date(value: str) -> bool:
    return len(value) == 10 and value[4] == "-" and value[:4].isdigit()


def _parse_rows(html: str) -> tuple[list[dict], int]:
    """Parse the results fragment. Returns (voyages, unparsed_row_count).

    A voyage that loads at more than one port emits continuation rows: nine
    cells as usual, but with Vessel/Voyage, Discharge and ETA blank, e.g.
        ['', 'PYEONGTAEK', '2026-07-31', 'E', 'A', '', '', '', '']
    Those carry a real extra loading call that inherits the previous row's
    voyage and arrival, so they are attached to that voyage rather than
    dropped. Genuinely unrecognised rows are counted, not ignored — otherwise
    a layout change would quietly yield nothing at all.
    """
    parser = _ScheduleTableParser()
    parser.feed(html)

    voyages: list[dict] = []
    unparsed = 0

    for cells in parser.rows:
        # Data rows carry 9 cells; header and spacer rows are shorter or empty.
        if len(cells) < 7:
            if any(c.strip() for c in cells):
                unparsed += 1
            continue

        vessel_voyage = cells[0].strip()
        load_port, etd = cells[1].strip(), cells[2].strip()
        discharge_port, eta = cells[5].strip(), cells[6].strip()

        # Continuation row: an extra loading call for the voyage above.
        if not vessel_voyage and not eta:
            if voyages and load_port and _is_date(etd):
                voyages[-1].setdefault("additional_loads", []).append(
                    {"load_port": load_port, "etd": etd}
                )
            else:
                unparsed += 1
            continue

        # Guard against header rows that happen to be wide enough.
        if not _is_date(eta):
            unparsed += 1
            continue

        name, voyage, service = _split_voyage(vessel_voyage)
        voyages.append(
            {
                "vessel": name,
                "voyage": voyage,
                "service": service,
                "load_port": load_port,
                "etd": etd,
                "discharge_port": discharge_port,
                "eta": eta,
                "watched": name.upper() in WATCHED_VESSELS,
            }
        )

    return voyages, unparsed


def search(client: httpx.Client, dep_port: str, arr_port: str, ndate: str) -> list[dict]:
    """One port-to-port query. `ndate` is a YYYYMMDD cutoff on *arrival* date."""
    resp = client.post(
        SEARCH_URL,
        headers=HEADERS,
        data={"dep_port": dep_port, "arr_port": arr_port, "nDate": ndate},
    )
    resp.raise_for_status()
    voyages, skipped = _parse_rows(resp.text)
    if skipped:
        print(f"    note: {skipped} unparsed row(s) for {dep_port}->{arr_port}")
    return voyages


def scrape_all(
    load_ports: list[str] | None = None,
    discharge_ports: list[str] | None = None,
    since: str | None = None,
) -> dict:
    """Sweep load x discharge ports and collect Europe-bound voyages."""
    load_ports = load_ports or KR_LOAD_PORTS
    discharge_ports = discharge_ports or NW_EUROPE_PORTS
    ndate = since or date.today().strftime("%Y%m%d")

    all_voyages: list[dict] = []
    seen: set[tuple] = set()
    errors: list[str] = []

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        for arr in discharge_ports:
            for dep in load_ports:
                try:
                    for v in search(client, dep, arr, ndate):
                        # The same voyage shows up under several load ports.
                        key = (v["vessel"], v["voyage"], v["discharge_port"], v["eta"])
                        if key not in seen:
                            seen.add(key)
                            all_voyages.append(v)
                except Exception as e:
                    errors.append(f"{dep}->{arr}: {e}")
                    print(f"  {dep}->{arr}: error {e}")
                time.sleep(REQUEST_DELAY)

    all_voyages.sort(key=lambda v: (v["eta"], v["vessel"]))
    watched = [v for v in all_voyages if v["watched"]]

    print(f"  {len(all_voyages)} Europe-bound voyage(s), {len(watched)} on the watch list")
    if all_voyages and not watched:
        # Expected often enough to be worth saying plainly: the watched ships
        # may be between voyages or loading outside the swept origins.
        print("  (no watched vessels found — they may be on non-Korean origins)")

    results = {
        "fetched_at": date.today().isoformat(),
        "query": {"load_ports": load_ports, "discharge_ports": discharge_ports, "since": ndate},
        "errors": errors,
        "voyages": all_voyages,
        "watched": watched,
    }

    SCHEDULE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_FILE.write_text(json.dumps(results, indent=2))
    return results


def upcoming_arrivals() -> list[tuple[str, str, str, str]]:
    """Cached watched arrivals as (vessel_voyage, port, date, source) tuples.

    Matches the shape of alerts.SHIPS_DETAILED so the two can be merged. Reads
    the cached file rather than the network: this feeds the alert path, which
    runs before reports precisely so a slow or failing fetch cannot delay it.
    """
    try:
        data = json.loads(SCHEDULE_FILE.read_text())
    except (OSError, json.JSONDecodeError):
        return []

    arrivals = []
    for v in data.get("watched", []):
        label = f"{v['vessel']} {v['voyage']}".strip()
        # "Rotterdam, Netherlands" -> "Rotterdam", to match the hand-kept entries.
        port = v.get("discharge_port", "").split(",")[0].strip()
        arrivals.append((label, port, v.get("eta", ""), "eukor"))
    return arrivals


if __name__ == "__main__":
    print("Fetching EUKOR schedules for NW Europe...")
    scrape_all()
    print(f"Saved to {SCHEDULE_FILE}")
