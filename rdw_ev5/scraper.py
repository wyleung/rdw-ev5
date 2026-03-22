"""Fetch Kia EV5 registrations from the RDW SODA API."""

import httpx

API_URL = "https://opendata.rdw.nl/resource/m9d7-ebf2.json"

FIELDS = [
    "kenteken",
    "catalogusprijs",
    "registratie_datum_goedkeuring_afschrijvingsmoment_bpm_dt",
    "typegoedkeuringsnummer",
    "datum_tenaamstelling",
    "eerste_kleur",
    "handelsbenaming",
    "uitvoering",
]

QUERY = """\
SELECT {fields}
WHERE caseless_one_of(`merk`, "Kia")
  AND caseless_one_of(`handelsbenaming`, "Ev5")
ORDER BY `kenteken` DESC
LIMIT {limit} OFFSET {offset}\
"""


def fetch_all(batch_size: int = 1000) -> list[dict]:
    """Fetch all Kia EV5 records, paginating through the API."""
    fields = ", ".join(f"`{f}`" for f in FIELDS)
    all_records: list[dict] = []
    offset = 0

    with httpx.Client(timeout=30) as client:
        while True:
            query = QUERY.format(fields=fields, limit=batch_size, offset=offset)
            resp = client.get(API_URL, params={"$query": query})
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            all_records.extend(batch)
            if len(batch) < batch_size:
                break
            offset += batch_size

    return all_records
