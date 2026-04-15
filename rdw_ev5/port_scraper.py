"""Scrape vessel port call history from MyShipTracking.com."""

import json
import re
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PORT_CALLS_FILE = DATA_DIR / "vessel_port_calls.json"

# EUKOR car carriers: MMSI → (name, IMO)
EUKOR_VESSELS = {
    "257887000": ("NOCC PACIFIC", 1041831),
    "265491000": ("MIGNON", 9189251),
    "259318000": ("NOCC ADRIATIC", 1041843),
    "538005232": ("MORNING CAPO", 9663295),
    "370808000": ("MORNING LYNN", 9383429),
    "311697000": ("MORNING CALM", 9285615),
}

# Ports where Kia vehicles are unloaded for NL/BE market
NL_BE_PORTS = {
    "ROTTERDAM",
    "ROZENBURG",
    "EUROPOORT",
    "ANTWERP",
    "ANTWERPEN",
    "ZEEBRUGGE",
    "VLISSINGEN",
}


def _extract_port_calls(html: str) -> list[dict]:
    """Parse port call table from a MyShipTracking vessel page."""
    calls = []
    tables = re.findall(r"<table[^>]*>(.*?)</table>", html, re.DOTALL)
    for t in tables:
        if "Time In Port" not in t and "Time in Port" not in t:
            continue
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", t, re.DOTALL)
        for row in rows[1:]:  # skip header
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.DOTALL)
            if len(cells) < 3:
                continue
            port = re.sub(r"<[^>]+>", "", cells[0]).strip()

            def get_utc(cell_html: str) -> str:
                m = re.search(r"'>(\d{4}-\d{2}-\d{2})\s*<b>(\d{2}:\d{2})</b>", cell_html)
                return f"{m.group(1)} {m.group(2)}" if m else ""

            calls.append(
                {"port": port, "arrival": get_utc(cells[1]), "departure": get_utc(cells[2])}
            )
    return calls


def scrape_all(vessels: dict | None = None) -> dict:
    """Scrape port call history for all vessels. Returns {name: {mmsi, port_calls}}."""
    vessels = vessels or EUKOR_VESSELS
    results = {}

    with httpx.Client(
        timeout=15, follow_redirects=True, headers={"User-Agent": "Mozilla/5.0"}
    ) as client:
        for mmsi, (name, _imo) in vessels.items():
            slug = name.lower().replace(" ", "-")
            url = f"https://www.myshiptracking.com/vessels/{slug}-mmsi-{mmsi}"
            try:
                resp = client.get(url)
                calls = _extract_port_calls(resp.text)
                nl_be = [c for c in calls if c["port"].upper() in NL_BE_PORTS]
                results[name] = {"mmsi": mmsi, "port_calls": calls, "nl_be_arrivals": nl_be}
                print(f"  {name}: {len(calls)} calls, {len(nl_be)} NL/BE")
            except Exception as e:
                print(f"  {name}: error {e}")

    PORT_CALLS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PORT_CALLS_FILE.write_text(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    print("Scraping MyShipTracking for EUKOR vessel port calls...")
    scrape_all()
    print(f"Saved to {PORT_CALLS_FILE}")
