"""
Repair Estimate Rule Simulator — Dash Application
Enterprise Mobility · Claims Ops

Run:
    pip install dash plotly psycopg2-binary sshtunnel
    python dashboard.py
    open http://127.0.0.1:8050
"""

import json
from datetime import date
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State, callback_context, ALL

import db   # SSH tunnel + PostgreSQL connection pool

# ── Load metadata once at startup (no raw data in memory) ────────────────────
print("Loading metadata from PostgreSQL…")
_meta = db.load_metadata()

TOTAL_RECORDS   = _meta["total_records"]
ALL_DMG         = _meta["all_dmg"]
ALL_STATES      = _meta["all_states"]
VENDOR_HIST_MAX = _meta["vendor_hist_max"]
DATA_MIN_DATE   = _meta["data_min_date"]
DATA_MAX_DATE   = _meta["data_max_date"]
print(f"  {TOTAL_RECORDS:,} records  |  "
      f"{DATA_MIN_DATE} → {DATA_MAX_DATE}  |  "
      f"{len(ALL_STATES)} states  |  {len(ALL_DMG)} damage types")


def _default_dates():
    return DATA_MIN_DATE, DATA_MAX_DATE


DEFAULT_START, DEFAULT_END = _default_dates()

# ── Colours ───────────────────────────────────────────────────────────────────
EM_GREEN  = "#00B140"
EM_NAVY   = "#003264"
EM_SOFT   = "#E6ECF3"
INK_DIM   = "#4A5768"
INK_FAINT = "#8A95A3"
RISK      = "#C44536"
BORDER    = "#E3E6EB"

BASE_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", size=11, color=INK_DIM),
)

AXIS_X = dict(showgrid=False, zeroline=False,
              tickfont=dict(size=10, family="IBM Plex Mono, monospace"))
AXIS_Y = dict(showgrid=True, gridcolor=BORDER, zeroline=False,
              tickfont=dict(size=10, family="IBM Plex Mono, monospace"))


def empty_fig():
    fig = go.Figure()
    fig.add_annotation(text="No data matches current filters",
                       xref="paper", yref="paper", x=0.5, y=0.5,
                       showarrow=False,
                       font=dict(size=12, color=INK_FAINT, family="Inter"))
    fig.update_layout(**BASE_LAYOUT)
    return fig


# ── Vendor history slider marks (dynamic) ─────────────────────────────────────
def _hist_marks(mx):
    step = max(1, round(mx / 4 / 5) * 5)
    marks = {0: "0"}
    v = step
    while v < mx:
        if mx - v >= step * 0.5:   # skip marks that crowd the max label
            marks[v] = str(v)
        v += step
    marks[mx] = f"{mx}+"
    return marks


# ── App ───────────────────────────────────────────────────────────────────────
app = Dash(__name__, suppress_callback_exceptions=True)
app.title = "Repair Estimate Rule Simulator · Enterprise Mobility"

app.index_string = """
<!DOCTYPE html>
<html>
<head>
  {%metas%}
  <title>{%title%}</title>
  {%favicon%}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  {%css%}
  <style>
    :root {
      --em-green:#00B140; --em-green-dark:#008F34; --em-green-soft:#E5F6EB;
      --em-navy:#003264;  --em-navy-dark:#00244A;  --em-navy-soft:#E6ECF3;
      --bg:#F7F8FA; --panel:#FFFFFF;
      --border:#E3E6EB; --border-2:#CDD2DA;
      --ink:#0B1B2E; --ink-dim:#4A5768; --ink-faint:#8A95A3;
      --risk:#C44536; --risk-soft:#FDEEEB;
      --grid:#EEF0F4;
    }
    *{box-sizing:border-box;margin:0;padding:0;}
    html,body{
      background:var(--bg);color:var(--ink);
      font-family:'Inter',-apple-system,BlinkMacSystemFont,sans-serif;
      font-size:13px;line-height:1.5;min-height:100vh;
      -webkit-font-smoothing:antialiased;
    }
    body{
      background-image:
        radial-gradient(circle at 0% 0%,rgba(0,177,64,.04) 0%,transparent 35%),
        radial-gradient(circle at 100% 100%,rgba(0,50,100,.04) 0%,transparent 35%);
    }
    ::-webkit-scrollbar{width:6px;}
    ::-webkit-scrollbar-track{background:var(--bg);}
    ::-webkit-scrollbar-thumb{background:var(--border-2);border-radius:3px;}

    /* ── Container & header ── */
    .container{max-width:1460px;margin:0 auto;padding:28px 36px 80px;}
    header{
      display:flex;justify-content:space-between;align-items:flex-end;
      padding-bottom:20px;border-bottom:1px solid var(--border);margin-bottom:28px;
    }
    .brand{display:flex;align-items:center;gap:14px;}
    .brand-logo{
      width:38px;height:38px;background:var(--em-navy);border-radius:6px;
      flex-shrink:0;position:relative;
    }
    .brand-logo::before,.brand-logo::after{
      content:'';position:absolute;width:16px;height:2.5px;left:11px;
    }
    .brand-logo::before{background:var(--em-green);top:13px;}
    .brand-logo::after{background:#fff;bottom:13px;}
    .brand-mark{
      font-family:'IBM Plex Mono',monospace;font-size:10px;
      letter-spacing:.2em;color:var(--em-green);text-transform:uppercase;font-weight:600;
    }
    h1{font-weight:700;font-size:23px;letter-spacing:-.025em;color:var(--em-navy);}
    h1 span{font-weight:400;color:var(--ink-dim);}
    .meta{
      text-align:right;font-size:11px;color:var(--ink-faint);
      line-height:1.8;font-family:'IBM Plex Mono',monospace;
    }
    .meta strong{
      color:var(--ink-dim);font-weight:500;text-transform:uppercase;
      letter-spacing:.1em;font-size:10px;display:block;
    }

    /* ── Main grid ── */
    .grid-main{display:grid;grid-template-columns:340px 1fr;gap:20px;align-items:start;}
    @media(max-width:1100px){.grid-main{grid-template-columns:1fr;}}

    /* ── Panel (left sidebar) ── */
    .panel{
      background:var(--panel);border:1px solid var(--border);border-radius:8px;
      padding:20px;box-shadow:0 1px 3px rgba(0,50,100,.04);
    }
    .panel-title{
      font-size:11px;letter-spacing:.15em;text-transform:uppercase;
      color:var(--em-navy);margin-bottom:16px;padding-bottom:10px;
      border-bottom:1px solid var(--border);
      display:flex;justify-content:space-between;align-items:baseline;font-weight:600;
    }
    .panel-title .num{
      color:var(--em-green);font-family:'IBM Plex Mono',monospace;
      font-weight:600;letter-spacing:0;font-size:12px;
    }

    /* ── Filter groups ── */
    .filter-group{margin-bottom:18px;}
    .filter-group:last-child{margin-bottom:0;}
    .filter-label{
      display:flex;justify-content:space-between;align-items:baseline;margin-bottom:6px;
    }
    .filter-label .name{
      font-size:11px;letter-spacing:.08em;text-transform:uppercase;
      color:var(--ink-dim);font-weight:600;
    }
    .filter-label .val{
      font-size:12px;color:var(--em-navy);
      font-family:'IBM Plex Mono',monospace;font-weight:600;
    }
    .filter-hint{font-size:11px;color:var(--ink-faint);margin-top:5px;line-height:1.5;}

    /* ── Dash RangeSlider / Slider override ── */
    .rc-slider-track{background:var(--em-green)!important;height:3px!important;}
    .rc-slider-rail{background:var(--border-2)!important;height:3px!important;}
    .rc-slider-handle{
      border-color:var(--em-green)!important;background:var(--em-green)!important;
      width:16px!important;height:16px!important;margin-top:-7px!important;
      opacity:1!important;box-shadow:0 1px 4px rgba(0,50,100,.25)!important;
    }
    .rc-slider-handle:hover,.rc-slider-handle-dragging{
      border-color:var(--em-green-dark)!important;
      box-shadow:0 0 0 5px rgba(0,177,64,.15)!important;
    }
    .rc-slider-mark-text{
      font-family:'IBM Plex Mono',monospace!important;
      font-size:10px!important;color:var(--ink-faint)!important;
    }
    .rc-slider{margin:10px 0 24px;}

    /* ── Date pickers ── */
    .date-row{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:4px;}
    .date-sub-label{
      font-size:10px;letter-spacing:.06em;text-transform:uppercase;
      color:var(--ink-faint);font-weight:600;margin-bottom:4px;
    }
    /* Constrain picker to column width */
    .em-date-picker{width:100%;}
    .em-date-picker .SingleDatePickerInput{
      width:100%;background:var(--panel);
      border:1px solid var(--border-2);border-radius:4px;
      transition:border-color .12s;
    }
    .em-date-picker .SingleDatePickerInput:focus-within{
      border-color:var(--em-green);
      box-shadow:0 0 0 2px rgba(0,177,64,.12);
    }
    .em-date-picker .DateInput{width:100%;}
    .em-date-picker .DateInput_input{
      font-family:'IBM Plex Mono',monospace;font-size:11px;
      font-weight:600;color:var(--em-navy);
      padding:6px 8px;width:100%;background:transparent;
      border:none;border-bottom:2px solid transparent;
    }
    .em-date-picker .DateInput_input__focused{
      border-bottom:2px solid var(--em-green);
    }
    /* Calendar selected day */
    .CalendarDay__selected,.CalendarDay__selected:hover{
      background:var(--em-green)!important;
      border-color:var(--em-green-dark)!important;
    }
    .CalendarDay__hovered_span,.CalendarDay__selected_span{
      background:var(--em-green-soft)!important;
      border-color:var(--em-green-soft)!important;
      color:var(--em-navy)!important;
    }
    .DayPickerNavigation_button{border-color:var(--border-2)!important;}
    .DayPickerNavigation_button:hover{border-color:var(--em-green)!important;}
    /* Error message */
    .date-error{
      font-size:11px;color:var(--risk);margin-top:6px;
      font-family:'IBM Plex Mono',monospace;min-height:16px;
    }

    /* ── State multiselect dropdown ── */
    .em-dropdown .Select-control{
      border:1px solid var(--border-2)!important;border-radius:4px!important;
      min-height:32px!important;background:var(--panel)!important;
      cursor:text!important;
    }
    .em-dropdown .Select-control:hover{border-color:var(--em-green)!important;}
    .em-dropdown.is-focused .Select-control,
    .em-dropdown.is-open    .Select-control{
      border-color:var(--em-green)!important;
      box-shadow:0 0 0 2px rgba(0,177,64,.12)!important;
    }
    .em-dropdown .Select-placeholder,.em-dropdown .Select-input input{
      font-family:'Inter',sans-serif!important;font-size:11px!important;
      color:var(--ink-faint)!important;
    }
    .em-dropdown .Select-input input{color:var(--ink)!important;}
    /* Multi-select tags */
    .em-dropdown .Select-value{
      background:var(--em-green-soft)!important;
      border:1px solid var(--em-green)!important;
      border-radius:3px!important;color:var(--em-navy)!important;
      margin:2px 3px 2px 0!important;
    }
    .em-dropdown .Select-value-label{
      font-size:11px!important;font-weight:600!important;
      color:var(--em-navy)!important;padding:1px 4px!important;
    }
    .em-dropdown .Select-value-icon{
      border-right:1px solid var(--em-green)!important;
      color:var(--em-green-dark)!important;padding:1px 4px!important;
    }
    .em-dropdown .Select-value-icon:hover{
      background:var(--em-green)!important;color:#fff!important;
    }
    /* Dropdown menu panel */
    .em-dropdown .Select-menu-outer{
      border:1px solid var(--border-2)!important;border-radius:4px!important;
      box-shadow:0 4px 16px rgba(0,50,100,.12)!important;
      font-family:'Inter',sans-serif!important;font-size:11px!important;
      margin-top:2px!important;z-index:999!important;
    }
    .em-dropdown .Select-option{
      padding:7px 10px!important;color:var(--ink-dim)!important;
      font-size:11px!important;cursor:pointer!important;
    }
    .em-dropdown .Select-option.is-focused{
      background:var(--em-green-soft)!important;color:var(--em-navy)!important;
    }
    .em-dropdown .Select-option.is-selected{
      background:var(--em-green)!important;color:#fff!important;font-weight:600!important;
    }
    .em-dropdown .Select-arrow-zone{display:none!important;}
    .em-dropdown .Select-clear-zone{color:var(--ink-faint)!important;}
    .em-dropdown .Select-clear-zone:hover{color:var(--risk)!important;}

    /* ── Chips ── */
    .chip-group{display:flex;flex-wrap:wrap;gap:5px;margin-top:4px;}
    .chip{
      padding:4px 9px;border-radius:4px;border:1px solid var(--border-2);
      background:var(--panel);color:var(--ink-dim);font-size:11px;font-weight:500;
      cursor:pointer;transition:all .12s;font-family:'Inter',sans-serif;line-height:1.4;
    }
    .chip:hover{border-color:var(--em-green);color:var(--em-green);}
    .chip.active{
      background:var(--em-green)!important;
      border-color:var(--em-green)!important;color:#fff!important;
    }

    /* ── Toggle buttons ── */
    .toggle{
      display:flex;border:1px solid var(--border-2);border-radius:5px;
      overflow:hidden;background:var(--bg);padding:2px;gap:2px;
    }
    .toggle-btn{
      flex:1;padding:6px 0;text-align:center;font-size:11px;font-weight:500;
      cursor:pointer;background:transparent;color:var(--ink-dim);border:none;
      transition:all .12s;font-family:'Inter',sans-serif;border-radius:3px;
    }
    .toggle-btn:hover{background:var(--em-green-soft);color:var(--em-green);}
    .toggle-btn.active{background:var(--em-navy);color:#fff;font-weight:600;}

    /* ── Reset button ── */
    .reset-btn{
      width:100%;padding:9px 0;background:transparent;color:var(--ink-dim);
      border:1px solid var(--border-2);border-radius:5px;font-size:11px;font-weight:600;
      letter-spacing:.08em;text-transform:uppercase;cursor:pointer;
      transition:all .15s;margin-top:16px;font-family:'Inter',sans-serif;
    }
    .reset-btn:hover{background:var(--em-navy);color:#fff;border-color:var(--em-navy);}

    /* ── KPI row ── */
    .kpi-row{
      display:grid;grid-template-columns:1fr 1fr 1fr 1fr;
      gap:14px;margin-bottom:18px;
    }
    @media(max-width:900px){.kpi-row{grid-template-columns:1fr 1fr;}}

    .kpi-card{
      background:var(--panel);border:1px solid var(--border);border-radius:8px;
      padding:18px 20px;box-shadow:0 1px 3px rgba(0,50,100,.04);
      position:relative;overflow:hidden;min-width:0;
    }
    .kpi-card::before{
      content:'';position:absolute;top:0;left:0;right:0;height:3px;
      background:var(--em-green);border-radius:8px 8px 0 0;
    }

    /* Headline KPI (clean-pass rate) */
    .kpi-card.kpi-headline{
      background:linear-gradient(135deg,var(--em-navy) 0%,var(--em-navy-dark) 100%);
      border-color:var(--em-navy);
    }
    .kpi-card.kpi-headline::before{background:rgba(0,177,64,.0);}
    .kpi-card.kpi-headline::after{
      content:'';position:absolute;top:0;right:0;
      width:80px;height:80px;
      background:radial-gradient(circle,rgba(0,177,64,.2) 0%,transparent 70%);
    }
    .kpi-card.kpi-headline .kpi-label{color:rgba(255,255,255,.65);}
    .kpi-card.kpi-headline .kpi-val{color:#fff;font-size:36px;white-space:nowrap;}
    .kpi-card.kpi-headline .kpi-sub{color:rgba(255,255,255,.55);}

    /* Risk KPI */
    .kpi-card.kpi-risk::before{background:var(--risk);}

    .kpi-label{
      font-size:10px;letter-spacing:.12em;text-transform:uppercase;
      color:var(--ink-faint);font-weight:600;margin-bottom:6px;
    }
    .kpi-val{
      font-size:28px;font-weight:700;letter-spacing:-.03em;
      color:var(--em-navy);line-height:1.1;font-family:'IBM Plex Mono',monospace;
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
    }
    .kpi-val .unit{font-size:14px;font-weight:500;color:var(--em-green);margin-left:1px;}
    .kpi-val.green{color:var(--em-green);}
    .kpi-val.red{color:var(--risk);}
    .kpi-sub{font-size:11px;color:var(--ink-faint);margin-top:5px;
             font-family:'IBM Plex Mono',monospace;}

    /* ── KPI rate input (inside Potential Business Value card) ── */
    .kpi-rate-wrap{display:flex;align-items:center;gap:6px;margin-top:8px;}
    .kpi-rate-wrap label{font-size:10px;color:var(--ink-faint);white-space:nowrap;}
    .kpi-rate-input{
      width:72px;padding:3px 7px;font-size:13px;font-family:'IBM Plex Mono',monospace;
      border:1px solid var(--border);border-radius:5px;background:var(--bg);
      color:var(--ink);outline:none;
    }
    .kpi-rate-input:focus{border-color:var(--em-green);}

    /* ── Chart panels ── */
    .charts-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
    @media(max-width:900px){.charts-grid{grid-template-columns:1fr;}}

    .chart-panel{
      background:var(--panel);border:1px solid var(--border);
      border-radius:8px;padding:16px 14px 8px;
      box-shadow:0 1px 3px rgba(0,50,100,.04);
    }
    .chart-panel.wide{grid-column:span 2;}
    .chart-title{
      font-size:10px;letter-spacing:.14em;text-transform:uppercase;
      color:var(--em-navy);font-weight:600;margin-bottom:1px;
    }
    .chart-sub{font-size:11px;color:var(--ink-faint);margin-bottom:4px;}

    /* ── Vendor date range toggle button ── */
    .vendor-toggle-btn{
      display:block;width:100%;margin-top:8px;
      padding:5px 0;background:transparent;
      color:var(--ink-faint);border:1px solid var(--border);
      border-radius:4px;font-size:10px;letter-spacing:.06em;
      text-transform:uppercase;cursor:pointer;
      transition:all .12s;font-family:'Inter',sans-serif;font-weight:500;
    }
    .vendor-toggle-btn:hover{border-color:var(--em-green);color:var(--em-green);}
    .vendor-toggle-btn.open{
      border-color:var(--em-navy);color:var(--em-navy);font-weight:600;
    }
    /* ── Vendor date section ── */
    .vendor-date-section{
      margin-top:10px;padding:10px 12px;
      background:var(--em-navy-soft);border:1px solid var(--border-2);
      border-radius:6px;
    }
    .vendor-date-label{
      font-size:10px;letter-spacing:.08em;text-transform:uppercase;
      color:var(--em-navy);font-weight:600;margin-bottom:6px;
    }

  </style>
</head>
<body>
{%app_entry%}
<footer>{%config%}{%scripts%}{%renderer%}</footer>
</body>
</html>
"""

# ── Layout ────────────────────────────────────────────────────────────────────
app.layout = html.Div(className="container", children=[

    # Stores — single source of truth for toggles and chip state
    dcc.Store(id="store-elec", data="any"),
    dcc.Store(id="store-bulk", data="any"),
    dcc.Store(id="store-dmg",  data=ALL_DMG),

    # Hidden placeholder buttons for elec/bulk callbacks (filters commented out in sidebar)
    html.Div(style={"display": "none"}, children=[
        html.Button(id="elec-any", n_clicks=0),
        html.Button(id="elec-yes", n_clicks=0),
        html.Button(id="elec-no",  n_clicks=0),
        html.Button(id="bulk-any", n_clicks=0),
        html.Button(id="bulk-yes", n_clicks=0),
        html.Button(id="bulk-no",  n_clicks=0),
    ]),

    # ── Header ────────────────────────────────────────────────────────────────
    html.Header([
        html.Div(className="brand", children=[
            html.Div(className="brand-logo"),
            html.Div([
                html.Div("Claims Ops · Rule Studio", className="brand-mark"),
                html.H1(["Auto-approval ", html.Span("rule simulator")]),
            ]),
        ]),
        html.Div(className="meta", children=[
            html.Strong("Dataset"),
            html.Div(f"{TOTAL_RECORDS:,} estimates loaded"),
            html.Div(id="meta-sel"),
        ]),
    ]),

    html.Div(className="grid-main", children=[

        # ══════════════════ LEFT SIDEBAR — FILTERS ════════════════════════════
        html.Div(className="panel", children=[
            html.Div(className="panel-title", children=[
                "Rule Filters",
                html.Span(id="sel-count", className="num"),
            ]),

            # Data Date Range
            html.Div(className="filter-group", children=[
                html.Div(className="filter-label", children=[
                    html.Span("Data Date Range", className="name"),
                ]),
                html.Div(className="date-row", children=[
                    html.Div([
                        html.Div("Start Date", className="date-sub-label"),
                        dcc.DatePickerSingle(
                            id="start-date",
                            date=DEFAULT_START,
                            min_date_allowed=DATA_MIN_DATE,
                            max_date_allowed=DATA_MAX_DATE,
                            display_format="MMM D, YYYY",
                            placeholder="Start date",
                            className="em-date-picker",
                            clearable=False,
                        ),
                    ]),
                    html.Div([
                        html.Div("End Date", className="date-sub-label"),
                        dcc.DatePickerSingle(
                            id="end-date",
                            date=DEFAULT_END,
                            min_date_allowed=DATA_MIN_DATE,
                            max_date_allowed=DATA_MAX_DATE,
                            display_format="MMM D, YYYY",
                            placeholder="End date",
                            className="em-date-picker",
                            clearable=False,
                        ),
                    ]),
                ]),
                html.Div(id="date-error", className="date-error"),
                html.Div("est_recv_dte — estimate received date", className="filter-hint"),

                # Toggle button for vendor percentile date range
                html.Button(
                    "▼  Test Rule by customizing vendor percentile date range",
                    id="vendor-date-toggle",
                    className="vendor-toggle-btn",
                    n_clicks=0,
                ),
            ]),

            # Vendor Percentile Date Range (hidden by default)
            html.Div(
                id="vendor-date-section",
                style={"display": "none"},
                children=[
                    html.Div(className="vendor-date-section", children=[
                        html.Div("Vendor Percentile Date Range",
                                 className="vendor-date-label"),
                        html.Div(className="date-row", children=[
                            html.Div([
                                html.Div("Start Date", className="date-sub-label"),
                                dcc.DatePickerSingle(
                                    id="vendor-start-date",
                                    date=DEFAULT_START,
                                    min_date_allowed=DATA_MIN_DATE,
                                    max_date_allowed=DATA_MAX_DATE,
                                    display_format="MMM D, YYYY",
                                    placeholder="Start date",
                                    className="em-date-picker",
                                    clearable=False,
                                ),
                            ]),
                            html.Div([
                                html.Div("End Date", className="date-sub-label"),
                                dcc.DatePickerSingle(
                                    id="vendor-end-date",
                                    date=DEFAULT_END,
                                    min_date_allowed=DATA_MIN_DATE,
                                    max_date_allowed=DATA_MAX_DATE,
                                    display_format="MMM D, YYYY",
                                    placeholder="End date",
                                    className="em-date-picker",
                                    clearable=False,
                                ),
                            ]),
                        ]),
                        html.Div(
                            "Vendor approval rate computed from this window only",
                            className="filter-hint",
                            style={"marginTop": "6px"},
                        ),
                    ]),
                ],
            ),

            # Est. Total Amount
            html.Div(className="filter-group", children=[
                html.Div(className="filter-label", children=[
                    html.Span("Estimate Cost", className="name"),
                    html.Span(id="cost-label", className="val"),
                ]),
                dcc.RangeSlider(
                    id="cost-slider", min=0, max=11000, step=250,
                    value=[0, 11000],
                    marks={0: "$0", 2500: "$2.5k", 5500: "$5.5k", 11000: "$11k+"},
                    tooltip={"always_visible": False},
                    updatemode="mouseup",
                ),
                html.Div("est_tot_amt — total repair cost", className="filter-hint"),
            ]),

            # Labor Hours
            html.Div(className="filter-group", children=[
                html.Div(className="filter-label", children=[
                    html.Span("Labor Hours", className="name"),
                    html.Span(id="labor-label", className="val"),
                ]),
                dcc.RangeSlider(
                    id="labor-slider", min=0, max=60, step=1,
                    value=[0, 60],
                    marks={0: "0", 15: "15", 30: "30", 45: "45", 60: "60+"},
                    tooltip={"always_visible": False},
                    updatemode="mouseup",
                ),
                html.Div("lbr_hr_qty — labour time billed", className="filter-hint"),
            ]),

            # Line Items
            html.Div(className="filter-group", children=[
                html.Div(className="filter-label", children=[
                    html.Span("Line Items", className="name"),
                    html.Span(id="line-label", className="val"),
                ]),
                dcc.RangeSlider(
                    id="line-slider", min=1, max=13, step=1,
                    value=[1, 13],
                    marks={1: "1", 4: "4", 7: "7", 10: "10", 13: "13+"},
                    tooltip={"always_visible": False},
                    updatemode="mouseup",
                ),
                html.Div("line_item_count — repair line items", className="filter-hint"),
            ]),

            # Min Vendor Approval Rate
            html.Div(className="filter-group", children=[
                html.Div(className="filter-label", children=[
                    html.Span("Minimum Vendor First Pass Percentile", className="name"),
                    html.Span(id="acc-label", className="val"),
                ]),
                dcc.Slider(
                    id="acc-slider", min=0, max=1.0, step=0.05, value=0,
                    marks={0: "0%", 0.25: "25%", 0.5: "50%", 0.75: "75%", 1.0: "100%"},
                    tooltip={"always_visible": False},
                    updatemode="mouseup",
                ),
                html.Div(
                    "Require vendors to have at least this first pass approval rate",
                    className="filter-hint",
                ),
            ]),

            # Min Vendor History
            html.Div(className="filter-group", children=[
                html.Div(className="filter-label", children=[
                    html.Span("Min Vendor History", className="name"),
                    html.Span(id="prior-label", className="val"),
                ]),
                dcc.Slider(
                    id="prior-slider",
                    min=0, max=VENDOR_HIST_MAX, step=max(1, VENDOR_HIST_MAX // 20),
                    value=0,
                    marks=_hist_marks(VENDOR_HIST_MAX),
                    tooltip={"always_visible": False},
                    updatemode="mouseup",
                ),
                html.Div(
                    "Exclude vendors with fewer than N prior estimates",
                    className="filter-hint",
                ),
            ]),

            # State filter
            html.Div(className="filter-group", children=[
                html.Div(className="filter-label", children=[
                    html.Span("State", className="name"),
                ]),
                dcc.Dropdown(
                    id="state-filter",
                    options=[{"label": s, "value": s} for s in ALL_STATES],
                    value=ALL_STATES,
                    multi=True,
                    searchable=True,
                    placeholder="All states — type to search",
                    className="em-dropdown",
                    clearable=True,
                    optionHeight=32,
                ),
                html.Div("licplte_st — empty = all states", className="filter-hint"),
            ]),

            # Damage Type chips
            html.Div(className="filter-group", children=[
                html.Div(className="filter-label", children=[
                    html.Span("Damage Type", className="name"),
                ]),
                html.Div(id="dmg-chips", className="chip-group", children=[
                    html.Button(
                        d,
                        id={"type": "dmg-chip", "index": d},
                        className="chip active",
                        n_clicks=0,
                    )
                    for d in ALL_DMG
                ]),
                html.Div("dmg_dsc — click to toggle; empty = any", className="filter-hint"),
            ]),

            # # Electronic Estimate toggle  (hidden — re-enable when needed)
            # html.Div(className="filter-group", children=[
            #     html.Div(className="filter-label", children=[
            #         html.Span("Electronic Estimate", className="name"),
            #     ]),
            #     html.Div(className="toggle", children=[
            #         html.Button("Any", id="elec-any", className="toggle-btn active", n_clicks=0),
            #         html.Button("Yes", id="elec-yes", className="toggle-btn",         n_clicks=0),
            #         html.Button("No",  id="elec-no",  className="toggle-btn",         n_clicks=0),
            #     ]),
            #     html.Div("is_electronic_est_ind", className="filter-hint"),
            # ]),

            # # Bulk Estimate toggle  (hidden — re-enable when needed)
            # html.Div(className="filter-group", children=[
            #     html.Div(className="filter-label", children=[
            #         html.Span("Bulk Estimate", className="name"),
            #     ]),
            #     html.Div(className="toggle", children=[
            #         html.Button("Any", id="bulk-any", className="toggle-btn active", n_clicks=0),
            #         html.Button("Yes", id="bulk-yes", className="toggle-btn",         n_clicks=0),
            #         html.Button("No",  id="bulk-no",  className="toggle-btn",         n_clicks=0),
            #     ]),
            #     html.Div("is_bulk_ind", className="filter-hint"),
            # ]),

            html.Button("↺  Reset All Filters", id="reset-btn",
                        className="reset-btn", n_clicks=0),
        ]),

        # ══════════════════ RIGHT PANEL — RESULTS ═════════════════════════════
        html.Div([

        dcc.Loading(
            type="circle",
            color=EM_GREEN,
            fullscreen=False,
            style={"position": "sticky", "top": "50%"},
            children=html.Div([

            # KPI row
            html.Div(className="kpi-row", children=[
                html.Div(className="kpi-card", children=[
                    html.Div("Total Estimates", className="kpi-label"),
                    html.Div(id="kpi-total",     className="kpi-val"),
                    html.Div(id="kpi-total-sub", className="kpi-sub"),
                ]),
                html.Div(className="kpi-card", children=[
                    html.Div("Estimates Selected", className="kpi-label"),
                    html.Div(id="kpi-selected",     className="kpi-val"),
                    html.Div(id="kpi-selected-sub", className="kpi-sub"),
                ]),
                html.Div(className="kpi-card kpi-headline", children=[
                    html.Div("Auto Approval Coverage", className="kpi-label"),
                    html.Div(id="kpi-coverage",     className="kpi-val"),
                    html.Div(id="kpi-coverage-sub", className="kpi-sub"),
                ]),
                html.Div(className="kpi-card kpi-headline", children=[
                    html.Div("Auto Approval Precision", className="kpi-label"),
                    html.Div(id="kpi-precision",     className="kpi-val"),
                    html.Div(id="kpi-precision-sub", className="kpi-sub"),
                ]),
            ]),

            # KPI row 2 — operational metrics
            html.Div(className="kpi-row", children=[
                html.Div(className="kpi-card", children=[
                    html.Div("Total Time Saved", className="kpi-label"),
                    html.Div(id="kpi-time-saved",     className="kpi-val"),
                    html.Div(id="kpi-time-saved-sub", className="kpi-sub"),
                ]),
                html.Div(className="kpi-card", children=[
                    html.Div("Extra Car Rentable Days", className="kpi-label"),
                    html.Div(id="kpi-rental-days",     className="kpi-val"),
                    html.Div(id="kpi-rental-days-sub", className="kpi-sub"),
                ]),
                html.Div(className="kpi-card", children=[
                    html.Div("Potential Business Value", className="kpi-label"),
                    html.Div(id="kpi-biz-value",     className="kpi-val green"),
                    html.Div(id="kpi-biz-value-sub", className="kpi-sub"),
                    html.Div(className="kpi-rate-wrap", children=[
                        html.Label("$ per rentable day:", htmlFor="rate-input"),
                        dcc.Input(id="rate-input", type="number", value=50,
                                  min=0, step=1, debounce=True,
                                  className="kpi-rate-input"),
                    ]),
                ]),
                html.Div(className="kpi-card kpi-risk", children=[
                    html.Div("Estimated Risk", className="kpi-label"),
                    html.Div(id="kpi-est-risk",     className="kpi-val red"),
                    html.Div(id="kpi-est-risk-sub", className="kpi-sub"),
                ]),
            ]),

            # Charts — 2-column grid, 3 rows
            dcc.Loading(type="dot", color=EM_GREEN,
            children=html.Div(className="charts-grid", children=[

                html.Div(className="chart-panel", children=[
                    html.Div("Estimate Amount Distribution",     className="chart-title"),
                    html.Div("est_tot_amt — filtered vs total",  className="chart-sub"),
                    dcc.Graph(id="ch-amt", config={"displayModeBar": False},
                              style={"height": "260px"}),
                ]),
                html.Div(className="chart-panel", children=[
                    html.Div("Labour Hours Distribution",        className="chart-title"),
                    html.Div("lbr_hr_qty — filtered vs total",   className="chart-sub"),
                    dcc.Graph(id="ch-labor", config={"displayModeBar": False},
                              style={"height": "260px"}),
                ]),

                html.Div(className="chart-panel", children=[
                    html.Div("Lines in Estimate Distribution",      className="chart-title"),
                    html.Div("line_item_count — filtered vs total", className="chart-sub"),
                    dcc.Graph(id="ch-lines", config={"displayModeBar": False},
                              style={"height": "260px"}),
                ]),
                html.Div(className="chart-panel", children=[
                    html.Div("Time to Approve Distribution",             className="chart-title"),
                    html.Div("time_to_approve_hours — filtered vs total", className="chart-sub"),
                    dcc.Graph(id="ch-time", config={"displayModeBar": False},
                              style={"height": "260px"}),
                ]),

                html.Div(className="chart-panel", children=[
                    html.Div("Damage Type — Count",         className="chart-title"),
                    html.Div("dmg_dsc — filtered vs total", className="chart-sub"),
                    dcc.Graph(id="ch-dmg", config={"displayModeBar": False},
                              style={"height": "300px"}),
                ]),
                html.Div(className="chart-panel", children=[
                    html.Div("Estimates by State",              className="chart-title"),
                    html.Div("licplte_st — filtered estimates", className="chart-sub"),
                    dcc.Graph(id="ch-state", config={"displayModeBar": False},
                              style={"height": "300px"}),
                ]),

                html.Div(className="chart-panel wide", children=[
                    html.Div("Est. Amount by Damage Type",      className="chart-title"),
                    html.Div("est_tot_amt — filtered vs total", className="chart-sub"),
                    dcc.Graph(id="ch-box", config={"displayModeBar": False},
                              style={"height": "300px"}),
                ]),

            ])),   # end inner dcc.Loading (charts)

        ])),   # end outer dcc.Loading (full right panel)
        ]),
    ]),
])


# =============================================================================
# STORE CALLBACKS — UI interaction → store value (no chart logic)
# =============================================================================

@app.callback(
    Output("store-elec", "data"),
    Input("elec-any", "n_clicks"),
    Input("elec-yes", "n_clicks"),
    Input("elec-no",  "n_clicks"),
    prevent_initial_call=True,
)
def cb_store_elec(a, b, c):
    clicked = callback_context.triggered[0]["prop_id"].split(".")[0]
    return {"elec-any": "any", "elec-yes": "Y", "elec-no": "N"}.get(clicked, "any")


@app.callback(
    Output("store-bulk", "data"),
    Input("bulk-any", "n_clicks"),
    Input("bulk-yes", "n_clicks"),
    Input("bulk-no",  "n_clicks"),
    prevent_initial_call=True,
)
def cb_store_bulk(a, b, c):
    clicked = callback_context.triggered[0]["prop_id"].split(".")[0]
    return {"bulk-any": "any", "bulk-yes": "Y", "bulk-no": "N"}.get(clicked, "any")


@app.callback(
    Output("store-dmg", "data"),
    Input({"type": "dmg-chip", "index": ALL}, "n_clicks"),
    State("store-dmg", "data"),
    prevent_initial_call=True,
)
def cb_store_dmg(_, active_dmg):
    ctx = callback_context
    if not ctx.triggered:
        return active_dmg
    raw = ctx.triggered[0]["prop_id"].split(".")[0]
    try:
        clicked = json.loads(raw)["index"]
    except Exception:
        return active_dmg
    active = set(active_dmg or [])
    active.symmetric_difference_update({clicked})
    return list(active)


# =============================================================================
# STYLE CALLBACKS — store → className (visual only, no data reads)
# =============================================================================

@app.callback(
    Output("elec-any", "className"),
    Output("elec-yes", "className"),
    Output("elec-no",  "className"),
    Input("store-elec", "data"),
)
def style_elec(val):
    return ["toggle-btn active" if v == val else "toggle-btn"
            for v in ("any", "Y", "N")]


@app.callback(
    Output("bulk-any", "className"),
    Output("bulk-yes", "className"),
    Output("bulk-no",  "className"),
    Input("store-bulk", "data"),
)
def style_bulk(val):
    return ["toggle-btn active" if v == val else "toggle-btn"
            for v in ("any", "Y", "N")]


@app.callback(
    Output({"type": "dmg-chip", "index": ALL}, "className"),
    Input("store-dmg", "data"),
)
def style_chips(active_dmg):
    active = set(active_dmg or [])
    return ["chip active" if d in active else "chip" for d in ALL_DMG]


# =============================================================================
# VENDOR DATE TOGGLE — show / hide the vendor percentile date section
# =============================================================================

@app.callback(
    Output("vendor-date-section", "style"),
    Output("vendor-date-toggle",  "className"),
    Output("vendor-date-toggle",  "children"),
    Input("vendor-date-toggle",   "n_clicks"),
    prevent_initial_call=True,
)
def toggle_vendor_dates(n):
    if n % 2 == 1:   # odd clicks → open
        return (
            {"display": "block"},
            "vendor-toggle-btn open",
            "▲  Hide vendor percentile date range",
        )
    return (                           # even clicks → closed
        {"display": "none"},
        "vendor-toggle-btn",
        "▼  Test Rule by customizing vendor percentile date range",
    )


# =============================================================================
# VENDOR DATE SYNC — data dates → vendor dates (one-way only)
# =============================================================================

@app.callback(
    Output("vendor-start-date", "date"),
    Output("vendor-end-date",   "date"),
    Input("start-date", "date"),
    Input("end-date",   "date"),
)
def sync_vendor_dates(start, end):
    """Keep vendor dates in step with data dates.
    Changing vendor dates independently does NOT trigger this."""
    return start, end


# =============================================================================
# RESET — writes all filter controls back to defaults
# =============================================================================

@app.callback(
    Output("cost-slider",       "value"),
    Output("labor-slider",      "value"),
    Output("line-slider",       "value"),
    Output("acc-slider",        "value"),
    Output("prior-slider",      "value"),
    Output("start-date",        "date"),
    Output("end-date",          "date"),
    Output("vendor-start-date", "date", allow_duplicate=True),
    Output("vendor-end-date",   "date", allow_duplicate=True),
    Output("state-filter",      "value"),
    Output("store-elec",        "data", allow_duplicate=True),
    Output("store-bulk",        "data", allow_duplicate=True),
    Output("store-dmg",         "data", allow_duplicate=True),
    Input("reset-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_all(_):
    s, e = _default_dates()
    return [0, 11000], [0, 60], [1, 13], 0, 0, s, e, s, e, ALL_STATES, "any", "any", ALL_DMG


# =============================================================================
# MAIN CHART CALLBACK — all filters → all visual outputs
# Reads from sliders + stores only; never from classNames.
# =============================================================================

@app.callback(
    # Labels
    Output("cost-label",   "children"),
    Output("labor-label",  "children"),
    Output("line-label",   "children"),
    Output("acc-label",    "children"),
    Output("prior-label",  "children"),
    # Panel count
    Output("sel-count",    "children"),
    Output("meta-sel",     "children"),
    # KPIs
    Output("kpi-selected",      "children"),
    Output("kpi-selected-sub",  "children"),
    Output("kpi-total",         "children"),
    Output("kpi-total-sub",     "children"),
    Output("kpi-coverage",      "children"),
    Output("kpi-coverage-sub",  "children"),
    Output("kpi-precision",     "children"),
    Output("kpi-precision-sub", "children"),
    # KPI row 2
    Output("kpi-time-saved",     "children"),
    Output("kpi-time-saved-sub", "children"),
    Output("kpi-rental-days",     "children"),
    Output("kpi-rental-days-sub", "children"),
    Output("kpi-biz-value",     "children"),
    Output("kpi-biz-value-sub", "children"),
    Output("kpi-est-risk",     "children"),
    Output("kpi-est-risk-sub", "children"),
    # Date validation
    Output("date-error", "children"),
    # Charts
    Output("ch-amt",   "figure"),
    Output("ch-labor", "figure"),
    Output("ch-lines", "figure"),
    Output("ch-time",  "figure"),
    Output("ch-dmg",   "figure"),
    Output("ch-state", "figure"),
    Output("ch-box",   "figure"),
    # Inputs
    Input("cost-slider",       "value"),
    Input("labor-slider",      "value"),
    Input("line-slider",       "value"),
    Input("acc-slider",        "value"),
    Input("prior-slider",      "value"),
    Input("start-date",        "date"),
    Input("end-date",          "date"),
    Input("vendor-start-date", "date"),
    Input("vendor-end-date",   "date"),
    Input("state-filter",      "value"),
    Input("store-elec",        "data"),
    Input("store-bulk",        "data"),
    Input("store-dmg",         "data"),
    Input("rate-input",        "value"),
)
def update_all(cost_r, labor_r, line_r, acc_min, prior_min,
               start_date_str, end_date_str,
               vendor_start_str, vendor_end_str,
               state_vals, elec_val, bulk_val, active_dmg, rate_per_day):

    # ── Helpers ───────────────────────────────────────────────────────────────
    def _parse(d):
        return date.fromisoformat(d) if isinstance(d, str) else d

    # ── Date validation ───────────────────────────────────────────────────────
    start_d = _parse(start_date_str)
    end_d   = _parse(end_date_str)

    if start_d is None and end_d is None:
        date_err = "⚠ Both dates are required"
    elif start_d is None:
        date_err = "⚠ Start date is required"
    elif end_d is None:
        date_err = "⚠ End date is required"
    elif start_d > end_d:
        date_err = "⚠ Start date must be on or before end date"
    else:
        date_err = ""

    apply_dates = date_err == ""
    eff_start = start_d if apply_dates else DATA_MIN_DATE
    eff_end   = end_d   if apply_dates else DATA_MAX_DATE

    # ── Vendor percentile date window ─────────────────────────────────────────
    vendor_start_d = _parse(vendor_start_str)
    vendor_end_d   = _parse(vendor_end_str)
    vendor_dates_ok = (vendor_start_d is not None and
                       vendor_end_d   is not None and
                       vendor_start_d <= vendor_end_d)
    eff_vstart = vendor_start_d if vendor_dates_ok else eff_start
    eff_vend   = vendor_end_d   if vendor_dates_ok else eff_end

    # ── Filter display labels (no DB call needed) ─────────────────────────────
    cost_lbl  = (f"${cost_r[0]:,.0f} – "
                 f"{'$11k+' if cost_r[1] >= 11000 else f'${cost_r[1]:,.0f}'}")
    labor_lbl = (f"{labor_r[0]} – "
                 f"{'60+ hr' if labor_r[1] >= 60 else f'{labor_r[1]} hr'}")
    line_lbl  = f"{line_r[0]} – {'13+' if line_r[1] >= 13 else line_r[1]}"
    acc_lbl   = "" if acc_min == 0 else f"≥ {acc_min*100:.0f}%"
    prior_lbl = "" if prior_min == 0 else f"≥ {prior_min:,}"

    # ── Query PostgreSQL ──────────────────────────────────────────────────────
    active = active_dmg if active_dmg else ALL_DMG
    params = dict(
        p_start_date        = eff_start,
        p_end_date          = eff_end,
        p_vendor_start_date = eff_vstart,
        p_vendor_end_date   = eff_vend,
        p_cost_min          = float(cost_r[0]),
        p_cost_max          = 999_999.0 if cost_r[1] >= 11000 else float(cost_r[1]),
        p_labor_min         = float(labor_r[0]),
        p_labor_max         = 9_999.0   if labor_r[1] >= 60   else float(labor_r[1]),
        p_line_min          = int(line_r[0]),
        p_line_max          = 9_999     if line_r[1]  >= 13   else int(line_r[1]),
        p_acc_min           = float(acc_min),
        p_prior_min         = int(prior_min),
        p_states            = state_vals if state_vals and len(state_vals) < len(ALL_STATES) else None,
        p_dmg_types         = active     if len(active) < len(ALL_DMG)                       else None,
        p_elec              = elec_val,
        p_bulk              = bulk_val,
    )
    data = db.query_dashboard(params)

    # ── Unpack KPIs ───────────────────────────────────────────────────────────
    kpis         = data.get("kpis") or {}
    n_date       = int(kpis.get("n_date",         0) or 0)
    n            = int(kpis.get("n",               0) or 0)
    n_rev1       = int(kpis.get("n_rev1",          0) or 0)
    n_appr       = int(kpis.get("n_appr",          0) or 0)
    time_saved_hrs = float(kpis.get("time_saved_hrs", 0) or 0)
    mean_correct = float(kpis.get("mean_correct_amt", 0) or 0)
    mean_wrong   = float(kpis.get("mean_wrong_amt",   0) or 0)

    # Derived KPIs
    coverage    = n / n_date if n_date > 0 else 0.0
    precision   = n_rev1 / n if n > 0 else 0.0
    rental_days = time_saved_hrs / 24.0
    rate        = float(rate_per_day) if rate_per_day else 50.0
    biz_value   = rental_days * rate
    est_risk    = mean_wrong - mean_correct

    sel_txt  = f"{n:,} / {TOTAL_RECORDS:,}"
    meta_txt = f"{n:,} records selected"

    # ── Empty state ───────────────────────────────────────────────────────────
    ef = empty_fig()
    if n == 0:
        return (cost_lbl, labor_lbl, line_lbl, acc_lbl, prior_lbl,
                sel_txt, meta_txt,
                "0", f"of {n_date:,} in date window",
                f"{n_date:,}", "after date filter only",
                "0%", "0 of 0 estimates",
                "—", [html.Span("0 of 0 correct", style={"color": EM_GREEN}),
                      html.Span(" · "),
                      html.Span("0 of 0 wrong",   style={"color": RISK})],
                "—", "", "—", "", "—", "", "—", "",
                date_err,
                ef, ef, ef, ef, ef, ef, ef)

    # ── Shared chart style constants ──────────────────────────────────────────
    _yax  = dict(showgrid=True, gridcolor=BORDER, zeroline=False,
                 tickfont=dict(size=9, family="IBM Plex Mono, monospace"))
    _xcat = dict(showgrid=False,
                 tickfont=dict(size=9, family="IBM Plex Mono, monospace"),
                 tickangle=-20)
    _leg  = dict(font=dict(size=10), orientation="h", x=0, y=1.08)
    _mar  = dict(l=48, r=16, t=46, b=48)
    _lbl  = dict(textposition="outside",
                 textfont=dict(size=8, family="IBM Plex Mono, monospace"))

    def _hist_fig(rows, xaxis=None):
        """Build a grouped bar chart from hist_* JSON rows."""
        if not rows:
            return empty_fig()
        labels = [r["bucket"] for r in rows]
        totals = [int(r["total"])    for r in rows]
        filtrd = [int(r["filtered"]) for r in rows]
        fig = go.Figure()
        fig.add_trace(go.Bar(x=labels, y=totals, name="Total",
            marker_color=EM_SOFT, opacity=0.85,
            texttemplate="%{y:,}", **_lbl,
            hovertemplate="%{x}: %{y:,}<extra>Total</extra>"))
        fig.add_trace(go.Bar(x=labels, y=filtrd, name="Filtered",
            marker_color=EM_GREEN, opacity=0.9,
            texttemplate="%{y:,}", **_lbl,
            hovertemplate="%{x}: %{y:,}<extra>Filtered</extra>"))
        fig.update_layout(**BASE_LAYOUT, barmode="group", showlegend=True,
            legend=_leg, margin=_mar,
            xaxis=xaxis or _xcat, yaxis=_yax)
        return fig

    # ── Charts 1-4: histograms ────────────────────────────────────────────────
    fig_amt   = _hist_fig(data.get("hist_amt"))
    fig_labor = _hist_fig(data.get("hist_labor"))
    fig_lines = _hist_fig(data.get("hist_lines"))
    fig_time  = _hist_fig(data.get("hist_time"))

    # ── Chart 5: Damage type count ────────────────────────────────────────────
    _hlbl = dict(textposition="outside",
                 textfont=dict(size=8, family="IBM Plex Mono, monospace"))
    dmg_rows = sorted(data.get("dmg_counts") or [], key=lambda r: r["total"])
    if dmg_rows:
        dg_labels   = [r["dmg_dsc"]         for r in dmg_rows]
        dg_total    = [int(r["total"])       for r in dmg_rows]
        dg_filtered = [int(r["filtered"])    for r in dmg_rows]
        fig_dmg = go.Figure()
        fig_dmg.add_trace(go.Bar(y=dg_labels, x=dg_total, orientation="h",
            name="Total", marker_color=EM_SOFT, opacity=0.85,
            texttemplate="%{x:,}", **_hlbl,
            hovertemplate="%{y}: %{x:,}<extra>Total</extra>"))
        fig_dmg.add_trace(go.Bar(y=dg_labels, x=dg_filtered, orientation="h",
            name="Filtered", marker_color=EM_GREEN, opacity=0.9,
            texttemplate="%{x:,}", **_hlbl,
            hovertemplate="%{y}: %{x:,}<extra>Filtered</extra>"))
        fig_dmg.update_layout(**BASE_LAYOUT, barmode="group", showlegend=True,
            legend=dict(font=dict(size=10), orientation="v",
                        x=1.02, y=1, xanchor="left", yanchor="top"),
            margin=dict(l=130, r=80, t=36, b=16),
            xaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=False,
                       tickfont=dict(size=9, family="IBM Plex Mono, monospace")),
            yaxis=dict(showgrid=False,
                       tickfont=dict(size=10, family="Inter, sans-serif")))
    else:
        fig_dmg = empty_fig()

    # ── Chart 6: State bubble map ─────────────────────────────────────────────
    state_rows = data.get("state_counts") or []
    if state_rows:
        states = [r["state"] for r in state_rows]
        counts = [int(r["cnt"]) for r in state_rows]
        max_c  = max(counts)
        sizes  = [round((c / max_c) * 45 + 8, 1) for c in counts]
        fig_state = go.Figure(go.Scattergeo(
            locations=states, locationmode="USA-states",
            text=states, customdata=counts,
            marker=dict(
                size=sizes, color=counts,
                colorscale=[[0, EM_SOFT], [0.4, "#66C98A"], [1, EM_GREEN]],
                showscale=True,
                colorbar=dict(
                    title=dict(text="Estimates",
                               font=dict(size=9, family="Inter")),
                    thickness=10, len=0.55, x=1.0,
                    tickfont=dict(size=8, family="IBM Plex Mono, monospace"),
                ),
                sizemode="diameter", sizemin=6,
                line=dict(color="#fff", width=1), opacity=0.85,
            ),
            hovertemplate="<b>%{text}</b><br>%{customdata:,} estimates<extra></extra>",
        ))
        fig_state.update_layout(
            **BASE_LAYOUT,
            geo=dict(scope="usa", projection_type="albers usa",
                     showland=True, landcolor="rgba(232,238,245,1)",
                     showlakes=True, lakecolor="rgba(255,255,255,0.9)",
                     showsubunits=True, subunitcolor=BORDER, subunitwidth=0.5,
                     bgcolor="rgba(0,0,0,0)"),
            margin=dict(l=0, r=50, t=8, b=0),
        )
    else:
        fig_state = empty_fig()

    # ── Chart 7: Box plot — est amount by damage type ─────────────────────────
    fig_box = go.Figure()
    for box_key, bname, bcolor, bfill in [
        ("box_base", "Total",    EM_SOFT,  "rgba(0,177,64,0.07)"),
        ("box_filt", "Filtered", EM_GREEN, "rgba(0,177,64,0.22)"),
    ]:
        rows = data.get(box_key) or []
        if rows:
            fig_box.add_trace(go.Box(
                x=[r["dmg_dsc"] for r in rows],
                q1=[float(r["q1"])     for r in rows],
                median=[float(r["median"]) for r in rows],
                q3=[float(r["q3"])     for r in rows],
                lowerfence=[float(r["lf"])  for r in rows],
                upperfence=[float(r["uf"])  for r in rows],
                name=bname, marker_color=bcolor, fillcolor=bfill,
                line=dict(color=bcolor, width=1.5),
                hovertemplate="%{x}<br>Median: $%{median:,.0f}<extra>"
                              + bname + "</extra>"))
    if not fig_box.data:
        fig_box = empty_fig()
    else:
        fig_box.update_layout(**BASE_LAYOUT, boxmode="group", showlegend=True,
            legend=dict(font=dict(size=10), orientation="h", x=0, y=1.04),
            margin=dict(l=56, r=16, t=36, b=56),
            yaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=False,
                       tickprefix="$",
                       tickfont=dict(size=9, family="IBM Plex Mono, monospace")),
            xaxis=dict(showgrid=False,
                       tickfont=dict(size=10, family="Inter, sans-serif"),
                       tickangle=-15))

    return (
        cost_lbl, labor_lbl, line_lbl, acc_lbl, prior_lbl,
        sel_txt, meta_txt,
        f"{n:,}",        f"of {n_date:,} in date window",
        f"{n_date:,}",   "after date filter only",
        f"{coverage:.1%}", f"{n:,} of {n_date:,} estimates",
        f"{precision:.1%}",
        [html.Span(f"{n_rev1:,} of {n:,} correct", style={"color": EM_GREEN}),
         html.Span(" · "),
         html.Span(f"{n - n_rev1:,} of {n:,} wrong", style={"color": RISK})],
        f"{time_saved_hrs:,.0f} hrs", f"from {n_appr:,} auto-approved estimates",
        f"{rental_days:,.1f} days",   f"{time_saved_hrs:,.0f} hrs ÷ 24",
        f"${biz_value:,.0f}",         f"{rental_days:,.1f} days × ${rate:,.0f}/day",
        f"${est_risk:,.0f}",          f"mean wrong ${mean_wrong:,.0f} − mean correct ${mean_correct:,.0f}",
        date_err,
        fig_amt, fig_labor, fig_lines, fig_time, fig_dmg, fig_state, fig_box,
    )


if __name__ == "__main__":
    print("=" * 50)
    print("  Repair Estimate Rule Simulator")
    print("  http://127.0.0.1:8050")
    print("=" * 50)
    app.run(debug=True, port=8050)
