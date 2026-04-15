"""Track EUKOR car carrier vessels via aisstream.io AIS WebSocket API.

Requires an API key from https://aisstream.io (free registration).
Set via env var AISSTREAM_API_KEY or --api-key flag.
"""

import asyncio
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
POSITIONS_FILE = DATA_DIR / "vessel_positions.json"
ARRIVALS_FILE = DATA_DIR / "vessel_arrivals.json"

# EUKOR vessels: MMSI → name
VESSELS = {
    "257887000": "NOCC PACIFIC",
    "265491000": "MIGNON",
    "259318000": "NOCC ADRIATIC",
    "538005232": "MORNING CAPO",
    "370808000": "MORNING LYNN",
    "311697000": "MORNING CALM",
}

# Port bounding boxes: (min_lat, min_lon, max_lat, max_lon)
PORTS = {
    "Rotterdam": (51.85, 3.90, 52.02, 4.55),
    "Antwerp": (51.15, 4.20, 51.40, 4.50),
}


def _in_port(lat: float, lon: float) -> str | None:
    """Return port name if coordinates fall within a port area, else None."""
    for name, (min_lat, min_lon, max_lat, max_lon) in PORTS.items():
        if min_lat <= lat <= max_lat and min_lon <= lon <= max_lon:
            return name
    return None


def _load_json(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text())
    return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2))


async def track_vessels(api_key: str, duration: int = 120) -> dict:
    """Connect to aisstream.io, collect vessel positions for *duration* seconds.

    Returns dict of {mmsi: {name, lat, lon, speed, heading, port, timestamp}}.
    """
    try:
        import websockets
    except ImportError:
        print("ERROR: 'websockets' package required. Install with: uv pip install websockets")
        sys.exit(1)

    positions = _load_json(POSITIONS_FILE)
    arrivals = _load_json(ARRIVALS_FILE)
    mmsi_list = list(VESSELS.keys())

    subscribe_msg = json.dumps(
        {
            "APIKey": api_key,
            "BoundingBoxes": [[[-90, -180], [90, 180]]],
            "FiltersShipMMSI": mmsi_list,
            "FilterMessageTypes": ["PositionReport"],
        }
    )

    print(f"Connecting to aisstream.io (listening for {duration}s)...")
    print(
        "NOTE: aisstream.io has known intermittent outages (github.com/aisstream/aisstream/issues/15)"
    )
    received = 0

    try:
        async with websockets.connect(
            "wss://stream.aisstream.io/v0/stream",
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            await ws.send(subscribe_msg)

            async def listen():
                nonlocal received
                async for raw in ws:
                    msg = json.loads(raw)
                    meta = msg.get("MetaData", {})
                    mmsi = str(meta.get("MMSI", ""))
                    if mmsi not in VESSELS:
                        continue

                    pos = msg.get("Message", {}).get("PositionReport", {})
                    lat = pos.get("Latitude", meta.get("latitude"))
                    lon = pos.get("Longitude", meta.get("longitude"))
                    if lat is None or lon is None:
                        continue

                    speed = pos.get("Sog", 0)
                    heading = pos.get("TrueHeading", 0)
                    port = _in_port(lat, lon)
                    now = datetime.now(UTC).isoformat()

                    name = VESSELS[mmsi]
                    positions[mmsi] = {
                        "name": name,
                        "lat": lat,
                        "lon": lon,
                        "speed_knots": speed,
                        "heading": heading,
                        "port": port,
                        "timestamp": now,
                    }
                    received += 1
                    status = f"in {port}" if port else f"at sea ({lat:.2f}, {lon:.2f})"
                    print(f"  {name}: {status}  speed={speed:.1f}kn")

                    # Detect new arrival
                    if port:
                        arrival_key = f"{mmsi}_{port}"
                        prev = arrivals.get(arrival_key)
                        if not prev or prev.get("departed"):
                            arrivals[arrival_key] = {
                                "name": name,
                                "mmsi": mmsi,
                                "port": port,
                                "arrived": now,
                                "departed": None,
                            }
                            print(f"  *** NEW ARRIVAL: {name} at {port}! ***")

            try:
                await asyncio.wait_for(listen(), timeout=duration)
            except TimeoutError:
                pass

    except Exception as e:
        print(f"WebSocket error: {e}")

    _save_json(POSITIONS_FILE, positions)
    _save_json(ARRIVALS_FILE, arrivals)
    if received == 0:
        print("\nNo AIS data received. Stream may be down (see aisstream/aisstream#15).")
    else:
        print(f"\nReceived {received} position updates for {len(positions)} vessels.")
    return positions


def run(api_key: str | None = None, duration: int = 120) -> dict:
    """Entry point: resolve API key and run the tracker."""
    key = api_key or os.environ.get("AISSTREAM_API_KEY")
    if not key:
        print(
            "No API key. Set AISSTREAM_API_KEY env var or pass --api-key.\n"
            "Get a free key at https://aisstream.io"
        )
        sys.exit(1)
    return asyncio.run(track_vessels(key, duration))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Track EUKOR vessels via AIS")
    parser.add_argument("--api-key", help="aisstream.io API key")
    parser.add_argument(
        "--duration", type=int, default=120, help="Seconds to listen (default: 120)"
    )
    args = parser.parse_args()
    run(args.api_key, args.duration)
