"""FastAPI web dashboard for Kia EV5 registrations and EUKOR ship tracking."""

import json
import sqlite3
from datetime import date
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from . import db, kia_db
from .alerts import SHIPS, SHIPS_DETAILED
from .report import (
    COLOR_ORDER,
    TRIM_ORDER,
    _build_cumulative,
    _fmt_eur,
    _get_all_dates,
    _make_color_datasets,
    _make_trim_datasets,
    _query_by_date_and_color,
    _query_by_date_and_trim,
    _query_trim_color_matrix,
)
from .ship_report import KR_MODELS, MODEL_COLORS, _build_daily_series, _query_daily_kr_models

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

app = FastAPI(title="Kia EV5 NL Dashboard")


def _ev5_conn() -> sqlite3.Connection:
    return db.connect(DATA_DIR / "ev5.db")


def _kia_conn() -> sqlite3.Connection:
    return kia_db.connect(DATA_DIR / "kia.db")


# ── API endpoints ─────────────────────────────────────────────────────────────


@app.get("/api/ev5/summary")
def ev5_summary():
    conn = _ev5_conn()
    today = date.today().isoformat()
    month = today[:7]
    total = conn.execute("SELECT COUNT(*) FROM vehicles").fetchone()[0]
    all_gross = conn.execute("SELECT COALESCE(SUM(catalogusprijs),0) FROM vehicles").fetchone()[0]
    month_gross = conn.execute(
        "SELECT COALESCE(SUM(catalogusprijs),0) FROM vehicles WHERE bpm_datum LIKE ?",
        (month + "%",),
    ).fetchone()[0]
    conn.close()
    return {
        "today": today,
        "month": month,
        "total": total,
        "all_gross": all_gross,
        "month_gross": month_gross,
        "all_gross_fmt": _fmt_eur(all_gross),
        "month_gross_fmt": _fmt_eur(month_gross),
        "month_pct": round(month_gross * 100 / all_gross, 1) if all_gross else 0,
    }


@app.get("/api/ev5/charts")
def ev5_charts():
    conn = _ev5_conn()
    today = date.today().isoformat()
    month = today[:7]

    all_dates = _get_all_dates(conn)
    month_dates = [d for d in all_dates if d.startswith(month)]

    color_data = _query_by_date_and_color(conn)
    trim_data = _query_by_date_and_trim(conn)

    all_color = _build_cumulative(color_data, all_dates, COLOR_ORDER)
    all_trim = _build_cumulative(trim_data, all_dates, TRIM_ORDER)
    month_color = _build_cumulative(color_data, month_dates, COLOR_ORDER)
    month_trim = _build_cumulative(trim_data, month_dates, TRIM_ORDER)
    conn.close()

    return {
        "allDates": all_dates,
        "monthDates": month_dates,
        "allColorDs": _make_color_datasets(all_color),
        "monthColorDs": _make_color_datasets(month_color),
        "allTrimDs": _make_trim_datasets(all_trim),
        "monthTrimDs": _make_trim_datasets(month_trim),
    }


@app.get("/api/ev5/matrix")
def ev5_matrix():
    conn = _ev5_conn()
    matrix = _query_trim_color_matrix(conn)
    conn.close()
    return {
        "matrix": matrix,
        "trimOrder": TRIM_ORDER,
        "colorOrder": COLOR_ORDER,
    }


@app.get("/api/ships/daily")
def ships_daily():
    conn = _kia_conn()
    all_dates, model_data = _query_daily_kr_models(conn)
    daily_series = _build_daily_series(model_data, all_dates)
    conn.close()

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

    ship_annotations = {}
    for i, (name, arrival) in enumerate(SHIPS):
        short = name.split(" V-")[0] if " V-" in name else name
        ship_annotations[f"ship{i}"] = {
            "type": "line",
            "xMin": arrival,
            "xMax": arrival,
            "borderColor": "#f97316",
            "borderWidth": 2,
            "borderDash": [6, 4],
            "label": {
                "display": True,
                "content": short,
                "position": "start",
                "backgroundColor": "rgba(249,115,22,0.85)",
                "color": "#fff",
                "font": {"size": 11, "weight": "bold"},
                "padding": 4,
                "rotation": -90,
            },
        }

    return {
        "dates": all_dates,
        "datasets": datasets,
        "shipAnnotations": ship_annotations,
        "totalKr": sum(sum(v) for v in daily_series.values()),
    }


@app.get("/api/vessels")
def vessels():
    pos_file = DATA_DIR / "vessel_positions.json"
    arr_file = DATA_DIR / "vessel_arrivals.json"
    pc_file = DATA_DIR / "vessel_port_calls.json"
    positions = json.loads(pos_file.read_text()) if pos_file.exists() else {}
    arrivals = json.loads(arr_file.read_text()) if arr_file.exists() else {}
    port_calls = json.loads(pc_file.read_text()) if pc_file.exists() else {}
    return {
        "positions": positions,
        "arrivals": arrivals,
        "port_calls": port_calls,
        "ships": SHIPS,
        "ships_detailed": [
            {"name": n, "port": p, "date": d, "source": s} for n, p, d, s in SHIPS_DETAILED
        ],
    }


@app.post("/api/vessels/refresh")
def vessels_refresh():
    """Trigger a fresh scrape of MyShipTracking port call data."""
    from .port_scraper import scrape_all

    results = scrape_all()
    return {"status": "ok", "vessels": len(results)}


# ── HTML pages ────────────────────────────────────────────────────────────────

_HEAD = """\
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script src="https://cdn.tailwindcss.com"></script>
<script>tailwind.config = { darkMode: 'class' }</script>
<link href="https://cdn.jsdelivr.net/npm/flowbite@2/dist/flowbite.min.css" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4"></script>
<script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-annotation@3"></script>"""

_THEME_JS = """\
function isDark(){return document.documentElement.classList.contains('dark')}
function themeColors(){return isDark()?{text:'#9ca3af',grid:'#374151'}:{text:'#374151',grid:'#e5e7eb'}}
function toggleTheme(){
  document.documentElement.classList.toggle('dark');
  location.reload(); // simplest way to re-render charts with new colors
}"""

_THEME_BTN = """\
<button onclick="toggleTheme()" class="p-2 rounded-lg text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-700">
  <svg class="w-5 h-5 hidden dark:block" fill="currentColor" viewBox="0 0 20 20">
    <path fill-rule="evenodd" clip-rule="evenodd" d="M10 2a1 1 0 011 1v1a1 1 0 11-2 0V3a1 1 0 011-1zm4 8a4 4 0 11-8 0 4 4 0 018 0zm-.464 4.95l.707.707a1 1 0 001.414-1.414l-.707-.707a1 1 0 00-1.414 1.414zm2.12-10.607a1 1 0 010 1.414l-.706.707a1 1 0 11-1.414-1.414l.707-.707a1 1 0 011.414 0zM17 11a1 1 0 100-2h-1a1 1 0 100 2h1zm-7 4a1 1 0 011 1v1a1 1 0 11-2 0v-1a1 1 0 011-1zM5.05 6.464A1 1 0 106.465 5.05l-.708-.707a1 1 0 00-1.414 1.414l.707.707zm1.414 8.486l-.707.707a1 1 0 01-1.414-1.414l.707-.707a1 1 0 011.414 1.414zM4 11a1 1 0 100-2H3a1 1 0 000 2h1z"></path>
  </svg>
  <svg class="w-5 h-5 block dark:hidden" fill="currentColor" viewBox="0 0 20 20">
    <path d="M17.293 13.293A8 8 0 016.707 2.707a8.001 8.001 0 1010.586 10.586z"></path>
  </svg>
</button>"""


def _nav(active: str) -> str:
    items = [("Charts", "/"), ("Matrix", "/matrix"), ("Ships", "/ships"), ("Vessels", "/vessels")]
    links = []
    for label, href in items:
        if label == active:
            cls = "px-3 py-1.5 text-sm font-medium rounded-lg bg-blue-600 text-white"
        else:
            cls = "px-3 py-1.5 text-sm font-medium rounded-lg text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700"
        links.append(f'<a href="{href}" class="{cls}">{label}</a>')
    return " ".join(links)


def _header(title: str, subtitle: str, active: str) -> str:
    return f"""\
<header class="flex items-center gap-4 px-5 py-3 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shrink-0">
  <h1 class="text-base font-semibold text-gray-900 dark:text-white">{title}</h1>
  <span class="text-sm text-gray-500 dark:text-gray-400">{subtitle}</span>
  <div class="ml-auto flex items-center gap-2">{_nav(active)}{_THEME_BTN}</div>
</header>"""


@app.get("/", response_class=HTMLResponse)
def page_charts():
    return f"""\
<!DOCTYPE html><html lang="en" class="dark"><head>{_HEAD}
<title>Kia EV5 Dashboard</title></head>
<body class="bg-white dark:bg-gray-900 h-screen flex flex-col">
{_header("Kia EV5 Registrations NL", '<span id="meta"></span>', "Charts")}
<div id="view" class="flex-1 grid grid-cols-2 grid-rows-2 min-h-0">
  <div class="relative p-2 border border-gray-100 dark:border-gray-700"><canvas id="allColor" class="absolute inset-2"></canvas></div>
  <div class="relative p-2 border border-gray-100 dark:border-gray-700"><canvas id="monthColor" class="absolute inset-2"></canvas></div>
  <div class="relative p-2 border border-gray-100 dark:border-gray-700"><canvas id="allTrim" class="absolute inset-2"></canvas></div>
  <div class="relative p-2 border border-gray-100 dark:border-gray-700"><canvas id="monthTrim" class="absolute inset-2"></canvas></div>
</div>
<script>{_THEME_JS}
async function init() {{
  const [s, c] = await Promise.all([fetch('/api/ev5/summary').then(r=>r.json()), fetch('/api/ev5/charts').then(r=>r.json())]);
  document.getElementById('meta').textContent = s.today+' · '+s.total+' vehicles · gross '+s.all_gross_fmt;
  const {{text:textColor,grid:gridColor}} = themeColors();
  function mk(id,labels,datasets,title) {{
    new Chart(document.getElementById(id), {{
      type:'line', data:{{labels,datasets}},
      options:{{responsive:true,maintainAspectRatio:false,
        plugins:{{title:{{display:true,text:title,color:textColor}},legend:{{labels:{{color:textColor}}}}}},
        scales:{{x:{{title:{{display:true,text:'Date',color:textColor}},ticks:{{color:textColor}},grid:{{color:gridColor}}}},
                 y:{{title:{{display:true,text:'Cumulative',color:textColor}},ticks:{{color:textColor}},grid:{{color:gridColor}},beginAtZero:true}}}}
      }}
    }});
  }}
  const dark=isDark();
  function fix(ds){{ds.forEach(d=>{{const col=dark?(d.darkColor||d.lightColor):d.lightColor;if(col)d.borderColor=d.backgroundColor=col}});return ds}}
  mk('allColor',c.allDates,fix(c.allColorDs),'By color — all time (gross '+s.all_gross_fmt+')');
  mk('monthColor',c.monthDates,fix(c.monthColorDs),'By color — '+s.month+' (gross '+s.month_gross_fmt+' — '+s.month_pct+'%)');
  mk('allTrim',c.allDates,c.allTrimDs,'By trim — all time (gross '+s.all_gross_fmt+')');
  mk('monthTrim',c.monthDates,c.monthTrimDs,'By trim — '+s.month+' (gross '+s.month_gross_fmt+' — '+s.month_pct+'%)');
}}
init();
</script></body></html>"""


@app.get("/matrix", response_class=HTMLResponse)
def page_matrix():
    return f"""\
<!DOCTYPE html><html lang="en" class="dark"><head>{_HEAD}
<title>EV5 Trim × Color Matrix</title></head>
<body class="bg-white dark:bg-gray-900 h-screen flex flex-col">
{_header("Kia EV5 Trim × Color Matrix", "", "Matrix")}
<div class="flex-1 overflow-auto p-6"><table id="mt" class="w-full border-collapse text-sm"></table></div>
<script>{_THEME_JS}
const SHORT={{"Snow White Pearl":"Snow White","Ivory Silver / Gravity Gray":"Ivory / Gravity","Fusion Black":"Fusion Black","Frost Blue / Dark Ocean Blue":"Frost / Ocean Blue","Magma Red":"Magma Red","Iceberg Green":"Iceberg Green","Iceberg Green Matte":"Iceberg Matte"}};
const TH='px-4 py-3 font-semibold text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700';
const TD='px-4 py-3 text-center text-gray-800 dark:text-gray-200 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700';
const TOT='px-4 py-3 text-center font-semibold text-gray-900 dark:text-white bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700';
async function init(){{
  const d=await fetch('/api/ev5/matrix').then(r=>r.json());
  const t=document.getElementById('mt'),m=d.matrix,to=d.trimOrder,co=d.colorOrder;
  const thead=t.createTHead(),hr=thead.insertRow();
  let th=document.createElement('th');th.className=TH+' text-left';th.textContent='Trim \\\\ Kleur';hr.appendChild(th);
  co.forEach((c,i)=>{{th=document.createElement('th');th.className=TH;th.textContent=SHORT[c]||c;th.title=c;th.dataset.col=i;hr.appendChild(th)}});
  th=document.createElement('th');th.className=TH;th.textContent='Total';hr.appendChild(th);
  const tbody=t.createTBody(),ct=new Array(co.length).fill(0);let gt=0;
  to.forEach(tr=>{{const r=tbody.insertRow(),rd=m[tr]||{{}};let rt=0;
    th=document.createElement('th');th.className=TH+' text-left';th.textContent=tr;r.appendChild(th);
    co.forEach((c,i)=>{{const n=rd[c]||0;rt+=n;ct[i]+=n;const td=r.insertCell();td.className=TD;td.textContent=n||'';td.dataset.col=i}});
    gt+=rt;const td=r.insertCell();td.className=TOT;td.textContent=rt}});
  const tfoot=t.createTFoot(),fr=tfoot.insertRow();
  th=document.createElement('th');th.className=TH+' text-left';th.textContent='Total';fr.appendChild(th);
  ct.forEach((n,i)=>{{const td=fr.insertCell();td.className=TOT;td.textContent=n;td.dataset.col=i}});
  const gd=fr.insertCell();gd.className=TOT+' font-bold';gd.textContent=gt;
  const HL='rgba(59,130,246,0.12)',HC='rgba(59,130,246,0.30)';
  function clr(){{t.querySelectorAll('td,th').forEach(e=>e.style.removeProperty('background-color'))}}
  t.addEventListener('mouseover',e=>{{const c=e.target.closest('td,th');if(!c)return;clr();
    c.closest('tr').querySelectorAll('td,th').forEach(x=>x.style.backgroundColor=HL);
    const col=c.dataset.col;if(col!==undefined){{t.querySelectorAll('[data-col="'+col+'"]').forEach(x=>x.style.backgroundColor=HL);c.style.backgroundColor=HC}}}});
  t.addEventListener('mouseleave',clr);
}}
init();
</script></body></html>"""


@app.get("/ships", response_class=HTMLResponse)
def page_ships():
    return f"""\
<!DOCTYPE html><html lang="en" class="dark"><head>{_HEAD}
<title>EUKOR Ship Arrivals</title></head>
<body class="bg-white dark:bg-gray-900 h-screen flex flex-col">
{_header("EUKOR Ship Arrivals vs Registrations", '<span id="meta"></span>', "Ships")}
<div class="flex-1 relative p-4 min-h-0"><canvas id="sc" class="absolute inset-4"></canvas></div>
<script>{_THEME_JS}
async function init(){{
  const d=await fetch('/api/ships/daily').then(r=>r.json());
  document.getElementById('meta').textContent=d.totalKr.toLocaleString()+' Korean-built vehicles';
  const {{text:textColor,grid:gridColor}}=themeColors();
  new Chart(document.getElementById('sc'),{{
    type:'bar',data:{{labels:d.dates,datasets:d.datasets}},
    options:{{responsive:true,maintainAspectRatio:false,
      plugins:{{title:{{display:true,text:'Daily Korean-built Kia registrations with EUKOR ship arrivals',color:textColor,font:{{size:14}}}},
        legend:{{labels:{{color:textColor}}}},
        tooltip:{{mode:'index',callbacks:{{footer:items=>{{const t=items.reduce((s,i)=>s+i.parsed.y,0);return'Total: '+t}}}}}},
        annotation:{{annotations:d.shipAnnotations}}}},
      scales:{{x:{{stacked:true,title:{{display:true,text:'Registration date',color:textColor}},ticks:{{color:textColor,maxRotation:90,autoSkip:true,maxTicksLimit:40}},grid:{{color:gridColor}}}},
               y:{{stacked:true,title:{{display:true,text:'Vehicles',color:textColor}},ticks:{{color:textColor}},grid:{{color:gridColor}},beginAtZero:true}}}}
    }}
  }});
}}
init();
</script></body></html>"""


@app.get("/vessels", response_class=HTMLResponse)
def page_vessels():
    return f"""\
<!DOCTYPE html><html lang="en" class="dark"><head>{_HEAD}
<title>Vessel Tracker</title></head>
<body class="bg-white dark:bg-gray-900 h-screen flex flex-col">
{_header("EUKOR Vessel Tracker", "Ship arrivals at Rotterdam, Antwerp & Zeebrugge", "Vessels")}
<div class="flex-1 overflow-auto p-6">
  <div id="cards" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4"></div>
  <div class="mt-8"><h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">Ship Arrivals Timeline</h2>
    <table id="timeline" class="w-full border-collapse text-sm"></table></div>
  <div class="mt-8"><h2 class="text-lg font-semibold text-gray-900 dark:text-white mb-4">Recent Port Calls (MyShipTracking)</h2>
    <div id="portcalls"></div></div>
</div>
<script>{_THEME_JS}
const TH='px-4 py-3 font-semibold text-gray-600 dark:text-gray-300 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-left';
const TD='px-4 py-3 text-gray-800 dark:text-gray-200 border border-gray-200 dark:border-gray-700';
const SRC_BADGE={{'eukor':'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300','mst':'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300','rdw':'bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-300'}};
async function init(){{
  const d=await fetch('/api/vessels').then(r=>r.json());

  // ── AIS position cards ──
  const cards=document.getElementById('cards');
  if(Object.keys(d.positions).length>0){{
    for(const [mmsi,pos] of Object.entries(d.positions)){{
      const port=pos.port?'<span class="text-green-400 font-semibold">In '+pos.port+'</span>':'<span class="text-gray-400">At sea</span>';
      cards.innerHTML+=`<div class="p-4 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <h3 class="font-semibold text-gray-900 dark:text-white">${{pos.name}}</h3>
        <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">MMSI: ${{mmsi}}</p>
        <p class="text-sm mt-2">${{port}}</p>
        <p class="text-sm text-gray-500 dark:text-gray-400">${{pos.lat.toFixed(4)}}, ${{pos.lon.toFixed(4)}} &middot; ${{pos.speed_knots.toFixed(1)}} kn</p>
        <p class="text-xs text-gray-400 mt-2">Updated: ${{new Date(pos.timestamp).toLocaleString()}}</p></div>`;
    }}
  }}else{{
    cards.innerHTML='<p class="text-sm text-gray-400 col-span-3">No live AIS positions (aisstream.io has <a href="https://github.com/aisstream/aisstream/issues/15" class="underline">known outages</a>). Showing data from EUKOR schedule, MyShipTracking and RDW wave analysis below.</p>';
  }}

  // ── Ship arrivals timeline ──
  const tl=document.getElementById('timeline');
  const ships=d.ships_detailed||[];
  if(ships.length){{
    tl.innerHTML='<thead><tr><th class="'+TH+'">Date</th><th class="'+TH+'">Port</th><th class="'+TH+'">Vessel</th><th class="'+TH+'">Source</th></tr></thead>';
    const tbody=tl.createTBody();
    ships.sort((a,b)=>a.date.localeCompare(b.date));
    const today=new Date().toISOString().slice(0,10);
    ships.forEach(s=>{{
      const tr=tbody.insertRow();
      const isPast=s.date<=today;
      const opacity=isPast?'':'opacity-60';
      const badge=SRC_BADGE[s.source]||'bg-gray-100 text-gray-800';
      [s.date,s.port,s.name].forEach(v=>{{const td=tr.insertCell();td.className=TD+' '+opacity;td.textContent=v}});
      const srcTd=tr.insertCell();
      srcTd.className=TD+' '+opacity;
      srcTd.innerHTML='<span class="text-xs px-2 py-1 rounded-full '+badge+'">'+s.source+'</span>';
    }});
  }}

  // ── Port call history per vessel ──
  const pc=document.getElementById('portcalls');
  const NL_BE=new Set(['ROTTERDAM','ROZENBURG','EUROPOORT','ANTWERP','ANTWERPEN','ZEEBRUGGE','VLISSINGEN']);
  for(const [name,data] of Object.entries(d.port_calls)){{
    const calls=data.port_calls||[];
    if(!calls.length) continue;
    let html='<h3 class="text-sm font-semibold text-gray-700 dark:text-gray-300 mt-4 mb-2">'+name+' <span class="text-gray-400 font-normal">(MMSI '+data.mmsi+')</span></h3>';
    html+='<table class="w-full border-collapse text-sm mb-4"><thead><tr><th class="'+TH+'">Port</th><th class="'+TH+'">Arrival (UTC)</th><th class="'+TH+'">Departure (UTC)</th></tr></thead><tbody>';
    calls.forEach(c=>{{
      const isNL=NL_BE.has(c.port.toUpperCase());
      const hl=isNL?' bg-green-50 dark:bg-green-900/20 font-semibold':'';
      html+='<tr><td class="'+TD+hl+'">'+c.port+(isNL?' &#127475;&#127473;':'')+'</td><td class="'+TD+hl+'">'+(c.arrival||'—')+'</td><td class="'+TD+hl+'">'+(c.departure||'—')+'</td></tr>';
    }});
    html+='</tbody></table>';
    pc.innerHTML+=html;
  }}
}}

init();
</script></body></html>"""
