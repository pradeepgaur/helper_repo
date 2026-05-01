"""
Repair Estimate Rule Simulator — Dash Application
Enterprise Mobility · Claims Ops

Run:
    pip install dash plotly pandas
    python dashboard.py
    open http://127.0.0.1:8050
"""

import json
import os
from datetime import date, timedelta
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, Input, Output, State, callback_context, ALL

# ── Load & pre-process once ───────────────────────────────────────────────────
CSV_PATH     = "data/repair_estimates.csv"
PARQUET_PATH = "data/repair_estimates.parquet"

# Use parquet cache when available and newer than the CSV (10× faster load)
if (os.path.exists(PARQUET_PATH) and
        os.path.getmtime(PARQUET_PATH) >= os.path.getmtime(CSV_PATH)):
    print("Loading from parquet cache…")
    df = pd.read_parquet(PARQUET_PATH)
else:
    print("Processing CSV (first run or CSV updated)…")
    df = pd.read_csv(CSV_PATH)
    df["auto_approved"]         = df["repr_auth_stat_typ_cde"] == "A"
    df["est_tot_amt"]           = pd.to_numeric(df["est_tot_amt"],          errors="coerce")
    df["lbr_hr_qty"]            = pd.to_numeric(df["lbr_hr_qty"],           errors="coerce")
    df["line_item_count"]       = pd.to_numeric(df["line_item_count"],      errors="coerce")
    df["time_to_approve_hours"] = pd.to_numeric(df["time_to_approve_hours"],errors="coerce")
    df["time_to_approve_days"]  = pd.to_numeric(df["time_to_approve_days"], errors="coerce")
    df["est_recv_dte"]          = pd.to_datetime(df["est_recv_dte"],         errors="coerce")

    # Vendor-level stats
    vs = (df.groupby("vr_vndr_id")
            .agg(vendor_est_count=("est_id", "count"),
                 vendor_approval_rate=("auto_approved", "mean"))
            .reset_index())
    df = df.merge(vs, on="vr_vndr_id", how="left")

    # Categorical dtypes — faster filtering & 5–10× less memory for string cols
    for col in ["dmg_dsc", "create_module", "repr_auth_stat_typ_cde",
                "repr_auth_stat_typ_dsc", "licplte_st",
                "is_electronic_est_ind", "is_bulk_ind"]:
        if col in df.columns:
            df[col] = df[col].astype("category")

    # Pre-compute date-only column so callbacks never call .dt.date at query time
    df["recv_date"] = df["est_recv_dte"].dt.normalize()   # midnight timestamps

    try:
        df.to_parquet(PARQUET_PATH, index=False)
        print("Parquet cache written.")
    except Exception as e:
        print(f"Could not write parquet cache: {e}")

# Ensure recv_date exists when loading from parquet too
if "recv_date" not in df.columns:
    df["recv_date"] = df["est_recv_dte"].dt.normalize()

TOTAL_RECORDS   = len(df)
ALL_DMG         = sorted(df["dmg_dsc"].dropna().unique().tolist())
ALL_STATES      = sorted(df["licplte_st"].dropna().unique().tolist())
VENDOR_HIST_MAX = int(df["vendor_est_count"].max())

# Actual data date boundaries (for picker min/max)
DATA_MIN_DATE = df["est_recv_dte"].min().date()
DATA_MAX_DATE = df["est_recv_dte"].max().date()

# Default date range: end = last day of previous month; start = 6 months before that
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
    marks = {0: "Any"}
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
      display:grid;grid-template-columns:1.3fr 1fr 1fr 1fr;
      gap:14px;margin-bottom:18px;
    }
    @media(max-width:900px){.kpi-row{grid-template-columns:1fr 1fr;}}

    .kpi-card{
      background:var(--panel);border:1px solid var(--border);border-radius:8px;
      padding:18px 20px;box-shadow:0 1px 3px rgba(0,50,100,.04);
      position:relative;overflow:hidden;
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
    .kpi-card.kpi-headline .kpi-val{color:#fff;font-size:38px;}
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
    }
    .kpi-val .unit{font-size:14px;font-weight:500;color:var(--em-green);margin-left:1px;}
    .kpi-val.green{color:var(--em-green);}
    .kpi-val.red{color:var(--risk);}
    .kpi-sub{font-size:11px;color:var(--ink-faint);margin-top:5px;
             font-family:'IBM Plex Mono',monospace;}

    /* ── Chart panels ── */
    .charts-grid{display:grid;grid-template-columns:1fr 1fr 1fr;gap:14px;}
    @media(max-width:1100px){.charts-grid{grid-template-columns:1fr 1fr;}}

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

            # Date Range
            html.Div(className="filter-group", children=[
                html.Div(className="filter-label", children=[
                    html.Span("Date Range", className="name"),
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
            ]),

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
                    html.Span("Min Vendor Accuracy", className="name"),
                    html.Span(id="acc-label", className="val"),
                ]),
                dcc.Slider(
                    id="acc-slider", min=0, max=1.0, step=0.05, value=0,
                    marks={0: "Any", 0.25: "25%", 0.5: "50%", 0.75: "75%", 1.0: "100%"},
                    tooltip={"always_visible": False},
                    updatemode="mouseup",
                ),
                html.Div(
                    "Require vendors to have at least this historical approval rate",
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

            # Electronic Estimate toggle
            html.Div(className="filter-group", children=[
                html.Div(className="filter-label", children=[
                    html.Span("Electronic Estimate", className="name"),
                ]),
                html.Div(className="toggle", children=[
                    html.Button("Any", id="elec-any", className="toggle-btn active", n_clicks=0),
                    html.Button("Yes", id="elec-yes", className="toggle-btn",         n_clicks=0),
                    html.Button("No",  id="elec-no",  className="toggle-btn",         n_clicks=0),
                ]),
                html.Div("is_electronic_est_ind", className="filter-hint"),
            ]),

            # Bulk Estimate toggle
            html.Div(className="filter-group", children=[
                html.Div(className="filter-label", children=[
                    html.Span("Bulk Estimate", className="name"),
                ]),
                html.Div(className="toggle", children=[
                    html.Button("Any", id="bulk-any", className="toggle-btn active", n_clicks=0),
                    html.Button("Yes", id="bulk-yes", className="toggle-btn",         n_clicks=0),
                    html.Button("No",  id="bulk-no",  className="toggle-btn",         n_clicks=0),
                ]),
                html.Div("is_bulk_ind", className="filter-hint"),
            ]),

            html.Button("↺  Reset All Filters", id="reset-btn",
                        className="reset-btn", n_clicks=0),
        ]),

        # ══════════════════ RIGHT PANEL — RESULTS ═════════════════════════════
        html.Div([

            # KPI row
            html.Div(className="kpi-row", children=[
                html.Div(className="kpi-card kpi-headline", children=[
                    html.Div("Clean-pass Rate", className="kpi-label"),
                    html.Div(id="kpi-cpr", className="kpi-val",
                             children=[html.Span(id="kpi-cpr-num"), html.Span("%", className="unit")]),
                    html.Div(id="kpi-cpr-sub", className="kpi-sub"),
                ]),
                html.Div(className="kpi-card", children=[
                    html.Div("Estimates Selected", className="kpi-label"),
                    html.Div(id="kpi-count",     className="kpi-val"),
                    html.Div(id="kpi-count-sub", className="kpi-sub"),
                ]),
                html.Div(className="kpi-card", children=[
                    html.Div("Avg. Est. Amount", className="kpi-label"),
                    html.Div(id="kpi-cost",     className="kpi-val"),
                    html.Div(id="kpi-cost-sub", className="kpi-sub"),
                ]),
                html.Div(className="kpi-card kpi-risk", children=[
                    html.Div("Median Approval Time", className="kpi-label"),
                    html.Div(id="kpi-time",     className="kpi-val red"),
                    html.Div(id="kpi-time-sub", className="kpi-sub"),
                ]),
            ]),

            # Charts 3-column grid
            dcc.Loading(type="dot", color=EM_GREEN,
            children=html.Div(className="charts-grid", children=[

                html.Div(className="chart-panel", children=[
                    html.Div("Approval Status",        className="chart-title"),
                    html.Div("repr_auth_stat_typ_cde", className="chart-sub"),
                    dcc.Graph(id="ch-donut",  config={"displayModeBar": False},
                              style={"height": "230px"}),
                ]),

                html.Div(className="chart-panel wide", children=[
                    html.Div("Damage Type Breakdown",     className="chart-title"),
                    html.Div("approval rate per dmg_dsc", className="chart-sub"),
                    dcc.Graph(id="ch-dmg", config={"displayModeBar": False},
                              style={"height": "230px"}),
                ]),

                html.Div(className="chart-panel", children=[
                    html.Div("Time to Approve",        className="chart-title"),
                    html.Div("time_to_approve_hours",  className="chart-sub"),
                    dcc.Graph(id="ch-hist", config={"displayModeBar": False},
                              style={"height": "230px"}),
                ]),

                html.Div(className="chart-panel wide", children=[
                    html.Div("Est. Amount by Damage Type",   className="chart-title"),
                    html.Div("est_tot_amt — approved vs not", className="chart-sub"),
                    dcc.Graph(id="ch-box", config={"displayModeBar": False},
                              style={"height": "230px"}),
                ]),

                html.Div(className="chart-panel", children=[
                    html.Div("Submission Channel",          className="chart-title"),
                    html.Div("create_module volume & rate", className="chart-sub"),
                    dcc.Graph(id="ch-module", config={"displayModeBar": False},
                              style={"height": "230px"}),
                ]),

                html.Div(className="chart-panel wide", children=[
                    html.Div("Labor Hours vs. Est. Amount", className="chart-title"),
                    html.Div("lbr_hr_qty × est_tot_amt",   className="chart-sub"),
                    dcc.Graph(id="ch-scatter", config={"displayModeBar": False},
                              style={"height": "230px"}),
                ]),
            ])),   # end dcc.Loading
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
# RESET — writes all filter controls back to defaults
# =============================================================================

@app.callback(
    Output("cost-slider",  "value"),
    Output("labor-slider", "value"),
    Output("line-slider",  "value"),
    Output("acc-slider",   "value"),
    Output("prior-slider", "value"),
    Output("start-date",   "date"),
    Output("end-date",     "date"),
    Output("state-filter", "value"),
    Output("store-elec",   "data", allow_duplicate=True),
    Output("store-bulk",   "data", allow_duplicate=True),
    Output("store-dmg",    "data", allow_duplicate=True),
    Input("reset-btn", "n_clicks"),
    prevent_initial_call=True,
)
def reset_all(_):
    s, e = _default_dates()
    return [0, 11000], [0, 60], [1, 13], 0, 0, s, e, ALL_STATES, "any", "any", ALL_DMG


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
    Output("kpi-cpr-num",    "children"),
    Output("kpi-cpr-sub",    "children"),
    Output("kpi-count",      "children"),
    Output("kpi-count-sub",  "children"),
    Output("kpi-cost",       "children"),
    Output("kpi-cost-sub",   "children"),
    Output("kpi-time",       "children"),
    Output("kpi-time-sub",   "children"),
    # Date validation
    Output("date-error", "children"),
    # Charts
    Output("ch-donut",   "figure"),
    Output("ch-dmg",     "figure"),
    Output("ch-hist",    "figure"),
    Output("ch-box",     "figure"),
    Output("ch-module",  "figure"),
    Output("ch-scatter", "figure"),
    # Inputs
    Input("cost-slider",  "value"),
    Input("labor-slider", "value"),
    Input("line-slider",  "value"),
    Input("acc-slider",   "value"),
    Input("prior-slider", "value"),
    Input("start-date",   "date"),
    Input("end-date",     "date"),
    Input("state-filter", "value"),
    Input("store-elec",   "data"),
    Input("store-bulk",   "data"),
    Input("store-dmg",    "data"),
)
def update_all(cost_r, labor_r, line_r, acc_min, prior_min,
               start_date_str, end_date_str, state_vals,
               elec_val, bulk_val, active_dmg):

    # ── Date validation ───────────────────────────────────────────────────────
    def _parse(d):
        return date.fromisoformat(d) if isinstance(d, str) else d

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

    # ── Filter ────────────────────────────────────────────────────────────────
    active = active_dmg if active_dmg else ALL_DMG
    mask = (
        (df["est_tot_amt"]     >= cost_r[0])  & (df["est_tot_amt"]     <= cost_r[1])  &
        (df["lbr_hr_qty"]      >= labor_r[0]) & (df["lbr_hr_qty"]      <= labor_r[1]) &
        (df["line_item_count"] >= line_r[0])  & (df["line_item_count"] <= line_r[1])  &
        (df["dmg_dsc"].isin(active))
    )
    if acc_min > 0:
        mask &= (df["vendor_approval_rate"] >= acc_min)
    if prior_min > 0:
        mask &= (df["vendor_est_count"] >= prior_min)
    if len(state_vals) < len(ALL_STATES):
        mask &= df["licplte_st"].isin(state_vals)
    if elec_val != "any":
        mask &= (df["is_electronic_est_ind"] == elec_val)
    if bulk_val != "any":
        mask &= (df["is_bulk_ind"] == bulk_val)
    if apply_dates:
        mask &= (
            (df["recv_date"] >= pd.Timestamp(start_d)) &
            (df["recv_date"] <= pd.Timestamp(end_d))
        )

    filt = df[mask]
    n = len(filt)

    # ── Filter display labels ─────────────────────────────────────────────────
    cost_lbl  = (f"${cost_r[0]:,.0f} – "
                 f"{'$11k+' if cost_r[1] >= 11000 else f'${cost_r[1]:,.0f}'}")
    labor_lbl = (f"{labor_r[0]} – "
                 f"{'60+ hr' if labor_r[1] >= 60 else f'{labor_r[1]} hr'}")
    line_lbl  = f"{line_r[0]} – {'13+' if line_r[1] >= 13 else line_r[1]}"
    acc_lbl   = "Any" if acc_min == 0 else f"≥ {acc_min*100:.0f}%"
    prior_lbl = "Any" if prior_min == 0 else f"≥ {prior_min:,}"
    sel_txt   = f"{n:,} / {TOTAL_RECORDS:,}"
    meta_txt  = f"{n:,} records selected"

    # ── Empty state ───────────────────────────────────────────────────────────
    ef = empty_fig()
    if n == 0:
        return (cost_lbl, labor_lbl, line_lbl, acc_lbl, prior_lbl,
                sel_txt, meta_txt,
                "0", "no records match",
                "0", "0% of dataset",
                "—", "", "—", "",
                date_err,
                ef, ef, ef, ef, ef, ef)

    # ── KPIs ──────────────────────────────────────────────────────────────────
    pct_total = n / TOTAL_RECORDS * 100
    n_appr    = int(filt["auto_approved"].sum())
    pct_appr  = n_appr / n * 100
    avg_cost  = filt["est_tot_amt"].mean()
    med_cost  = filt["est_tot_amt"].median()
    med_time  = filt["time_to_approve_hours"].median()
    mean_time = filt["time_to_approve_hours"].mean()

    # ── Chart 1: Approval status donut ───────────────────────────────────────
    sc = filt["repr_auth_stat_typ_dsc"].value_counts()
    STATUS_COLORS = {
        "Approved": EM_GREEN,
        "Pending":  "#F5A623",
        "Denied":   RISK,
        "Hold":     INK_FAINT,
    }
    pie_colors = [STATUS_COLORS.get(lbl, INK_DIM) for lbl in sc.index]
    fig_donut = go.Figure(go.Pie(
        labels=sc.index, values=sc.values, hole=0.62,
        marker=dict(colors=pie_colors, line=dict(color="#fff", width=2)),
        textinfo="percent",
        textfont=dict(size=10, family="IBM Plex Mono, monospace"),
        hovertemplate="%{label}: %{value:,}<extra></extra>",
        sort=False,
    ))
    fig_donut.add_annotation(
        text=f"{pct_appr:.0f}%", x=0.5, y=0.57,
        font=dict(size=24, color=EM_NAVY, family="IBM Plex Mono, monospace"),
        showarrow=False)
    fig_donut.add_annotation(
        text="approved", x=0.5, y=0.40,
        font=dict(size=10, color=INK_FAINT, family="Inter, sans-serif"),
        showarrow=False)
    fig_donut.update_layout(
        **BASE_LAYOUT,
        margin=dict(l=0, r=0, t=8, b=8), showlegend=True,
        legend=dict(font=dict(size=10, family="Inter"), orientation="v",
                    x=0.78, y=0.5, yanchor="middle"))

    # ── Chart 2: Damage breakdown horizontal bar ──────────────────────────────
    dg = (filt.groupby("dmg_dsc", observed=True)
              .agg(total=("est_id", "count"), approved=("auto_approved", "sum"))
              .reset_index()
              .assign(rate=lambda x: x.approved / x.total * 100)
              .sort_values("rate"))
    fig_dmg = go.Figure()
    fig_dmg.add_trace(go.Bar(
        y=dg["dmg_dsc"], x=dg["total"], orientation="h",
        marker_color=EM_SOFT, name="Total",
        hovertemplate="%{y}: %{x:,}<extra>Total</extra>"))
    fig_dmg.add_trace(go.Bar(
        y=dg["dmg_dsc"], x=dg["approved"], orientation="h",
        marker_color=EM_GREEN, name="Approved",
        customdata=dg["rate"],
        hovertemplate="%{y}: %{x:,} approved (%{customdata:.0f}%)<extra></extra>"))
    fig_dmg.update_layout(
        **BASE_LAYOUT, barmode="overlay",
        margin=dict(l=130, r=80, t=10, b=10), showlegend=True,
        legend=dict(font=dict(size=10), orientation="v", x=1.02, y=1, xanchor="left", yanchor="top"),
        xaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=False,
                   tickfont=dict(size=9, family="IBM Plex Mono, monospace")),
        yaxis=dict(showgrid=False,
                   tickfont=dict(size=10, family="Inter, sans-serif")))

    # ── Chart 3: Approval-time histogram (pre-binned — never sends raw rows) ─────
    t_vals = filt["time_to_approve_hours"].dropna()
    counts, edges = np.histogram(t_vals, bins=22)
    mids  = (edges[:-1] + edges[1:]) / 2
    med_v = float(t_vals.median())
    fig_hist = go.Figure(go.Bar(
        x=mids, y=counts, width=(edges[1] - edges[0]) * 0.9,
        marker=dict(color=EM_GREEN, line=dict(color="#fff", width=0.5)),
        opacity=0.88,
        hovertemplate="%{x:.1f}h: %{y:,} estimates<extra></extra>"))
    fig_hist.add_vline(x=med_v, line_dash="dash", line_color=EM_NAVY, line_width=1.5)
    fig_hist.add_annotation(
        x=med_v, y=1, yref="paper",
        text=f" med {med_v:.1f}h", showarrow=False, xanchor="left",
        font=dict(size=9, color=EM_NAVY, family="IBM Plex Mono, monospace"))
    fig_hist.update_layout(
        **BASE_LAYOUT,
        margin=dict(l=48, r=16, t=28, b=36),
        xaxis=dict(showgrid=False, zeroline=False,
                   title=dict(text="hours", font=dict(size=10, color=INK_FAINT)),
                   tickfont=dict(size=9, family="IBM Plex Mono, monospace")),
        yaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=False,
                   tickfont=dict(size=9, family="IBM Plex Mono, monospace")))

    # ── Chart 4: Est. amount box plot by damage type (sampled per group) ─────────
    _fill = {EM_GREEN: "rgba(0,177,64,0.09)", RISK: "rgba(196,69,54,0.09)"}
    _BOX_CAP = 300   # points per damage-type group — keeps JSON tiny
    box_data = (filt.groupby("dmg_dsc", observed=True, group_keys=False)
                    .apply(lambda g: g.sample(min(len(g), _BOX_CAP), random_state=42)))
    fig_box = go.Figure()
    for appr, color, name in [(True, EM_GREEN, "Approved"),
                               (False, RISK,     "Declined / Pending")]:
        sub = box_data[box_data["auto_approved"] == appr]
        if sub.empty:
            continue
        fig_box.add_trace(go.Box(
            x=sub["dmg_dsc"], y=sub["est_tot_amt"], name=name,
            marker=dict(color=color, size=3, opacity=0.6),
            line=dict(color=color, width=1.5),
            fillcolor=_fill[color], boxmean=False,
            hovertemplate="%{x}<br>$%{y:,.0f}<extra>" + name + "</extra>"))
    fig_box.update_layout(
        **BASE_LAYOUT, boxmode="group", showlegend=True,
        legend=dict(font=dict(size=10), orientation="h", x=0, y=1.1),
        margin=dict(l=56, r=16, t=32, b=56),
        yaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=False,
                   tickprefix="$",
                   tickfont=dict(size=9, family="IBM Plex Mono, monospace")),
        xaxis=dict(showgrid=False,
                   tickfont=dict(size=10, family="Inter, sans-serif"),
                   tickangle=-15))

    # ── Chart 5: Submission channel bar ──────────────────────────────────────
    mg = (filt.groupby("create_module", observed=True)
              .agg(total=("est_id", "count"), approved=("auto_approved", "sum"))
              .reset_index()
              .assign(rate=lambda x: x.approved / x.total * 100)
              .sort_values("total", ascending=False))
    fig_mod = go.Figure()
    fig_mod.add_trace(go.Bar(
        x=mg["create_module"], y=mg["total"],
        marker_color=EM_SOFT, name="Total",
        hovertemplate="%{x}: %{y:,}<extra>Total</extra>"))
    fig_mod.add_trace(go.Bar(
        x=mg["create_module"], y=mg["approved"],
        marker_color=EM_GREEN, name="Approved",
        customdata=mg["rate"],
        hovertemplate="%{x}: %{y:,} (%{customdata:.0f}%)<extra>Approved</extra>"))
    fig_mod.update_layout(
        **BASE_LAYOUT, barmode="overlay", showlegend=True,
        legend=dict(font=dict(size=10), orientation="v", x=1.02, y=1, xanchor="left", yanchor="top"),
        margin=dict(l=48, r=80, t=10, b=40),
        xaxis=dict(showgrid=False,
                   tickfont=dict(size=10, family="Inter, sans-serif")),
        yaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=False,
                   tickfont=dict(size=9, family="IBM Plex Mono, monospace")))

    # ── Chart 6: Labor hours vs. est. amount scatter ──────────────────────────
    samp = filt.sample(min(900, n), random_state=42) if n > 900 else filt
    fig_sc = go.Figure()
    for appr, color, name in [(True, EM_GREEN, "Approved"),
                               (False, RISK,    "Not Approved")]:
        sub = samp[samp["auto_approved"] == appr]
        if sub.empty:
            continue
        fig_sc.add_trace(go.Scatter(
            x=sub["lbr_hr_qty"], y=sub["est_tot_amt"],
            mode="markers", name=name,
            marker=dict(color=color, size=5, opacity=0.5, line=dict(width=0)),
            hovertemplate="Labor: %{x:.1f}h<br>Est: $%{y:,.0f}<extra>" + name + "</extra>"))
    fig_sc.update_layout(
        **BASE_LAYOUT, showlegend=True,
        legend=dict(font=dict(size=10), orientation="h", x=0, y=1.1),
        margin=dict(l=56, r=16, t=32, b=44),
        xaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=False,
                   title=dict(text="Labor Hours (lbr_hr_qty)",
                              font=dict(size=10, color=INK_FAINT)),
                   tickfont=dict(size=9, family="IBM Plex Mono, monospace")),
        yaxis=dict(showgrid=True, gridcolor=BORDER, zeroline=False,
                   tickprefix="$",
                   tickfont=dict(size=9, family="IBM Plex Mono, monospace")))

    return (
        cost_lbl, labor_lbl, line_lbl, acc_lbl, prior_lbl,
        sel_txt, meta_txt,
        f"{pct_appr:.1f}", f"{n_appr:,} of {n:,} estimates",
        f"{n:,}",          f"{pct_total:.1f}% of total dataset",
        f"${avg_cost:,.0f}", f"median ${med_cost:,.0f}",
        f"{med_time:.1f}h",  f"mean {mean_time:.1f}h",
        date_err,
        fig_donut, fig_dmg, fig_hist, fig_box, fig_mod, fig_sc,
    )


if __name__ == "__main__":
    print("=" * 50)
    print("  Repair Estimate Rule Simulator")
    print("  http://127.0.0.1:8050")
    print("=" * 50)
    app.run(debug=True, port=8050)
