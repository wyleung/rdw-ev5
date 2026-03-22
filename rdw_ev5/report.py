"""Generate HTML report with cumulative registration charts."""

import json
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path

REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "reports"

# Map Dutch color names to CSS colors
COLOR_MAP = {
    "BLAUW": "#1f77b4",
    "GRIJS": "#7f7f7f",
    "GROEN": "#2ca02c",
    "ZWART": "#1a1a1a",
    "WIT": "#d4d4d4",
    "ROOD": "#d62728",
    "BRUIN": "#8c564b",
    "GEEL": "#ffe119",
    "ORANJE": "#ff7f0e",
    "PAARS": "#9467bd",
}

PRICE_PALETTE = [
    "#e6194b",
    "#3cb44b",
    "#4363d8",
    "#f58231",
    "#911eb4",
    "#42d4f4",
    "#f032e6",
    "#bfef45",
    "#fabebe",
    "#469990",
]


def _query_by_date_and_group(conn: sqlite3.Connection, group_col: str) -> dict:
    """Return {group_value: {date: count}} from the vehicles table."""
    rows = conn.execute(
        f"""
        SELECT substr(bpm_datum, 1, 10) as d, {group_col}, count(*)
        FROM vehicles
        WHERE bpm_datum IS NOT NULL
        GROUP BY d, {group_col}
        ORDER BY d
        """
    ).fetchall()
    data: dict[str, dict[str, int]] = defaultdict(dict)
    for d, group, count in rows:
        data[group][d] = count
    return data


def _build_cumulative(data: dict, all_dates: list[str]) -> dict[str, list[int]]:
    """Convert per-day counts to cumulative series aligned to all_dates."""
    result = {}
    for group, date_counts in sorted(data.items()):
        cumulative = []
        total = 0
        for d in all_dates:
            total += date_counts.get(d, 0)
            cumulative.append(total)
        result[str(group)] = cumulative
    return result


def _get_all_dates(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT substr(bpm_datum, 1, 10) as d
        FROM vehicles
        WHERE bpm_datum IS NOT NULL
        ORDER BY d
        """
    ).fetchall()
    return [r[0] for r in rows]


def _color_for(kleur: str) -> str:
    return COLOR_MAP.get(kleur.upper(), "#bcbd22")


HIGHLIGHT_COLORS = {"WIT", "ROOD"}


def _make_color_datasets(series: dict[str, list[int]]) -> list[dict]:
    datasets = []
    for kleur, values in series.items():
        highlight = kleur.upper() in HIGHLIGHT_COLORS
        datasets.append(
            {
                "label": kleur.capitalize(),
                "data": values,
                "borderColor": _color_for(kleur),
                "backgroundColor": _color_for(kleur),
                "borderWidth": 4 if highlight else 2,
                "pointRadius": 2 if highlight else 1,
                "fill": False,
            }
        )
    return datasets


def _make_price_datasets(series: dict[str, list[int]]) -> list[dict]:
    datasets = []
    for i, (price, values) in enumerate(series.items()):
        color = PRICE_PALETTE[i % len(PRICE_PALETTE)]
        datasets.append(
            {
                "label": f"\u20ac{price}",
                "data": values,
                "borderColor": color,
                "backgroundColor": color,
                "borderWidth": 2,
                "pointRadius": 1,
                "fill": False,
            }
        )
    return datasets


def generate_report(conn: sqlite3.Connection, output_dir: Path = REPORTS_DIR) -> Path:
    today = date.today()
    today_str = today.isoformat()
    month_prefix = today_str[:7]  # e.g. "2026-03"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{today_str}.html"

    all_dates = _get_all_dates(conn)
    month_dates = [d for d in all_dates if d.startswith(month_prefix)]

    color_data = _query_by_date_and_group(conn, "eerste_kleur")
    price_data = _query_by_date_and_group(conn, "catalogusprijs")

    # All-time cumulative
    all_color_series = _build_cumulative(color_data, all_dates)
    all_price_series = _build_cumulative(price_data, all_dates)

    # Current-month cumulative
    month_color_series = _build_cumulative(color_data, month_dates)
    month_price_series = _build_cumulative(price_data, month_dates)

    total = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
    all_gross = conn.execute("SELECT COALESCE(SUM(catalogusprijs), 0) FROM vehicles").fetchone()[0]
    month_gross = conn.execute(
        "SELECT COALESCE(SUM(catalogusprijs), 0) FROM vehicles WHERE bpm_datum LIKE ?",
        (month_prefix + "%",),
    ).fetchone()[0]

    html = _render_html(
        today_str,
        month_prefix,
        total,
        all_gross,
        month_gross,
        all_dates,
        all_color_series,
        all_price_series,
        month_dates,
        month_color_series,
        month_price_series,
    )
    output_path.write_text(html)
    return output_path


def _chart_js(canvas_id: str, dates_var: str, datasets_var: str, title: str) -> str:
    return f"""
new Chart(document.getElementById('{canvas_id}'), {{
  type: 'line',
  data: {{ labels: {dates_var}, datasets: {datasets_var} }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{ title: {{ display: true, text: '{title}' }} }},
    scales: {{
      x: {{ title: {{ display: true, text: 'Date' }} }},
      y: {{ title: {{ display: true, text: 'Cumulative vehicles' }}, beginAtZero: true }}
    }}
  }}
}});"""


def _fmt_eur(amount: int) -> str:
    """Format integer as €1.234.567."""
    s = f"{amount:,}".replace(",", ".")
    return f"\u20ac{s}"


def _render_html(
    today: str,
    month: str,
    total: int,
    all_gross: int,
    month_gross: int,
    all_dates: list[str],
    all_color_series: dict[str, list[int]],
    all_price_series: dict[str, list[int]],
    month_dates: list[str],
    month_color_series: dict[str, list[int]],
    month_price_series: dict[str, list[int]],
) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kia EV5 NL Registrations &mdash; {today}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: system-ui, sans-serif; height: 100vh; display: flex; flex-direction: column; }}
  header {{ padding: 0.8rem 1.2rem; border-bottom: 1px solid #ddd; }}
  header h1 {{ font-size: 1.2rem; display: inline; }}
  header .meta {{ color: #666; font-size: 0.85rem; margin-left: 1rem; }}
  .grid {{ flex: 1; display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr; gap: 0; min-height: 0; }}
  .cell {{ position: relative; padding: 0.5rem; border: 1px solid #eee; }}
  .cell canvas {{ position: absolute; inset: 0.5rem; }}
</style>
</head>
<body>
<header>
  <h1>Kia EV5 Registrations in the Netherlands</h1>
  <span class="meta">{today} &middot; {total} vehicles tracked</span>
</header>
<div class="grid">
  <div class="cell"><canvas id="allColor"></canvas></div>
  <div class="cell"><canvas id="monthColor"></canvas></div>
  <div class="cell"><canvas id="allPrice"></canvas></div>
  <div class="cell"><canvas id="monthPrice"></canvas></div>
</div>
<script>
const allDates = {json.dumps(all_dates)};
const monthDates = {json.dumps(month_dates)};

const allColorDs = {json.dumps(_make_color_datasets(all_color_series))};
const monthColorDs = {json.dumps(_make_color_datasets(month_color_series))};
const allPriceDs = {json.dumps(_make_price_datasets(all_price_series))};
const monthPriceDs = {json.dumps(_make_price_datasets(month_price_series))};

{_chart_js("allColor", "allDates", "allColorDs", f"By color — all time (gross {_fmt_eur(all_gross)})")}
{_chart_js("monthColor", "monthDates", "monthColorDs", f"By color — {month} (gross {_fmt_eur(month_gross)} — {month_gross * 100 / all_gross:.1f}% of total)")}
{_chart_js("allPrice", "allDates", "allPriceDs", f"By catalog price — all time (gross {_fmt_eur(all_gross)})")}
{_chart_js("monthPrice", "monthDates", "monthPriceDs", f"By catalog price — {month} (gross {_fmt_eur(month_gross)} — {month_gross * 100 / all_gross:.1f}% of total)")}
</script>
</body>
</html>
"""
