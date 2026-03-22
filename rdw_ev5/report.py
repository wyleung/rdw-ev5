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
charts['{canvas_id}'] = new Chart(document.getElementById('{canvas_id}'), {{
  type: 'line',
  data: {{ labels: {dates_var}, datasets: {datasets_var} }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      title: {{ display: true, text: '{title}', color: textColor }},
      legend: {{ labels: {{ color: textColor }} }}
    }},
    scales: {{
      x: {{
        title: {{ display: true, text: 'Date', color: textColor }},
        ticks: {{ color: textColor }},
        grid: {{ color: gridColor }}
      }},
      y: {{
        title: {{ display: true, text: 'Cumulative vehicles', color: textColor }},
        ticks: {{ color: textColor }},
        grid: {{ color: gridColor }},
        beginAtZero: true
      }}
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
<html lang="en" class="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kia EV5 NL Registrations &mdash; {today}</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config = {{ darkMode: 'class' }}</script>
<link href="https://cdn.jsdelivr.net/npm/flowbite@2/dist/flowbite.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
</head>
<body class="bg-white dark:bg-gray-900 h-screen flex flex-col">
<header class="flex items-center gap-4 px-5 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shrink-0">
  <h1 class="text-base font-semibold text-gray-900 dark:text-white">Kia EV5 Registrations in the Netherlands</h1>
  <span class="text-sm text-gray-500 dark:text-gray-400">{today} &middot; {total} vehicles tracked</span>
  <button onclick="toggleTheme()" class="ml-auto p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700" aria-label="Toggle theme">
    <svg class="w-5 h-5 hidden dark:block" fill="currentColor" viewBox="0 0 20 20">
      <path fill-rule="evenodd" clip-rule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"></path>
    </svg>
    <svg class="w-5 h-5 block dark:hidden" fill="currentColor" viewBox="0 0 20 20">
      <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"></path>
    </svg>
  </button>
</header>
<div class="flex-1 grid grid-cols-2 grid-rows-2 min-h-0">
  <div class="relative p-2 border border-gray-100 dark:border-gray-700 dark:bg-gray-900"><canvas id="allColor" class="absolute inset-2"></canvas></div>
  <div class="relative p-2 border border-gray-100 dark:border-gray-700 dark:bg-gray-900"><canvas id="monthColor" class="absolute inset-2"></canvas></div>
  <div class="relative p-2 border border-gray-100 dark:border-gray-700 dark:bg-gray-900"><canvas id="allPrice" class="absolute inset-2"></canvas></div>
  <div class="relative p-2 border border-gray-100 dark:border-gray-700 dark:bg-gray-900"><canvas id="monthPrice" class="absolute inset-2"></canvas></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/flowbite@2/dist/flowbite.min.js"></script>
<script>
function isDark() {{ return document.documentElement.classList.contains('dark'); }}
function themeColors() {{
  return isDark()
    ? {{ text: '#9ca3af', grid: '#374151' }}
    : {{ text: '#374151', grid: '#e5e7eb' }};
}}
let {{ text: textColor, grid: gridColor }} = themeColors();

const charts = {{}};

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

function toggleTheme() {{
  document.documentElement.classList.toggle('dark');
  const {{ text, grid }} = themeColors();
  Object.values(charts).forEach(c => {{
    c.options.plugins.title.color = text;
    c.options.plugins.legend.labels.color = text;
    ['x', 'y'].forEach(ax => {{
      c.options.scales[ax].title.color = text;
      c.options.scales[ax].ticks.color = text;
      c.options.scales[ax].grid.color = grid;
    }});
    c.update();
  }});
}}
</script>
</body>
</html>
"""
