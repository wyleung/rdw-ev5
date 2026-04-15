"""Generate HTML report: daily Korean-built Kia registrations vs EUKOR ship arrivals."""

import json
import sqlite3
from collections import defaultdict
from datetime import date
from pathlib import Path

from .alerts import SHIPS

REPORTS_DIR = Path(__file__).resolve().parent.parent / "data" / "reports"

# Korean-built models (shipped by EUKOR from Pyeongtaek/Gunsan/Masan/Ulsan)
KR_MODELS = ["EV2", "EV3", "EV4", "EV5", "EV6", "EV9", "PV5", "NIRO", "SORENTO"]

MODEL_COLORS = {
    "EV2": "#06b6d4",  # cyan
    "EV3": "#3b82f6",  # blue
    "EV4": "#8b5cf6",  # violet
    "EV5": "#ef4444",  # red
    "EV6": "#f59e0b",  # amber
    "EV9": "#10b981",  # emerald
    "PV5": "#ec4899",  # pink
    "NIRO": "#6366f1",  # indigo
    "SORENTO": "#84cc16",  # lime
}


def _query_daily_kr_models(conn: sqlite3.Connection) -> tuple[list[str], dict]:
    """Return (sorted_dates, {model: {date: count}}) for Korean-built models from 2026."""
    placeholders = ",".join("?" for _ in KR_MODELS)
    rows = conn.execute(
        f"""
        SELECT substr(datum_eerste_toelating, 1, 8) as d,
               UPPER(handelsbenaming) as model, COUNT(*) as n
        FROM vehicles
        WHERE datum_eerste_toelating IS NOT NULL
          AND datum_eerste_toelating >= '20260101'
          AND UPPER(handelsbenaming) IN ({placeholders})
        GROUP BY d, model
        ORDER BY d
        """,
        KR_MODELS,
    ).fetchall()

    data: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    all_dates_set: set[str] = set()
    for d_raw, model, n in rows:
        d = f"{d_raw[:4]}-{d_raw[4:6]}-{d_raw[6:8]}"
        data[model][d] += n
        all_dates_set.add(d)

    all_dates = sorted(all_dates_set)
    return all_dates, dict(data)


def _build_daily_series(
    data: dict[str, dict[str, int]], all_dates: list[str]
) -> dict[str, list[int]]:
    """Align per-model daily counts to the full date list."""
    result = {}
    for model in KR_MODELS:
        if model in data:
            result[model] = [data[model].get(d, 0) for d in all_dates]
    return result


def generate_ship_report(conn: sqlite3.Connection, output_dir: Path = REPORTS_DIR) -> Path:
    today = date.today()
    today_str = today.isoformat()
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"ships-{today_str}.html"

    all_dates, model_data = _query_daily_kr_models(conn)
    daily_series = _build_daily_series(model_data, all_dates)

    total_kr = sum(sum(v) for v in daily_series.values())

    # Build Chart.js datasets (stacked bars)
    datasets = []
    for model in KR_MODELS:
        if model not in daily_series:
            continue
        color = MODEL_COLORS.get(model, "#94a3b8")
        datasets.append(
            {
                "label": model,
                "data": daily_series[model],
                "backgroundColor": color,
                "borderColor": color,
                "borderWidth": 1,
            }
        )

    # Ship arrival annotations
    ship_annotations = {}
    for i, (name, arrival) in enumerate(SHIPS):
        short_name = name.split(" V-")[0] if " V-" in name else name
        ship_annotations[f"ship{i}"] = {
            "type": "line",
            "xMin": arrival,
            "xMax": arrival,
            "borderColor": "#f97316",
            "borderWidth": 2,
            "borderDash": [6, 4],
            "label": {
                "display": True,
                "content": short_name,
                "position": "start",
                "backgroundColor": "rgba(249,115,22,0.85)",
                "color": "#fff",
                "font": {"size": 11, "weight": "bold"},
                "padding": 4,
                "rotation": -90,
            },
        }

    html = _render_html(today_str, total_kr, all_dates, datasets, ship_annotations)
    output_path.write_text(html)
    return output_path


def _render_html(
    today: str,
    total_kr: int,
    all_dates: list[str],
    datasets: list[dict],
    ship_annotations: dict,
) -> str:
    return f"""\
<!DOCTYPE html>
<html lang="en" class="dark">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Kia Ship Arrivals &mdash; {today}</title>
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config = {{ darkMode: 'class' }}</script>
<link href="https://cdn.jsdelivr.net/npm/flowbite@2/dist/flowbite.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3"></script>
</head>
<body class="bg-white dark:bg-gray-900 h-screen flex flex-col">
<header class="flex items-center gap-4 px-5 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shrink-0">
  <h1 class="text-base font-semibold text-gray-900 dark:text-white">Kia EUKOR Ship Arrivals vs Registrations</h1>
  <span class="text-sm text-gray-500 dark:text-gray-400">{today} &middot; {total_kr:,} Korean-built vehicles registered</span>
  <button onclick="toggleTheme()" class="ml-auto p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700" aria-label="Toggle theme">
    <svg class="w-5 h-5 hidden dark:block" fill="currentColor" viewBox="0 0 20 20">
      <path fill-rule="evenodd" clip-rule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"></path>
    </svg>
    <svg class="w-5 h-5 block dark:hidden" fill="currentColor" viewBox="0 0 20 20">
      <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"></path>
    </svg>
  </button>
</header>
<div class="flex-1 relative p-4 min-h-0">
  <canvas id="shipChart" class="absolute inset-4"></canvas>
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

const dates = {json.dumps(all_dates)};
const datasets = {json.dumps(datasets)};
const shipAnnotations = {json.dumps(ship_annotations)};

const chart = new Chart(document.getElementById('shipChart'), {{
  type: 'bar',
  data: {{ labels: dates, datasets: datasets }},
  options: {{
    responsive: true,
    maintainAspectRatio: false,
    plugins: {{
      title: {{
        display: true,
        text: 'Daily Korean-built Kia registrations (stacked) with EUKOR ship arrivals',
        color: textColor,
        font: {{ size: 14 }}
      }},
      legend: {{
        labels: {{ color: textColor }}
      }},
      tooltip: {{
        mode: 'index',
        callbacks: {{
          footer: function(items) {{
            const total = items.reduce((s, i) => s + i.parsed.y, 0);
            return 'Total: ' + total;
          }}
        }}
      }},
      annotation: {{
        annotations: shipAnnotations
      }}
    }},
    scales: {{
      x: {{
        stacked: true,
        title: {{ display: true, text: 'Registration date (datum_eerste_toelating)', color: textColor }},
        ticks: {{
          color: textColor,
          maxRotation: 90,
          autoSkip: true,
          maxTicksLimit: 40
        }},
        grid: {{ color: gridColor }}
      }},
      y: {{
        stacked: true,
        title: {{ display: true, text: 'Vehicles registered', color: textColor }},
        ticks: {{ color: textColor }},
        grid: {{ color: gridColor }},
        beginAtZero: true
      }}
    }}
  }}
}});

function toggleTheme() {{
  document.documentElement.classList.toggle('dark');
  const {{ text, grid }} = themeColors();
  textColor = text; gridColor = grid;
  chart.options.plugins.title.color = text;
  chart.options.plugins.legend.labels.color = text;
  ['x', 'y'].forEach(ax => {{
    chart.options.scales[ax].title.color = text;
    chart.options.scales[ax].ticks.color = text;
    chart.options.scales[ax].grid.color = grid;
  }});
  chart.update();
}}
</script>
</body>
</html>
"""
