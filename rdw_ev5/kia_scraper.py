"""Fetch all Kia registrations from the RDW SODA API since a given date."""

import httpx

API_URL = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"

FIELDS = [
    "kenteken",
    "merk",
    "handelsbenaming",
    "catalogusprijs",
    "registratie_datum_goedkeuring_afschrijvingsmoment_bpm_dt",
    "typegoedkeuringsnummer",
    "datum_tenaamstelling",
    "datum_eerste_toelating",
    "eerste_kleur",
    "tweede_kleur",
    "uitvoering",
    "variant",
    "inrichting",
    "massa_rijklaar",
    "aantal_zitplaatsen",
    "aantal_deuren",
    "bruto_bpm",
]

QUERY = """\
SELECT {fields}
WHERE caseless_one_of(`merk`, "Kia")
  AND `datum_eerste_toelating_dt` >= "{since}T00:00:00.000"
ORDER BY `kenteken` ASC
LIMIT {limit} OFFSET {offset}\
"""


def fetch_all(since: str = "2025-01-01", batch_size: int = 1000) -> list[dict]:
    """Fetch all Kia records from *since* date, paginating through the API.

    Args:
        since: ISO date string, e.g. "2025-01-01".
        batch_size: records per API call (max 1000).
    """
    fields = ", ".join(f"`{f}`" for f in FIELDS)
    all_records: list[dict] = []
    offset = 0

    with httpx.Client(timeout=60) as client:
        while True:
            query = QUERY.format(fields=fields, since=since, limit=batch_size, offset=offset)
            resp = client.get(API_URL, params={"$query": query})
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            all_records.extend(batch)
            print(f"  fetched {len(all_records)} records ...", flush=True)
            if len(batch) < batch_size:
                break
            offset += batch_size

    return all_records
