"""
Streamlit Backtest Dashboard — Interactive UI for NautilusTrader backtests.

Launch:
    streamlit run tools/nautilus_backtest/streamlit_app.py
"""

import subprocess
import sys
import json
import os
import shutil
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Imports from results_manager
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from results_manager import load_positions, compute_stats, RESULTS_DIR, get_folder_size, format_size

NAUTILUS_DIR = Path(__file__).parent
RITHMIC_DIR = NAUTILUS_DIR.parent / "rithmic_adapter"
PYTHON = sys.executable

# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------
STRATEGIES = {
    "MagicLine": {
        "script": "run_magicline.py",
        "params": {
            "length":            {"type": "int",   "default": 20,   "min": 5,   "max": 100, "step": 1,    "label": "LB Period"},
            "touch_tol":         {"type": "int",   "default": 4,    "min": 1,   "max": 20,  "step": 1,    "label": "Touch Tolerance (ticks)"},
            "zone_buffer":       {"type": "float", "default": 1.0,  "min": 0.0, "max": 10.0,"step": 0.25, "label": "Zone Buffer (pts)"},
            "came_from_pts":     {"type": "float", "default": 5.0,  "min": 1.0, "max": 20.0,"step": 0.5,  "label": "Came-From (pts)"},
            "came_from_lookback":{"type": "int",   "default": 10,   "min": 3,   "max": 30,  "step": 1,    "label": "Came-From Lookback"},
            "ema_period":        {"type": "int",   "default": 21,   "min": 5,   "max": 200, "step": 1,    "label": "EMA Period"},
            "no_ema_filter":     {"type": "bool",  "default": False, "label": "Disable EMA Filter"},
            "stop_mode":         {"type": "select","default": 1,    "options": {"Fixed": 0, "Structural": 1}, "label": "Stop Mode"},
            "stop_buffer":       {"type": "int",   "default": 20,   "min": 4,   "max": 80,  "step": 2,    "label": "Stop Buffer (ticks)"},
            "be_trigger":        {"type": "float", "default": 10.0, "min": 0.0, "max": 30.0,"step": 1.0,  "label": "BE Trigger (pts)"},
            "no_be":             {"type": "bool",  "default": False, "label": "Disable Breakeven"},
            "tp1_r":             {"type": "float", "default": 3.0,  "min": 0.5, "max": 10.0,"step": 0.5,  "label": "TP1 R-Multiple"},
            "tp2_r":             {"type": "float", "default": 10.0, "min": 1.0, "max": 30.0,"step": 0.5,  "label": "TP2 R-Multiple"},
            "partial_pct":       {"type": "int",   "default": 25,   "min": 10,  "max": 90,  "step": 5,    "label": "Partial Close %"},
            "no_partial":        {"type": "bool",  "default": False, "label": "Disable Partial"},
            "trade_start":       {"type": "int",   "default": 200,  "min": 0,   "max": 2359,"step": 100,  "label": "Trade Start (HHMM)"},
            "trade_end":         {"type": "int",   "default": 1600, "min": 0,   "max": 2359,"step": 100,  "label": "Trade End (HHMM)"},
            "max_trades":        {"type": "int",   "default": 3,    "min": 1,   "max": 10,  "step": 1,    "label": "Max Trades/Day"},
        },
    },
    "JadeCap": {
        "script": "run_jadecap.py",
        "params": {
            "long_only":         {"type": "bool",  "default": False, "label": "Long Only"},
            "short_only":        {"type": "bool",  "default": False, "label": "Short Only"},
            "entry_model":       {"type": "select","default": 1, "options": {"Immediate": 0, "FVG Only": 1, "Both": 2, "MSS Market": 3}, "label": "Entry Model"},
            "strictness":        {"type": "select","default": 0, "options": {"Aggressive": 0, "Balanced": 1, "Conservative": 2}, "label": "Strictness"},
            "exit_model":        {"type": "select","default": 2, "options": {"RR": 0, "TP1+TP2": 1, "Scale+Trail": 2, "Midday": 3}, "label": "Exit Model"},
            "stop_mode":         {"type": "select","default": 0, "options": {"Fixed": 0, "Structural": 1}, "label": "Stop Mode"},
            "stop_ticks":        {"type": "int",   "default": 40,  "min": 10,  "max": 100, "step": 5,    "label": "Stop (ticks)"},
            "rr_multiple":       {"type": "float", "default": 3.0, "min": 0.5, "max": 10.0,"step": 0.5,  "label": "RR Multiple"},
            "partial_pct":       {"type": "int",   "default": 25,  "min": 10,  "max": 90,  "step": 5,    "label": "Partial %"},
            "no_partial":        {"type": "bool",  "default": False, "label": "Disable Partial"},
            "pivot_strength":    {"type": "int",   "default": 10,  "min": 3,   "max": 50,  "step": 1,    "label": "Pivot Strength"},
            "sweep_min_ticks":   {"type": "int",   "default": 2,   "min": 1,   "max": 10,  "step": 1,    "label": "Sweep Min (ticks)"},
            "fvg_min_ticks":     {"type": "int",   "default": 2,   "min": 1,   "max": 10,  "step": 1,    "label": "FVG Min (ticks)"},
            "max_bars_fill":     {"type": "int",   "default": 30,  "min": 5,   "max": 100, "step": 5,    "label": "Max Bars to Fill"},
            "max_trades":        {"type": "int",   "default": 1,   "min": 1,   "max": 10,  "step": 1,    "label": "Max Trades/Day"},
            "max_per_side":      {"type": "int",   "default": 1,   "min": 1,   "max": 5,   "step": 1,    "label": "Max/Side"},
            "ema_filter":        {"type": "bool",  "default": False, "label": "Enable EMA Filter"},
            "ema_period":        {"type": "int",   "default": 50,  "min": 10,  "max": 200, "step": 5,    "label": "EMA Period"},
        },
    },
    "BrianStonk": {
        "script": "run_brianstonk.py",
        "params": {
            "long_only":         {"type": "bool",  "default": False, "label": "Long Only"},
            "short_only":        {"type": "bool",  "default": False, "label": "Short Only"},
            "target_r":          {"type": "float", "default": 1.0, "min": 0.5, "max": 5.0, "step": 0.25, "label": "Target R"},
            "stop_default":      {"type": "float", "default": 20.0,"min": 5.0, "max": 50.0,"step": 1.0,  "label": "Stop Default (pts)"},
            "stop_min":          {"type": "float", "default": 18.0,"min": 5.0, "max": 40.0,"step": 1.0,  "label": "Stop Min (pts)"},
            "stop_max":          {"type": "float", "default": 25.0,"min": 10.0,"max": 60.0,"step": 1.0,  "label": "Stop Max (pts)"},
            "be_trigger":        {"type": "float", "default": 10.0,"min": 0.0, "max": 30.0,"step": 1.0,  "label": "BE Trigger (pts)"},
            "max_trades":        {"type": "int",   "default": 6,   "min": 1,   "max": 20,  "step": 1,    "label": "Max Trades/Day"},
            "cooldown":          {"type": "int",   "default": 5,   "min": 0,   "max": 30,  "step": 1,    "label": "Cooldown (min)"},
            "fvg_min_gap":       {"type": "float", "default": 2.0, "min": 0.5, "max": 10.0,"step": 0.5,  "label": "FVG Min Gap (pts)"},
        },
    },
    "IFVG": {
        "script": "run_backtest.py",
        "params": {
            "long_only":         {"type": "bool",  "default": False, "label": "Long Only"},
            "short_only":        {"type": "bool",  "default": False, "label": "Short Only"},
            "shadow_threshold":  {"type": "float", "default": 30.0,"min": 10.0,"max": 60.0,"step": 5.0,  "label": "Shadow Threshold %"},
            "max_wait":          {"type": "int",   "default": 30,  "min": 5,   "max": 100, "step": 5,    "label": "Max Wait Bars"},
            "tp1_points":        {"type": "float", "default": 20.0,"min": 5.0, "max": 50.0,"step": 2.5,  "label": "TP1 (pts)"},
            "trail_points":      {"type": "float", "default": 15.0,"min": 5.0, "max": 40.0,"step": 2.5,  "label": "Trail (pts)"},
            "stop_buffer":       {"type": "int",   "default": 40,  "min": 10,  "max": 80,  "step": 5,    "label": "Stop Buffer (ticks)"},
            "stop_max":          {"type": "float", "default": 40.0,"min": 10.0,"max": 80.0,"step": 5.0,  "label": "Stop Max (pts)"},
            "be_trigger":        {"type": "float", "default": 10.0,"min": 0.0, "max": 30.0,"step": 1.0,  "label": "BE Trigger (pts)"},
            "max_trades":        {"type": "int",   "default": 3,   "min": 1,   "max": 10,  "step": 1,    "label": "Max Trades/Day"},
            "regime":            {"type": "bool",  "default": False, "label": "Vol Regime Adaptive"},
        },
    },
    "SwingReclaim": {
        "script": "run_swingreclaim.py",
        "params": {
            "long_only":         {"type": "bool",  "default": False, "label": "Long Only"},
            "short_only":        {"type": "bool",  "default": False, "label": "Short Only"},
            "strength":          {"type": "int",   "default": 45,  "min": 5,   "max": 100, "step": 5,    "label": "Swing Strength"},
            "reclaim_window":    {"type": "int",   "default": 20,  "min": 5,   "max": 60,  "step": 5,    "label": "Reclaim Window"},
            "session_start":     {"type": "int",   "default": 930, "min": 0,   "max": 2359,"step": 100,  "label": "Session Start (HHMM)"},
            "session_end":       {"type": "int",   "default": 1600,"min": 0,   "max": 2359,"step": 100,  "label": "Session End (HHMM)"},
            "enable_session":    {"type": "bool",  "default": False, "label": "Enable Session Window"},
            "max_trades":        {"type": "int",   "default": 3,   "min": 1,   "max": 10,  "step": 1,    "label": "Max Trades/Day"},
            "stop_buffer":       {"type": "int",   "default": 4,   "min": 1,   "max": 20,  "step": 1,    "label": "Stop Buffer (ticks)"},
            "stop_min":          {"type": "float", "default": 2.0, "min": 0.5, "max": 20.0,"step": 0.5,  "label": "Stop Min (pts)"},
            "stop_max":          {"type": "float", "default": 40.0,"min": 5.0, "max": 80.0,"step": 5.0,  "label": "Stop Max (pts)"},
            "be_trigger":        {"type": "float", "default": 10.0,"min": 0.0, "max": 30.0,"step": 1.0,  "label": "BE Trigger (pts)"},
            "no_be":             {"type": "bool",  "default": False, "label": "Disable Breakeven"},
            "tp1_points":        {"type": "float", "default": 20.0,"min": 5.0, "max": 50.0,"step": 2.5,  "label": "TP1 (pts)"},
            "tp1_pct":           {"type": "int",   "default": 50,  "min": 10,  "max": 90,  "step": 5,    "label": "TP1 Partial %"},
            "trail_points":      {"type": "float", "default": 15.0,"min": 5.0, "max": 40.0,"step": 2.5,  "label": "Trail (pts)"},
        },
    },
    "LB Short": {
        "script": "run_lb_short.py",
        "params": {
            "length":            {"type": "int",   "default": 20,   "min": 5,   "max": 100, "step": 1,    "label": "LB Period"},
            "rth_start":         {"type": "int",   "default": 930,  "min": 0,   "max": 2359,"step": 100,  "label": "RTH Start (HHMM)"},
            "rth_end":           {"type": "int",   "default": 1600, "min": 0,   "max": 2359,"step": 100,  "label": "RTH End (HHMM)"},
            "eod_time":          {"type": "int",   "default": 1640, "min": 0,   "max": 2359,"step": 100,  "label": "EOD Flatten (HHMM)"},
            "max_trades":        {"type": "int",   "default": 1,    "min": 1,   "max": 5,   "step": 1,    "label": "Max Trades/Day"},
            "stop_buffer":       {"type": "int",   "default": 20,   "min": 4,   "max": 80,  "step": 2,    "label": "Stop Buffer (ticks)"},
            "be_trigger":        {"type": "float", "default": 10.0, "min": 0.0, "max": 30.0,"step": 1.0,  "label": "BE Trigger (pts)"},
            "no_be":             {"type": "bool",  "default": False, "label": "Disable Breakeven"},
            "tp1_pts":           {"type": "float", "default": 15.0, "min": 5.0, "max": 50.0,"step": 2.5,  "label": "TP1 (pts)"},
            "partial_pct":       {"type": "int",   "default": 25,   "min": 10,  "max": 90,  "step": 5,    "label": "Partial Close %"},
            "trail_pts":         {"type": "float", "default": 5.0,  "min": 1.0, "max": 30.0,"step": 1.0,  "label": "Trail (pts)"},
            "no_ema_filter":     {"type": "bool",  "default": False, "label": "Disable EMA Filter"},
            "ema_period":        {"type": "int",   "default": 50,   "min": 10,  "max": 200, "step": 5,    "label": "EMA Period"},
        },
    },
}


# ========================= CUSTOM CSS =========================

CUSTOM_CSS = """
<style>
/* ---------- Global ---------- */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    color: #f0f2f6 !important;
}

/* Dark background overrides */
.stApp { background: #0e1117; color: #f0f2f6; }
header[data-testid="stHeader"] { background: #0e1117; }

/* ---------- Global white text ---------- */
p, span, label, li, td, th, h1, h2, h3, h4, h5, h6,
div, .stMarkdown, .stText, .stCaption,
[data-testid="stText"], [data-testid="stMarkdownContainer"],
[data-testid="stCaptionContainer"] {
    color: #f0f2f6 !important;
}

/* Input labels and helper text */
.stSelectbox label, .stTextInput label, .stNumberInput label,
.stDateInput label, .stSlider label, .stToggle label,
.stMultiSelect label, .stCheckbox label {
    color: #f0f2f6 !important;
}

/* Selectbox selected value text */
.stSelectbox [data-baseweb="select"] span,
.stMultiSelect [data-baseweb="select"] span {
    color: #f0f2f6 !important;
}

/* Input field text — force light text on dark background for all input types */
.stTextInput input, .stNumberInput input, .stDateInput input,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input,
[data-testid="stDateInput"] input {
    color: #f0f2f6 !important;
    -webkit-text-fill-color: #f0f2f6 !important;
}

/* Expander header text */
details summary span {
    color: #f0f2f6 !important;
}

/* ---------- Dropdown/popover/overlay menus — force black text + white bg ---------- */
[data-baseweb="popover"],
[data-baseweb="popover"] *,
[data-baseweb="menu"],
[data-baseweb="menu"] *,
[data-baseweb="list"],
[data-baseweb="list"] *,
[data-baseweb="select"] [role="listbox"],
[data-baseweb="select"] [role="listbox"] *,
[role="listbox"],
[role="listbox"] *,
[role="option"],
[role="option"] *,
[data-baseweb="popover"] li,
[data-baseweb="popover"] span,
[data-baseweb="popover"] div,
[data-baseweb="popover"] p {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}
[data-baseweb="popover"],
[data-baseweb="menu"],
[role="listbox"] {
    background-color: #ffffff !important;
}

/* Calendar / date-picker — force black text + white bg */
[data-baseweb="calendar"],
[data-baseweb="calendar"] *,
[data-baseweb="datepicker"],
[data-baseweb="datepicker"] *,
.stDateInput [data-baseweb="popover"],
.stDateInput [data-baseweb="popover"] * {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}
[data-baseweb="calendar"],
[data-baseweb="datepicker"] {
    background-color: #ffffff !important;
}

/* Tooltip */
[data-baseweb="tooltip"],
[data-baseweb="tooltip"] * {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}

/* Alert boxes — force black */
div[data-testid="stAlert"] *,
.stAlert * {
    color: #000000 !important;
    -webkit-text-fill-color: #000000 !important;
}

/* ---------- Tab styling ---------- */
.stTabs [data-baseweb="tab-list"] {
    gap: 0;
    background: #131720;
    border-radius: 12px;
    padding: 4px;
    border: 1px solid #1e2530;
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px;
    padding: 10px 24px;
    font-weight: 500;
    font-size: 0.85rem;
    letter-spacing: 0.01em;
    color: #8899aa;
}
.stTabs [aria-selected="true"] {
    background: linear-gradient(135deg, rgba(0,204,150,0.15) 0%, rgba(99,110,250,0.15) 100%);
    color: #e8eaed !important;
    border-bottom: none;
}

/* ---------- Metric cards ---------- */
div[data-testid="stMetric"] {
    background: linear-gradient(135deg, #161b22 0%, #1a1f2e 100%);
    border: 1px solid #2a3040;
    border-radius: 12px;
    padding: 16px 20px;
    transition: border-color 0.2s, transform 0.15s;
}
div[data-testid="stMetric"]:hover {
    border-color: #00cc96;
    transform: translateY(-1px);
}
div[data-testid="stMetric"] label {
    color: #8899aa !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.4rem !important;
    font-weight: 700 !important;
    color: #e8eaed !important;
}

/* ---------- Dataframe / table ---------- */
.stDataFrame {
    border: 1px solid #1e2530;
    border-radius: 12px;
    overflow: hidden;
}
.stDataFrame [data-testid="stDataFrameResizable"] {
    border-radius: 12px;
}

/* ---------- Buttons ---------- */
.stButton > button[kind="primary"],
.stButton > button[data-testid="stBaseButton-primary"] {
    background: linear-gradient(135deg, #00cc96 0%, #00b386 100%);
    border: none;
    border-radius: 10px;
    font-weight: 600;
    letter-spacing: 0.01em;
    transition: all 0.2s;
}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="stBaseButton-primary"]:hover {
    background: linear-gradient(135deg, #00e6a8 0%, #00cc96 100%);
    transform: translateY(-1px);
    box-shadow: 0 4px 16px rgba(0,204,150,0.25);
}
.stButton > button[kind="secondary"],
.stButton > button[data-testid="stBaseButton-secondary"] {
    border: 1px solid #2a3040;
    border-radius: 10px;
    background: #161b22;
    color: #c8d0d8;
    font-weight: 500;
    transition: all 0.2s;
}
.stButton > button[kind="secondary"]:hover,
.stButton > button[data-testid="stBaseButton-secondary"]:hover {
    border-color: #636efa;
    background: #1a1f2e;
}

/* ---------- Inputs ---------- */
.stSelectbox > div > div,
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stDateInput > div > div > input,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input,
[data-testid="stDateInput"] input,
[data-testid="stSelectbox"] > div > div {
    border-radius: 8px !important;
    border-color: #2a3040 !important;
    background: #161b22 !important;
    color: #f0f2f6 !important;
}

/* ---------- Dividers ---------- */
hr {
    border-color: #1e2530 !important;
    opacity: 0.6;
}

/* ---------- Status containers ---------- */
details[data-testid="stExpander"],
div[data-testid="stStatusWidget"] {
    border: 1px solid #1e2530;
    border-radius: 12px;
    background: #131720;
}

/* ---------- Section headers ---------- */
.section-header {
    font-size: 0.7rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #5a6a7a;
    margin-bottom: 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid #1e2530;
}

/* ---------- Delete zone ---------- */
.delete-zone {
    background: rgba(239, 85, 59, 0.05);
    border: 1px solid rgba(239, 85, 59, 0.15);
    border-radius: 12px;
    padding: 16px;
}
</style>
"""


# ========================= HELPER FUNCTIONS =========================

def load_margin_summary(folder: Path) -> dict | None:
    """Load margin_summary.json from a result folder, return None if missing."""
    json_path = folder / "margin_summary.json"
    if not json_path.exists():
        return None
    try:
        with open(json_path) as f:
            return json.load(f)
    except Exception:
        return None


@st.cache_data(ttl=30)
def load_all_results():
    """Scan results directory and load stats for every folder."""
    if not RESULTS_DIR.exists():
        return []
    folders = sorted([f for f in RESULTS_DIR.iterdir() if f.is_dir()])
    rows = []
    for folder in folders:
        df = load_positions(folder)
        if df is None:
            continue
        stats = compute_stats(df)
        stats["label"] = folder.name
        stats["size"] = get_folder_size(folder)
        stats["size_str"] = format_size(stats["size"])
        margin = load_margin_summary(folder)
        stats["margin_status"] = margin["status"] if margin else "N/A"
        stats["margin_calls"] = margin["margin_calls"] if margin else 0
        stats["margin_summary"] = margin
        # Run timestamp from positions.csv modification time
        csv_path = folder / "positions.csv"
        if csv_path.exists():
            mtime = os.path.getmtime(csv_path)
            stats["run_time"] = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
        else:
            stats["run_time"] = ""
        rows.append(stats)
    return rows


def build_equity_chart(df, title="Equity Curve"):
    """Build interactive Plotly equity + drawdown chart."""
    pnls = df["pnl"]
    equity = pnls.cumsum()
    peak = equity.cummax()
    dd = equity - peak

    x = df["ts_closed"] if "ts_closed" in df.columns and not df["ts_closed"].isna().all() else list(range(len(equity)))

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        row_heights=[0.7, 0.3],
    )
    # Equity line with gradient fill
    fig.add_trace(
        go.Scatter(x=x, y=equity, mode="lines", name="Equity",
                   line=dict(color="#00cc96", width=2.5),
                   fill="tozeroy",
                   fillcolor="rgba(0,204,150,0.08)"),
        row=1, col=1,
    )
    # Drawdown fill
    fig.add_trace(
        go.Scatter(x=x, y=dd, mode="lines", name="Drawdown",
                   fill="tozeroy",
                   line=dict(color="#ef553b", width=1.5),
                   fillcolor="rgba(239,85,59,0.12)"),
        row=2, col=1,
    )
    fig.update_layout(
        title=dict(text=title, font=dict(size=14, color="#c8d0d8")),
        height=500, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(14,17,23,1)",
        margin=dict(l=60, r=20, t=45, b=25),
        legend=dict(orientation="h", y=1.06, x=0.5, xanchor="center",
                    font=dict(size=11, color="#8899aa")),
        hovermode="x unified",
        xaxis=dict(gridcolor="#1e2530", zerolinecolor="#1e2530"),
        yaxis=dict(gridcolor="#1e2530", zerolinecolor="#1e2530"),
        xaxis2=dict(gridcolor="#1e2530", zerolinecolor="#1e2530"),
        yaxis2=dict(gridcolor="#1e2530", zerolinecolor="#1e2530"),
    )
    fig.update_yaxes(title_text="P&L ($)", title_font=dict(size=11, color="#5a6a7a"), row=1, col=1)
    fig.update_yaxes(title_text="DD ($)", title_font=dict(size=11, color="#5a6a7a"), row=2, col=1)
    return fig


def build_monthly_heatmap(df):
    """Build monthly P&L heatmap."""
    if "ts_closed" not in df.columns or df["ts_closed"].isna().all():
        return None
    df2 = df.copy()
    df2["month"] = df2["ts_closed"].dt.to_period("M")
    monthly = df2.groupby("month")["pnl"].sum()
    if len(monthly) < 2:
        return None

    periods = monthly.index
    years = sorted(set(p.year for p in periods))
    months = list(range(1, 13))
    month_labels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

    z = []
    for y in years:
        row = []
        for m in months:
            key = pd.Period(f"{y}-{m:02d}", freq="M")
            row.append(monthly.get(key, np.nan))
        z.append(row)

    fig = go.Figure(data=go.Heatmap(
        z=z, x=month_labels, y=[str(y) for y in years],
        colorscale=[[0, "#ef553b"], [0.5, "#0e1117"], [1, "#00cc96"]],
        zmid=0,
        text=[[f"${v:,.0f}" if not np.isnan(v) else "" for v in row] for row in z],
        texttemplate="%{text}", textfont=dict(size=11, color="#c8d0d8"),
        hovertemplate="Year: %{y}<br>Month: %{x}<br>P&L: $%{z:,.0f}<extra></extra>",
        xgap=3, ygap=3,
    ))
    fig.update_layout(
        title=dict(text="Monthly P&L", font=dict(size=13, color="#c8d0d8")),
        height=max(200, 80 + len(years) * 50),
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=50, r=20, t=45, b=25),
    )
    return fig


def build_trade_histogram(df):
    """Build trade P&L distribution histogram."""
    fig = go.Figure()
    wins = df["pnl"][df["pnl"] > 0]
    losses = df["pnl"][df["pnl"] <= 0]
    fig.add_trace(go.Histogram(x=wins, name="Wins", marker_color="rgba(0,204,150,0.7)",
                                marker_line=dict(color="#00cc96", width=1)))
    fig.add_trace(go.Histogram(x=losses, name="Losses", marker_color="rgba(239,85,59,0.7)",
                                marker_line=dict(color="#ef553b", width=1)))
    fig.update_layout(
        title=dict(text="Trade Distribution", font=dict(size=13, color="#c8d0d8")),
        barmode="overlay", template="plotly_dark", height=320,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(14,17,23,1)",
        margin=dict(l=50, r=20, t=45, b=25),
        xaxis_title="P&L ($)", yaxis_title="Count",
        xaxis=dict(gridcolor="#1e2530"), yaxis=dict(gridcolor="#1e2530"),
        legend=dict(font=dict(size=11, color="#8899aa")),
    )
    return fig


ET = ZoneInfo("America/New_York")


def _apply_dark_theme(fig, title=None, height=400):
    """Standardize Plotly dark theme across all charts."""
    layout_opts = dict(
        template="plotly_dark",
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(14,17,23,1)",
        margin=dict(l=60, r=20, t=45, b=25),
        hovermode="x unified",
        legend=dict(orientation="h", y=1.06, x=0.5, xanchor="center",
                    font=dict(size=11, color="#8899aa")),
    )
    if title:
        layout_opts["title"] = dict(text=title, font=dict(size=13, color="#c8d0d8"))
    fig.update_layout(**layout_opts)
    # Apply grid color to all axes
    grid_style = dict(gridcolor="#1e2530", zerolinecolor="#1e2530")
    fig.update_xaxes(**grid_style)
    fig.update_yaxes(**grid_style)
    return fig


def build_monthly_bar_chart(df):
    """Green/red bars per month — clearer than heatmap for magnitude."""
    if "ts_closed" not in df.columns or df["ts_closed"].isna().all():
        return None
    df2 = df.copy()
    df2["month"] = df2["ts_closed"].dt.to_period("M")
    monthly = df2.groupby("month")["pnl"].sum()
    if len(monthly) < 2:
        return None

    labels = [str(p) for p in monthly.index]
    colors = ["#00cc96" if v >= 0 else "#ef553b" for v in monthly.values]

    fig = go.Figure(go.Bar(
        x=labels, y=monthly.values,
        marker_color=colors,
        marker_line=dict(width=0),
        hovertemplate="%{x}<br>P&L: $%{y:,.0f}<extra></extra>",
    ))
    _apply_dark_theme(fig, title="Monthly P&L", height=320)
    fig.update_xaxes(title_text="Month", tickangle=-45)
    fig.update_yaxes(title_text="P&L ($)")
    return fig


def build_direction_stats(df):
    """Split by BUY/SELL direction. Returns None if single-direction strategy."""
    if "entry" not in df.columns:
        return None
    entries = df["entry"].unique()
    if len(entries) < 2:
        return None

    result = {}
    for direction in ("BUY", "SELL"):
        sub = df[df["entry"] == direction]
        if len(sub) == 0:
            continue
        pnls = sub["pnl"]
        wins = pnls[pnls > 0]
        losses = pnls[pnls <= 0]
        n = len(pnls)
        gross_w = wins.sum() if len(wins) > 0 else 0
        gross_l = abs(losses.sum()) if len(losses) > 0 else 0
        result[direction] = {
            "trades": n,
            "total_pnl": pnls.sum(),
            "win_rate": len(wins) / n * 100 if n > 0 else 0,
            "profit_factor": gross_w / gross_l if gross_l > 0 else float("inf"),
            "avg_pnl": pnls.mean(),
            "equity": pnls.cumsum().values,
        }
    return result if len(result) >= 2 else None


def build_direction_equity_chart(dir_stats):
    """Overlaid Long vs Short cumulative P&L lines."""
    if dir_stats is None:
        return None
    fig = go.Figure()
    colors = {"BUY": "#00cc96", "SELL": "#ef553b"}
    labels = {"BUY": "Long", "SELL": "Short"}
    for direction in ("BUY", "SELL"):
        if direction in dir_stats:
            d = dir_stats[direction]
            fig.add_trace(go.Scatter(
                x=list(range(len(d["equity"]))), y=d["equity"],
                mode="lines", name=labels[direction],
                line=dict(color=colors[direction], width=2.5),
            ))
    _apply_dark_theme(fig, title="Long vs Short Equity", height=400)
    fig.update_yaxes(title_text="Cumulative P&L ($)")
    fig.update_xaxes(title_text="Trade #")
    return fig


def build_dow_chart(df):
    """P&L by day-of-week (Mon-Fri) with trade count annotations."""
    if "ts_opened" not in df.columns or df["ts_opened"].isna().all():
        return None
    df2 = df.copy()
    df2["dow"] = df2["ts_opened"].dt.tz_convert(ET).dt.dayofweek
    dow_pnl = df2.groupby("dow")["pnl"].agg(["sum", "count"])
    all_dow_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    # Include weekend days only if trades exist there
    max_dow = max(dow_pnl.index.max(), 4)  # at least Mon-Fri
    day_range = range(max_dow + 1)
    dow_labels = [all_dow_labels[i] for i in day_range]
    # Fill missing days
    all_days = pd.DataFrame({"sum": 0.0, "count": 0}, index=day_range)
    all_days.update(dow_pnl)

    colors = ["#00cc96" if v >= 0 else "#ef553b" for v in all_days["sum"].values]

    fig = go.Figure(go.Bar(
        x=dow_labels, y=all_days["sum"].values,
        marker_color=colors,
        text=[f"n={int(c)}" for c in all_days["count"].values],
        textposition="outside",
        textfont=dict(size=10, color="#8899aa"),
        hovertemplate="%{x}<br>P&L: $%{y:,.0f}<extra></extra>",
    ))
    _apply_dark_theme(fig, title="P&L by Day of Week", height=350)
    fig.update_yaxes(title_text="P&L ($)")
    return fig


def build_hour_chart(df):
    """P&L by entry hour (ET) — shows which hours are profitable."""
    if "ts_opened" not in df.columns or df["ts_opened"].isna().all():
        return None
    df2 = df.copy()
    df2["hour"] = df2["ts_opened"].dt.tz_convert(ET).dt.hour
    hour_pnl = df2.groupby("hour")["pnl"].agg(["sum", "count"])

    hours = list(range(hour_pnl.index.min(), hour_pnl.index.max() + 1))
    pnls = [hour_pnl.loc[h, "sum"] if h in hour_pnl.index else 0 for h in hours]
    counts = [int(hour_pnl.loc[h, "count"]) if h in hour_pnl.index else 0 for h in hours]
    hour_labels = [f"{h:02d}:00" for h in hours]
    colors = ["#00cc96" if v >= 0 else "#ef553b" for v in pnls]

    fig = go.Figure(go.Bar(
        x=hour_labels, y=pnls,
        marker_color=colors,
        text=[f"n={c}" for c in counts],
        textposition="outside",
        textfont=dict(size=10, color="#8899aa"),
        hovertemplate="%{x}<br>P&L: $%{y:,.0f}<extra></extra>",
    ))
    _apply_dark_theme(fig, title="P&L by Entry Hour (ET)", height=350)
    fig.update_yaxes(title_text="P&L ($)")
    return fig


def build_streak_stats(df):
    """Returns max win streak, max loss streak, current streak."""
    if len(df) == 0:
        return None
    wins = (df["pnl"] > 0).astype(int)
    max_win = max_loss = cur = 0
    cur_type = None
    for w in wins:
        if w == 1:
            if cur_type == "win":
                cur += 1
            else:
                cur = 1
                cur_type = "win"
            max_win = max(max_win, cur)
        else:
            if cur_type == "loss":
                cur += 1
            else:
                cur = 1
                cur_type = "loss"
            max_loss = max(max_loss, cur)
    return {
        "max_win_streak": max_win,
        "max_loss_streak": max_loss,
        "current_streak": cur,
        "current_type": cur_type or "N/A",
    }


def build_risk_metrics(df):
    """Calmar ratio, recovery factor, avg duration, expectancy, % profitable months."""
    pnls = df["pnl"]
    equity = pnls.cumsum()
    peak = equity.cummax()
    max_dd = abs((equity - peak).min())
    total_pnl = pnls.sum()
    n = len(pnls)

    # Calmar = annualized return / max DD
    calmar = 0.0
    if max_dd > 0 and "ts_closed" in df.columns and not df["ts_closed"].isna().all():
        days = (df["ts_closed"].max() - df["ts_closed"].min()).days
        if days > 0:
            annual_return = total_pnl * (365.25 / days)
            calmar = annual_return / max_dd

    recovery_factor = total_pnl / max_dd if max_dd > 0 else float("inf")

    avg_duration = df["duration_min"].mean() if "duration_min" in df.columns else None

    expectancy = pnls.mean() if n > 0 else 0

    # % profitable months
    pct_profitable_months = 0.0
    if "ts_closed" in df.columns and not df["ts_closed"].isna().all():
        monthly = df.copy()
        monthly["month"] = monthly["ts_closed"].dt.to_period("M")
        mpnl = monthly.groupby("month")["pnl"].sum()
        if len(mpnl) > 0:
            pct_profitable_months = (mpnl > 0).sum() / len(mpnl) * 100

    return {
        "calmar": calmar,
        "recovery_factor": recovery_factor,
        "avg_duration_min": avg_duration,
        "expectancy": expectancy,
        "pct_profitable_months": pct_profitable_months,
    }


def build_duration_histogram(df):
    """Histogram of trade durations in minutes."""
    if "duration_min" not in df.columns or df["duration_min"].isna().all():
        return None
    fig = go.Figure(go.Histogram(
        x=df["duration_min"].dropna(),
        nbinsx=30,
        marker_color="rgba(99,110,250,0.7)",
        marker_line=dict(color="#636efa", width=1),
        hovertemplate="Duration: %{x:.0f} min<br>Count: %{y}<extra></extra>",
    ))
    _apply_dark_theme(fig, title="Trade Duration Distribution", height=320)
    fig.update_xaxes(title_text="Duration (min)")
    fig.update_yaxes(title_text="Count")
    return fig


def build_duration_scatter(df):
    """Scatter: duration vs P&L colored by win/loss."""
    if "duration_min" not in df.columns or df["duration_min"].isna().all():
        return None
    df2 = df.dropna(subset=["duration_min"])
    colors = ["#00cc96" if p > 0 else "#ef553b" for p in df2["pnl"]]

    fig = go.Figure(go.Scatter(
        x=df2["duration_min"], y=df2["pnl"],
        mode="markers",
        marker=dict(color=colors, size=6, opacity=0.7,
                    line=dict(width=0.5, color="#1e2530")),
        hovertemplate="Duration: %{x:.0f} min<br>P&L: $%{y:,.0f}<extra></extra>",
    ))
    _apply_dark_theme(fig, title="Duration vs P&L", height=350)
    fig.update_xaxes(title_text="Duration (min)")
    fig.update_yaxes(title_text="P&L ($)")
    return fig


def build_expectancy_curve(df):
    """Expanding mean P&L per trade over time."""
    if len(df) < 2:
        return None
    expanding_mean = df["pnl"].expanding().mean()

    fig = go.Figure(go.Scatter(
        x=list(range(1, len(expanding_mean) + 1)),
        y=expanding_mean,
        mode="lines",
        line=dict(color="#636efa", width=2.5),
        fill="tozeroy",
        fillcolor="rgba(99,110,250,0.08)",
        hovertemplate="Trade #%{x}<br>Avg P&L: $%{y:,.2f}<extra></extra>",
    ))
    _apply_dark_theme(fig, title="Expectancy Curve (Expanding Avg P&L)", height=350)
    fig.update_xaxes(title_text="Trade #")
    fig.update_yaxes(title_text="Avg P&L ($)")
    return fig


def build_rolling_stats_chart(df, window=30):
    """3-line chart: rolling Sharpe, Win Rate, Profit Factor."""
    if len(df) < window:
        return None
    pnls = df["pnl"]

    # Rolling Sharpe (annualized)
    rolling_mean = pnls.rolling(window).mean()
    rolling_std = pnls.rolling(window).std()
    rolling_sharpe = (rolling_mean / rolling_std) * np.sqrt(252)
    rolling_sharpe = rolling_sharpe.replace([np.inf, -np.inf], np.nan)

    # Rolling win rate
    rolling_wr = pnls.rolling(window).apply(lambda x: (x > 0).sum() / len(x) * 100, raw=True)

    # Rolling profit factor
    def _pf(x):
        w = x[x > 0].sum()
        l = abs(x[x <= 0].sum())
        return w / l if l > 0 else 0
    rolling_pf = pnls.rolling(window).apply(_pf, raw=True)
    rolling_pf = rolling_pf.clip(upper=10)  # cap for display

    x = list(range(len(pnls)))

    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(
        go.Scatter(x=x, y=rolling_sharpe, mode="lines", name="Sharpe",
                   line=dict(color="#636efa", width=2)),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=x, y=rolling_pf, mode="lines", name="Profit Factor",
                   line=dict(color="#ffa15a", width=2)),
        secondary_y=False,
    )
    fig.add_trace(
        go.Scatter(x=x, y=rolling_wr, mode="lines", name="Win Rate %",
                   line=dict(color="#00cc96", width=2, dash="dot")),
        secondary_y=True,
    )
    _apply_dark_theme(fig, title=f"Rolling Stats (window={window})", height=420)
    fig.update_yaxes(title_text="Sharpe / PF", secondary_y=False)
    fig.update_yaxes(title_text="Win Rate %", secondary_y=True)
    fig.update_xaxes(title_text="Trade #")
    return fig


def build_winrate_by_month_chart(df):
    """Monthly win rate trend line."""
    if "ts_closed" not in df.columns or df["ts_closed"].isna().all():
        return None
    df2 = df.copy()
    df2["month"] = df2["ts_closed"].dt.to_period("M")
    monthly = df2.groupby("month")["pnl"].agg(
        win_rate=lambda x: (x > 0).sum() / len(x) * 100,
        count="count",
    )
    if len(monthly) < 2:
        return None

    labels = [str(p) for p in monthly.index]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=labels, y=monthly["win_rate"],
        mode="lines+markers",
        line=dict(color="#00cc96", width=2.5),
        marker=dict(size=6),
        hovertemplate="%{x}<br>WR: %{y:.1f}%<extra></extra>",
    ))
    fig.add_hline(y=50, line=dict(color="#5a6a7a", width=1, dash="dash"))
    _apply_dark_theme(fig, title="Monthly Win Rate Trend", height=320)
    fig.update_yaxes(title_text="Win Rate %")
    fig.update_xaxes(tickangle=-45)
    return fig


def build_trade_table(df):
    """Formatted DataFrame for the Trades tab."""
    cols = {}
    if "ts_opened" in df.columns and not df["ts_opened"].isna().all():
        cols["Date (ET)"] = df["ts_opened"].dt.tz_convert(ET).dt.strftime("%Y-%m-%d %H:%M")
    if "entry" in df.columns:
        cols["Direction"] = df["entry"]
    if "avg_px_open" in df.columns:
        cols["Entry Price"] = df["avg_px_open"].apply(lambda x: f"{x:,.2f}" if pd.notna(x) else "")
    if "avg_px_close" in df.columns:
        cols["Exit Price"] = df["avg_px_close"].apply(lambda x: f"{x:,.2f}" if pd.notna(x) else "")
    cols["P&L"] = df["pnl"].apply(lambda x: f"${x:,.2f}")
    cols["Cum P&L"] = df["pnl"].cumsum().apply(lambda x: f"${x:,.2f}")
    if "duration_min" in df.columns:
        cols["Duration"] = df["duration_min"].apply(lambda x: f"{x:.0f} min" if pd.notna(x) else "")
    if "peak_qty" in df.columns:
        cols["Size"] = df["peak_qty"].apply(lambda x: f"{int(x)}" if pd.notna(x) else "")
    return pd.DataFrame(cols)


def render_param_controls(params: dict, prefix: str, overrides: dict | None = None) -> dict:
    """Render strategy-specific parameter controls.

    Args:
        params: Parameter spec dict from STRATEGIES registry.
        prefix: Unique key prefix for Streamlit widgets.
        overrides: Optional dict of current values (e.g. from config.yaml)
                   to use instead of the spec defaults.
    """
    ovr = overrides or {}
    values = {}
    keys = list(params.keys())
    col1, col2 = st.columns(2)
    for i, key in enumerate(keys):
        p = params[key]
        cur = ovr.get(key, p["default"])
        target = col1 if i % 2 == 0 else col2
        with target:
            if p["type"] == "int":
                # Cast ALL params to Python int for Streamlit type consistency
                try:
                    val = int(cur)
                except (ValueError, TypeError):
                    val = int(p["default"])
                mn = int(p["min"])
                mx = int(p["max"])
                stp = int(p["step"])
                val = max(mn, min(mx, val))
                values[key] = st.number_input(
                    p["label"], value=val, min_value=mn,
                    max_value=mx, step=stp, key=f"{prefix}_{key}")
            elif p["type"] == "float":
                # Cast ALL params to Python float for Streamlit type consistency
                try:
                    val = float(cur)
                except (ValueError, TypeError):
                    val = float(p["default"])
                mn = float(p["min"])
                mx = float(p["max"])
                stp = float(p["step"])
                val = max(mn, min(mx, val))
                values[key] = st.number_input(
                    p["label"], value=val, min_value=mn,
                    max_value=mx, step=stp, format="%.2f",
                    key=f"{prefix}_{key}")
            elif p["type"] == "bool":
                values[key] = st.toggle(p["label"], value=bool(cur), key=f"{prefix}_{key}")
            elif p["type"] == "select":
                options = p["options"]
                labels = list(options.keys())
                # Find index matching current value, fall back to default
                vals = list(options.values())
                if cur in vals:
                    idx = vals.index(cur)
                else:
                    idx = vals.index(p["default"]) if p["default"] in vals else 0
                choice = st.selectbox(p["label"], labels, index=idx, key=f"{prefix}_{key}")
                values[key] = options[choice]
    return values


def sanitize_label(label: str) -> str:
    """Sanitize label for use as a directory name (no spaces, colons, etc.)."""
    import re
    label = label.strip()
    label = re.sub(r'[<>:"/\\|?*]', '', label)  # remove illegal Windows path chars
    label = re.sub(r'\s+', '_', label)            # spaces to underscores
    return label or "unnamed"


def build_cli_args(strategy_name, common, specific):
    """Build command-line argument list for a runner script."""
    args = [
        "--start", common["start"],
        "--end", common["end"],
        "--bar-minutes", str(common["bar_minutes"]),
        "--label", sanitize_label(common["label"]),
        "--contracts", str(common["contracts"]),
    ]
    if common["mes"]:
        args.append("--mes")
    if common["vix_filter"]:
        args.append("--vix-filter")
    if common["dollars_per_contract"] > 0:
        args.extend(["--dollars-per-contract", str(common["dollars_per_contract"])])

    for key, val in specific.items():
        cli_key = f"--{key.replace('_', '-')}"
        pdef = STRATEGIES[strategy_name]["params"][key]
        if pdef["type"] == "bool":
            if val:
                args.append(cli_key)
        elif pdef["type"] == "select":
            args.extend([cli_key, str(val)])
        else:
            args.extend([cli_key, str(val)])

    return args


# ========================= PAGE CONFIG =========================

st.set_page_config(
    page_title="Backtest Dashboard",
    page_icon=":chart_with_upwards_trend:",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ========================= DATA LOAD =========================

results = load_all_results()

# ========================= TABS =========================

tab_results, tab_run, tab_wf, tab_compare, tab_live = st.tabs([
    "Results", "Run Backtest", "Walk-Forward", "Compare", "Live Trading"
])

# ================================================================
# TAB 1 — RESULTS DASHBOARD
# ================================================================

with tab_results:
    if not results:
        st.info("No result folders found. Run a backtest first.")
    else:
        # Sort by most recent run first
        sorted_results = sorted(results, key=lambda r: r.get("run_time", ""), reverse=True)

        # Build dropdown options: "label — run_time"
        dropdown_options = [
            f"{r['label']}  —  {r['run_time']}" if r.get("run_time") else r["label"]
            for r in sorted_results
        ]
        label_map = {opt: r["label"] for opt, r in zip(dropdown_options, sorted_results)}

        col_select, col_refresh = st.columns([5, 1])
        with col_select:
            chosen = st.selectbox(
                "Select result", dropdown_options, index=0,
                key="results_select", label_visibility="collapsed",
            )
        with col_refresh:
            if st.button("Refresh", type="secondary", use_container_width=True):
                load_all_results.clear()
                st.rerun()

        if chosen:
            selected_label = label_map[chosen]
            selected = next((r for r in sorted_results if r["label"] == selected_label), None)

            if selected:
                # Metric cards row — always visible
                c1, c2, c3, c4, c5, c6 = st.columns(6)
                pnl_val = selected['total_pnl']
                c1.metric("Total P&L", f"${pnl_val:,.0f}")
                c2.metric("Sharpe", f"{selected['sharpe']:.2f}")
                c3.metric("Win Rate", f"{selected['win_rate']:.1f}%")
                pf = selected["profit_factor"]
                c4.metric("Profit Factor", f"{pf:.2f}" if pf < 100 else "inf")
                c5.metric("Max Drawdown", f"${selected['max_dd']:,.0f}")
                c6.metric("Trades", f"{selected['trades']}")

                # Load data for sub-tabs
                folder = RESULTS_DIR / selected_label
                df = load_positions(folder)
                margin_data = selected.get("margin_summary")
                margin_chart_path = folder / "margin_analysis.png"

                # Determine which tabs to show
                has_data = df is not None and len(df) > 0
                dir_stats = build_direction_stats(df) if has_data else None
                has_direction = dir_stats is not None
                has_margin = margin_data is not None or margin_chart_path.exists()

                tab_names = ["Overview"]
                if has_direction:
                    tab_names.append("Direction")
                tab_names.extend(["Time Analysis", "Trade Analysis", "Rolling Stats", "Trades"])
                if has_margin:
                    tab_names.append("Margin")

                detail_tabs = st.tabs(tab_names)
                tab_idx = 0

                # --- OVERVIEW TAB ---
                with detail_tabs[tab_idx]:
                    tab_idx += 1
                    if has_data:
                        fig = build_equity_chart(df, title=f"{selected_label}")
                        st.plotly_chart(fig, use_container_width=True, key="detail_equity")

                        bar_fig = build_monthly_bar_chart(df)
                        if bar_fig:
                            st.plotly_chart(bar_fig, use_container_width=True, key="detail_monthly_bar")

                        hm_col, hist_col = st.columns(2)
                        with hm_col:
                            hm_fig = build_monthly_heatmap(df)
                            if hm_fig:
                                st.plotly_chart(hm_fig, use_container_width=True, key="detail_heatmap")
                        with hist_col:
                            hist_fig = build_trade_histogram(df)
                            st.plotly_chart(hist_fig, use_container_width=True, key="detail_hist")
                    else:
                        st.info("No position data available.")

                # --- DIRECTION TAB ---
                if has_direction:
                    with detail_tabs[tab_idx]:
                        tab_idx += 1
                        dc1, dc2 = st.columns(2)
                        for side, col in [("BUY", dc1), ("SELL", dc2)]:
                            if side in dir_stats:
                                d = dir_stats[side]
                                label_text = "Long" if side == "BUY" else "Short"
                                with col:
                                    st.markdown(f"**{label_text}**")
                                    sc1, sc2 = st.columns(2)
                                    sc1.metric(f"{label_text} P&L", f"${d['total_pnl']:,.0f}")
                                    sc2.metric(f"{label_text} Trades", f"{d['trades']}")
                                    sc3, sc4 = st.columns(2)
                                    sc3.metric(f"{label_text} Win Rate", f"{d['win_rate']:.1f}%")
                                    pf_val = d['profit_factor']
                                    sc4.metric(f"{label_text} PF", f"{pf_val:.2f}" if pf_val < 100 else "inf")

                        dir_eq_fig = build_direction_equity_chart(dir_stats)
                        if dir_eq_fig:
                            st.plotly_chart(dir_eq_fig, use_container_width=True, key="detail_dir_equity")
                else:
                    pass

                # --- TIME ANALYSIS TAB ---
                with detail_tabs[tab_idx]:
                    tab_idx += 1
                    if has_data:
                        ta1, ta2 = st.columns(2)
                        with ta1:
                            dow_fig = build_dow_chart(df)
                            if dow_fig:
                                st.plotly_chart(dow_fig, use_container_width=True, key="detail_dow")
                            else:
                                st.info("No timestamp data for day-of-week analysis.")
                        with ta2:
                            hour_fig = build_hour_chart(df)
                            if hour_fig:
                                st.plotly_chart(hour_fig, use_container_width=True, key="detail_hour")
                            else:
                                st.info("No timestamp data for hour analysis.")
                    else:
                        st.info("No position data available.")

                # --- TRADE ANALYSIS TAB ---
                with detail_tabs[tab_idx]:
                    tab_idx += 1
                    if has_data:
                        risk = build_risk_metrics(df)
                        rm1, rm2, rm3, rm4, rm5 = st.columns(5)
                        rm1.metric("Calmar Ratio", f"{risk['calmar']:.2f}")
                        rf_val = risk['recovery_factor']
                        rm2.metric("Recovery Factor", f"{rf_val:.2f}" if rf_val < 100 else "inf")
                        dur_val = risk['avg_duration_min']
                        rm3.metric("Avg Duration", f"{dur_val:.0f} min" if pd.notna(dur_val) else "N/A")
                        rm4.metric("Expectancy", f"${risk['expectancy']:,.2f}")
                        rm5.metric("Profitable Months", f"{risk['pct_profitable_months']:.0f}%")

                        streak = build_streak_stats(df)
                        if streak:
                            sk1, sk2, sk3 = st.columns(3)
                            sk1.metric("Best Win Streak", f"{streak['max_win_streak']}")
                            sk2.metric("Worst Loss Streak", f"{streak['max_loss_streak']}")
                            cur_label = f"{streak['current_streak']} ({'W' if streak['current_type'] == 'win' else 'L'})"
                            sk3.metric("Current Streak", cur_label)

                        ta_c1, ta_c2 = st.columns(2)
                        with ta_c1:
                            hist_fig = build_trade_histogram(df)
                            st.plotly_chart(hist_fig, use_container_width=True, key="detail_hist_ta")
                        with ta_c2:
                            dur_hist = build_duration_histogram(df)
                            if dur_hist:
                                st.plotly_chart(dur_hist, use_container_width=True, key="detail_dur_hist")
                            else:
                                st.info("No duration data available.")

                        ta_c3, ta_c4 = st.columns(2)
                        with ta_c3:
                            dur_scatter = build_duration_scatter(df)
                            if dur_scatter:
                                st.plotly_chart(dur_scatter, use_container_width=True, key="detail_dur_scatter")
                        with ta_c4:
                            exp_fig = build_expectancy_curve(df)
                            if exp_fig:
                                st.plotly_chart(exp_fig, use_container_width=True, key="detail_expectancy")
                    else:
                        st.info("No position data available.")

                # --- ROLLING STATS TAB ---
                with detail_tabs[tab_idx]:
                    tab_idx += 1
                    if has_data:
                        min_trades = 10
                        if len(df) < min_trades:
                            st.info(f"Need at least {min_trades} trades for rolling statistics.")
                        else:
                            window = st.slider(
                                "Rolling Window", min_value=10, max_value=min(100, len(df)),
                                value=min(30, len(df)), step=5, key="rolling_window",
                            )
                            roll_fig = build_rolling_stats_chart(df, window=window)
                            if roll_fig:
                                st.plotly_chart(roll_fig, use_container_width=True, key="detail_rolling")
                            else:
                                st.info(f"Not enough trades for window size {window}.")

                            wr_month_fig = build_winrate_by_month_chart(df)
                            if wr_month_fig:
                                st.plotly_chart(wr_month_fig, use_container_width=True, key="detail_wr_month")
                    else:
                        st.info("No position data available.")

                # --- TRADES TAB ---
                with detail_tabs[tab_idx]:
                    tab_idx += 1
                    if has_data:
                        trade_df = build_trade_table(df)
                        st.download_button(
                            "Export CSV",
                            data=trade_df.to_csv(index=False),
                            file_name=f"{selected_label}_trades.csv",
                            mime="text/csv",
                            key="export_trades_csv",
                        )
                        st.dataframe(
                            trade_df, use_container_width=True, hide_index=True,
                            height=min(600, 45 + len(trade_df) * 38),
                            key="detail_trade_table",
                        )
                    else:
                        st.info("No position data available.")

                # --- MARGIN TAB ---
                if has_margin:
                    with detail_tabs[tab_idx]:
                        tab_idx += 1
                        if margin_data:
                            mc1, mc2, mc3, mc4 = st.columns(4)
                            status = margin_data["status"]
                            mc1.metric("Status", status)
                            mc2.metric("Margin Calls", margin_data["margin_calls"])
                            mc3.metric("Max Shortfall", f"${margin_data['max_shortfall']:,.0f}")
                            day_m = margin_data.get("day_trade_margin", 0)
                            elev_m = margin_data.get("elevated_margin", 0)
                            mc4.metric("Margins", f"Day ${day_m:,} / Elev ${elev_m:,}")

                            if margin_data.get("top_violations"):
                                with st.expander(f"Violation Details ({margin_data['total_violations']} bars)"):
                                    vdf = pd.DataFrame(margin_data["top_violations"])
                                    st.dataframe(vdf, use_container_width=True, hide_index=True)

                        if margin_chart_path.exists():
                            st.image(str(margin_chart_path), use_container_width=True)

                # Delete zone — always visible below tabs
                st.markdown("")
                with st.container():
                    st.markdown('<div class="delete-zone">', unsafe_allow_html=True)
                    dc1, dc2, _ = st.columns([1, 1, 4])
                    with dc1:
                        confirm_delete = st.checkbox("Confirm delete", key="confirm_del")
                    with dc2:
                        if st.button("Delete Result", type="primary", disabled=not confirm_delete):
                            shutil.rmtree(folder)
                            load_all_results.clear()
                            st.success(f"Deleted {selected_label}")
                            st.rerun()
                    st.markdown('</div>', unsafe_allow_html=True)


# ================================================================
# TAB 2 — RUN BACKTEST
# ================================================================

with tab_run:
    st.markdown('<p class="section-header">Strategy & Common Settings</p>', unsafe_allow_html=True)

    # Strategy picker — prominent
    strategy_name = st.selectbox("Strategy", list(STRATEGIES.keys()), key="run_strategy")

    com1, com2, com3 = st.columns(3)
    with com1:
        start_date = st.date_input("Start Date", value=date(2024, 1, 1), key="run_start")
        end_date = st.date_input("End Date", value=date(2026, 1, 1), key="run_end")
    with com2:
        mes = st.toggle("Use MES ($5/pt)", value=False, key="run_mes")
        vix_filter = st.toggle("VIX Filter", value=False, key="run_vix")
        bar_minutes = st.number_input("Bar Minutes", value=5, min_value=1, max_value=60, step=1, key="run_bar_min")
    with com3:
        contracts = st.number_input("Contracts", value=10, min_value=1, max_value=100, step=1, key="run_contracts")
        dpc = st.number_input("$/Contract (0=fixed)", value=0.0, min_value=0.0, step=500.0, key="run_dpc")
        label = st.text_input("Label", value=strategy_name.lower().replace(" ", "_"), key="run_label")

    st.markdown(f'<p class="section-header">{strategy_name} Parameters</p>', unsafe_allow_html=True)
    specific_vals = render_param_controls(STRATEGIES[strategy_name]["params"], f"run_{strategy_name}")

    st.markdown("")
    if st.button("Run Backtest", type="primary", use_container_width=True, key="run_btn"):
        common = {
            "start": start_date.isoformat(),
            "end": end_date.isoformat(),
            "mes": mes,
            "vix_filter": vix_filter,
            "bar_minutes": bar_minutes,
            "contracts": contracts,
            "dollars_per_contract": dpc,
            "label": label,
        }
        cli_args = build_cli_args(strategy_name, common, specific_vals)
        script = STRATEGIES[strategy_name]["script"]
        cmd = [PYTHON, "-u", script] + cli_args

        with st.status(f"Running {strategy_name} backtest...", expanded=True) as status:
            st.code(" ".join(cmd), language="bash")
            log_area = st.empty()
            log_lines = []

            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=str(NAUTILUS_DIR), text=True, bufsize=1,
                encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )

            for line in proc.stdout:
                log_lines.append(line.rstrip())
                display = "\n".join(log_lines[-30:])
                log_area.code(display, language="text")

            proc.wait()
            load_all_results.clear()
            if proc.returncode == 0:
                status.update(label="Backtest completed!", state="complete")
            else:
                status.update(label=f"Backtest exited with code {proc.returncode}", state="error")

        # Refresh page so Results tab picks up new data
        st.rerun()


# ================================================================
# TAB 3 — WALK-FORWARD
# ================================================================

with tab_wf:
    st.markdown('<p class="section-header">Walk-Forward Settings</p>', unsafe_allow_html=True)
    st.info("Currently supports **IFVG** strategy only.")

    wf1, wf2 = st.columns(2)
    with wf1:
        wf_start = st.date_input("Start Date", value=date(2022, 1, 1), key="wf_start")
        wf_end = st.date_input("End Date", value=date(2026, 1, 1), key="wf_end")
        wf_is_months = st.number_input("IS Months", value=12, min_value=3, max_value=36, step=1, key="wf_is")
        wf_oos_months = st.number_input("OOS Months", value=3, min_value=1, max_value=12, step=1, key="wf_oos")
    with wf2:
        wf_metric = st.selectbox("Optimization Metric", ["sharpe", "total_pnl", "profit_factor", "win_rate"],
                                  key="wf_metric")
        wf_workers = st.number_input("Workers", value=1, min_value=1, max_value=8, step=1, key="wf_workers")
        wf_mes = st.toggle("Use MES", value=True, key="wf_mes")
        wf_vix = st.toggle("VIX Filter", value=False, key="wf_vix")
        wf_contracts = st.number_input("Contracts", value=2, min_value=1, max_value=50, step=1, key="wf_contracts")

    st.markdown('<p class="section-header">Parameter Grid</p>', unsafe_allow_html=True)
    default_grid = {
        "shadow_threshold_pct": "20, 30, 40",
        "tp1_points": "15, 20, 25, 30",
        "trail_points": "10, 15, 20",
        "stop_buffer_ticks": "20, 40, 60",
        "be_trigger_pts": "8, 10, 15",
    }

    grid_values = {}
    gc1, gc2 = st.columns(2)
    for i, (param, default_csv) in enumerate(default_grid.items()):
        target = gc1 if i % 2 == 0 else gc2
        with target:
            val = st.text_input(param, value=default_csv, key=f"wf_grid_{param}")
            try:
                parsed = [float(x.strip()) for x in val.split(",") if x.strip()]
                grid_values[param] = parsed
            except ValueError:
                grid_values[param] = []

    combos = 1
    for vals in grid_values.values():
        combos *= max(len(vals), 1)
    st.caption(f"Total combinations: **{combos:,}**")

    st.markdown("")
    if st.button("Run Walk-Forward", type="primary", use_container_width=True, key="wf_btn"):
        grid_path = NAUTILUS_DIR / "_wf_grid_temp.json"
        export_grid = {}
        for k, v in grid_values.items():
            if k in ("stop_buffer_ticks",):
                export_grid[k] = [int(x) for x in v]
            else:
                export_grid[k] = v
        with open(grid_path, "w") as f:
            json.dump(export_grid, f)

        cmd = [
            PYTHON, "-u", "walk_forward.py",
            "--start", wf_start.isoformat(),
            "--end", wf_end.isoformat(),
            "--is-months", str(wf_is_months),
            "--oos-months", str(wf_oos_months),
            "--metric", wf_metric,
            "--workers", str(wf_workers),
            "--contracts", str(wf_contracts),
            "--param-grid", str(grid_path),
        ]
        if wf_mes:
            cmd.append("--mes")
        if wf_vix:
            cmd.append("--vix-filter")

        with st.status("Running walk-forward optimization...", expanded=True) as status:
            st.code(" ".join(cmd), language="bash")
            log_area = st.empty()
            log_lines = []

            proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                cwd=str(NAUTILUS_DIR), text=True, bufsize=1,
                encoding="utf-8", errors="replace",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )

            for line in proc.stdout:
                log_lines.append(line.rstrip())
                display = "\n".join(log_lines[-30:])
                log_area.code(display, language="text")

            proc.wait()
            load_all_results.clear()
            grid_path.unlink(missing_ok=True)
            if proc.returncode == 0:
                status.update(label="Walk-forward completed!", state="complete")
            else:
                status.update(label=f"Walk-forward exited with code {proc.returncode}", state="error")

        # Refresh page so Results tab picks up new data
        st.rerun()


# ================================================================
# TAB 4 — COMPARE
# ================================================================

with tab_compare:
    if not results:
        st.info("No results to compare. Run some backtests first.")
    else:
        labels = [r["label"] for r in results]
        selected_labels = st.multiselect("Select results to compare", labels,
                                          default=labels[:2] if len(labels) >= 2 else labels,
                                          key="compare_select")

        if len(selected_labels) < 2:
            st.warning("Select at least 2 results to compare.")
        else:
            # Overlaid equity curves
            colors = ["#00cc96", "#636efa", "#ef553b", "#ffa15a", "#ab63fa",
                      "#19d3f3", "#ff6692", "#b6e880"]
            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                row_heights=[0.7, 0.3],
            )

            for i, lbl in enumerate(selected_labels):
                folder = RESULTS_DIR / lbl
                df = load_positions(folder)
                if df is None:
                    continue
                pnls = df["pnl"]
                equity = pnls.cumsum()
                peak = equity.cummax()
                dd = equity - peak
                color = colors[i % len(colors)]

                x = df["ts_closed"] if "ts_closed" in df.columns and not df["ts_closed"].isna().all() else list(range(len(equity)))

                fig.add_trace(
                    go.Scatter(x=x, y=equity, mode="lines", name=lbl,
                               line=dict(color=color, width=2.5)),
                    row=1, col=1,
                )
                fig.add_trace(
                    go.Scatter(x=x, y=dd, mode="lines", name=f"{lbl} DD",
                               line=dict(color=color, width=1, dash="dot"),
                               showlegend=False),
                    row=2, col=1,
                )

            fig.update_layout(
                height=540, template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(14,17,23,1)",
                margin=dict(l=60, r=20, t=30, b=25),
                legend=dict(orientation="h", y=1.06, x=0.5, xanchor="center",
                            font=dict(size=11, color="#8899aa")),
                hovermode="x unified",
                xaxis=dict(gridcolor="#1e2530"), yaxis=dict(gridcolor="#1e2530"),
                xaxis2=dict(gridcolor="#1e2530"), yaxis2=dict(gridcolor="#1e2530"),
            )
            fig.update_yaxes(title_text="P&L ($)", title_font=dict(size=11, color="#5a6a7a"), row=1, col=1)
            fig.update_yaxes(title_text="DD ($)", title_font=dict(size=11, color="#5a6a7a"), row=2, col=1)
            st.plotly_chart(fig, use_container_width=True)

            # Comparison table with column_config
            comp_rows = []
            for lbl in selected_labels:
                sel = next((r for r in results if r["label"] == lbl), None)
                if sel:
                    pf = sel["profit_factor"]
                    comp_rows.append({
                        "Label": lbl,
                        "Trades": int(sel["trades"]),
                        "Total P&L": round(sel["total_pnl"], 0),
                        "Win Rate": round(sel["win_rate"], 1),
                        "PF": round(pf, 2) if pf < 100 else None,
                        "Sharpe": round(sel["sharpe"], 2),
                        "Max DD": round(sel["max_dd"], 0),
                        "Avg Win": round(sel["avg_win"], 0),
                        "Avg Loss": round(sel["avg_loss"], 0),
                    })

            if comp_rows:
                cdf = pd.DataFrame(comp_rows)
                comp_config = {
                    "Label": st.column_config.TextColumn("Label", width="medium"),
                    "Trades": st.column_config.NumberColumn("Trades", format="%d"),
                    "Total P&L": st.column_config.NumberColumn("Total P&L", format="$%,.0f"),
                    "Win Rate": st.column_config.ProgressColumn("Win Rate", format="%.1f%%", min_value=0, max_value=100),
                    "PF": st.column_config.NumberColumn("PF", format="%.2f"),
                    "Sharpe": st.column_config.NumberColumn("Sharpe", format="%.2f"),
                    "Max DD": st.column_config.NumberColumn("Max DD", format="$%,.0f"),
                    "Avg Win": st.column_config.NumberColumn("Avg Win", format="$%,.0f"),
                    "Avg Loss": st.column_config.NumberColumn("Avg Loss", format="$%,.0f"),
                }
                st.dataframe(cdf, use_container_width=True, hide_index=True,
                             column_config=comp_config)


# ================================================================
# TAB 5 — LIVE TRADING
# ================================================================

def _load_rithmic_config():
    """Load rithmic adapter config.yaml as dict, or None."""
    cfg_path = RITHMIC_DIR / "config.yaml"
    if not cfg_path.exists():
        return None
    try:
        import yaml
        with open(cfg_path) as f:
            return yaml.safe_load(f)
    except Exception:
        return None


def _load_live_state():
    """Load live adapter state.json, or None."""
    state_path = RITHMIC_DIR / "logs" / "state.json"
    if not state_path.exists():
        return None
    try:
        with open(state_path) as f:
            return json.load(f)
    except Exception:
        return None


def _load_equity_log():
    """Load equity snapshots from equity.jsonl."""
    log_path = RITHMIC_DIR / "logs" / "equity.jsonl"
    if not log_path.exists():
        return []
    records = []
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
    except Exception:
        pass
    return records


def build_live_equity_chart(equity_records):
    """Build Plotly equity + position chart from live equity snapshots."""
    if not equity_records:
        return None

    df = pd.DataFrame(equity_records)
    df["ts"] = pd.to_datetime(df["ts"])

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
        row_heights=[0.7, 0.3],
    )

    # Realized P&L line
    fig.add_trace(
        go.Scatter(x=df["ts"], y=df["realized"], mode="lines", name="Realized P&L",
                   line=dict(color="#00cc96", width=2.5),
                   fill="tozeroy", fillcolor="rgba(0,204,150,0.08)"),
        row=1, col=1,
    )
    # Total (realized + unrealized) as a lighter overlay
    fig.add_trace(
        go.Scatter(x=df["ts"], y=df["total"], mode="lines", name="Total (incl. unrealized)",
                   line=dict(color="#636efa", width=1.5, dash="dot")),
        row=1, col=1,
    )

    # Drawdown on realized
    realized = pd.Series(df["realized"].values)
    peak = realized.cummax()
    dd = realized - peak
    fig.add_trace(
        go.Scatter(x=df["ts"], y=dd, mode="lines", name="Drawdown",
                   line=dict(color="#ef553b", width=1), visible="legendonly",
                   fill="tozeroy", fillcolor="rgba(239,85,59,0.1)"),
        row=1, col=1,
    )

    # Position qty in bottom panel
    fig.add_trace(
        go.Scatter(x=df["ts"], y=df["qty"], mode="lines", name="Position",
                   line=dict(color="#ffa15a", width=1.5),
                   fill="tozeroy", fillcolor="rgba(255,161,90,0.1)"),
        row=2, col=1,
    )

    fig.update_layout(
        height=480, template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(14,17,23,1)",
        margin=dict(l=60, r=20, t=45, b=25),
        legend=dict(orientation="h", y=1.08, x=0.5, xanchor="center",
                    font=dict(size=11, color="#8899aa")),
        hovermode="x unified",
        xaxis=dict(gridcolor="#1e2530", zerolinecolor="#1e2530"),
        yaxis=dict(gridcolor="#1e2530", zerolinecolor="#1e2530"),
        xaxis2=dict(gridcolor="#1e2530", zerolinecolor="#1e2530"),
        yaxis2=dict(gridcolor="#1e2530", zerolinecolor="#1e2530"),
    )
    fig.update_yaxes(title_text="P&L ($)", title_font=dict(size=11, color="#5a6a7a"), row=1, col=1)
    fig.update_yaxes(title_text="Qty", title_font=dict(size=11, color="#5a6a7a"), row=2, col=1)
    return fig


def _load_trade_log():
    """Load completed trades from trades.jsonl."""
    log_path = RITHMIC_DIR / "logs" / "trades.jsonl"
    if not log_path.exists():
        return []
    trades = []
    try:
        with open(log_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    trades.append(json.loads(line))
    except Exception:
        pass
    return trades


def _get_latest_log_file():
    """Find the most recent adapter log file."""
    log_dir = RITHMIC_DIR / "logs"
    if not log_dir.exists():
        return None
    logs = sorted(log_dir.glob("adapter_*.log"), reverse=True)
    return logs[0] if logs else None


def _tail_log(path, n=50):
    """Read last N lines from a log file."""
    if path is None or not path.exists():
        return ""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:])
    except Exception:
        return ""


def _is_adapter_running():
    """Check if run_live.py process is running."""
    try:
        import psutil
        for proc in psutil.process_iter(["pid", "cmdline"]):
            cmdline = proc.info.get("cmdline") or []
            if any("run_live.py" in arg for arg in cmdline):
                return proc.info["pid"]
    except ImportError:
        pass
    return None


with tab_live:
    # ------ Header ------
    cfg = _load_rithmic_config()
    adapter_pid = _is_adapter_running()
    has_config = cfg is not None

    # Status bar
    sc1, sc2, sc3, sc4 = st.columns(4)
    with sc1:
        if adapter_pid:
            st.metric("Adapter Status", "RUNNING")
        else:
            st.metric("Adapter Status", "STOPPED")
    with sc2:
        if has_config:
            rith = cfg.get("rithmic", {})
            st.metric("System", rith.get("system", "N/A")[:25])
        else:
            st.metric("System", "No Config")
    with sc3:
        if has_config:
            rith = cfg.get("rithmic", {})
            raw_sym = rith.get("symbol", "?")
            # If auto-roll is on, resolve to show the actual contract
            if rith.get("auto_roll", True):
                try:
                    sys.path.insert(0, str(RITHMIC_DIR))
                    from contract_roller import resolve_front_month, parse_symbol, _SYMBOL_RE
                    if _SYMBOL_RE.match(raw_sym.upper()):
                        root_sym, _, _ = parse_symbol(raw_sym)
                    else:
                        root_sym = raw_sym.upper()
                    resolved = resolve_front_month(root_sym, roll_days=rith.get("roll_days_before", 8))
                    st.metric("Symbol", f"{resolved}/{rith.get('exchange', '?')}")
                except Exception:
                    st.metric("Symbol", f"{raw_sym}/{rith.get('exchange', '?')}")
                finally:
                    if str(RITHMIC_DIR) in sys.path:
                        sys.path.remove(str(RITHMIC_DIR))
            else:
                st.metric("Symbol", f"{raw_sym}/{rith.get('exchange', '?')}")
        else:
            st.metric("Symbol", "N/A")
    with sc4:
        state = _load_live_state()
        if state and state.get("trade", {}).get("entry_price", 0) > 0:
            trade = state["trade"]
            direction = trade.get("direction", 1)
            dir_label = "SHORT" if direction < 0 else "LONG"
            st.metric("Position", f"{dir_label} @ {trade['entry_price']:.2f}")
        else:
            st.metric("Position", "FLAT")

    # ------ Sub-tabs ------
    live_tab_names = ["Controls", "Position", "Trade Log", "Adapter Log"]
    lt_controls, lt_position, lt_trades, lt_log = st.tabs(live_tab_names)

    # ------ CONTROLS ------
    with lt_controls:
        if not has_config:
            st.warning(
                f"No `config.yaml` found in `{RITHMIC_DIR}`.\n\n"
                "Copy `config.yaml.example` to `config.yaml` and fill in your Rithmic credentials."
            )
        else:
            rith = cfg.get("rithmic", {})
            strat = cfg.get("strategy", {})
            risk = cfg.get("risk", {})
            is_locked = adapter_pid is not None

            st.markdown('<p class="section-header">Connection</p>', unsafe_allow_html=True)
            cc1, cc2 = st.columns(2)
            with cc1:
                live_uri = st.text_input("URI", value=rith.get("uri", "wss://rituz00100.rithmic.com:443"),
                                         disabled=is_locked, key="live_uri")
                live_user = st.text_input("User", value=rith.get("user", ""),
                                          disabled=is_locked, key="live_user")
                live_system = st.text_input("System", value=rith.get("system", "Rithmic Paper Trading"),
                                            disabled=is_locked, key="live_system")
            with cc2:
                live_acct = st.text_input("Account ID", value=rith.get("account_id", ""),
                                          disabled=is_locked, key="live_acct")
                live_password = st.text_input("Password", value=rith.get("password", ""),
                                              type="password", disabled=is_locked, key="live_pass")
                cc2a, cc2b = st.columns(2)
                with cc2a:
                    live_exchange = st.text_input("Exchange", value=rith.get("exchange", "CME"),
                                                  disabled=is_locked, key="live_exchange")
                with cc2b:
                    _COMMON_ROOTS = ["ES", "MES", "NQ", "MNQ", "YM", "MYM", "RTY", "M2K", "CL", "GC", "SI", "HG"]
                    _raw_sym = rith.get("symbol", "ES")
                    # If it's a full symbol like "ESH6", extract root for the selectbox
                    try:
                        sys.path.insert(0, str(RITHMIC_DIR))
                        from contract_roller import parse_symbol as _ps, _SYMBOL_RE as _sre
                        if _sre.match(_raw_sym.upper()):
                            _display_root, _, _ = _ps(_raw_sym)
                        else:
                            _display_root = _raw_sym.upper()
                    except Exception:
                        _display_root = _raw_sym.upper()
                    finally:
                        if str(RITHMIC_DIR) in sys.path:
                            sys.path.remove(str(RITHMIC_DIR))

                    _root_idx = _COMMON_ROOTS.index(_display_root) if _display_root in _COMMON_ROOTS else 0
                    live_symbol = st.selectbox(
                        "Root Symbol", _COMMON_ROOTS, index=_root_idx,
                        disabled=is_locked, key="live_symbol",
                    )

            # Auto-roll controls
            _auto_roll_val = rith.get("auto_roll", True)
            _roll_days_val = int(rith.get("roll_days_before", 8) or 8)
            ar1, ar2, ar3 = st.columns([1, 1, 4])
            with ar1:
                live_auto_roll = st.toggle("Auto Roll", value=_auto_roll_val,
                                           disabled=is_locked, key="live_auto_roll")
            with ar2:
                live_roll_days = st.number_input(
                    "Roll Days Before Expiry", value=_roll_days_val,
                    min_value=int(1), max_value=int(15), step=int(1),
                    disabled=is_locked or not live_auto_roll, key="live_roll_days")
            with ar3:
                # Show resolved contract info
                if live_auto_roll:
                    try:
                        sys.path.insert(0, str(RITHMIC_DIR))
                        from contract_roller import resolve_front_month, next_roll_date as _nrd
                        _resolved = resolve_front_month(live_symbol, roll_days=live_roll_days)
                        _roll_dt = _nrd(live_symbol, roll_days=live_roll_days)
                        st.markdown(f"Currently: **{_resolved}** — rolls {_roll_dt.strftime('%b %d, %Y')}")
                    except Exception:
                        st.caption("Could not resolve contract")
                    finally:
                        if str(RITHMIC_DIR) in sys.path:
                            sys.path.remove(str(RITHMIC_DIR))

            # Strategy selector (interactive — changes are saved to config.yaml)
            live_strat_names = list(STRATEGIES.keys())
            current_strat = strat.get("name", "MagicLine")
            strat_idx = live_strat_names.index(current_strat) if current_strat in live_strat_names else 0
            selected_strat = st.selectbox(
                "Active Strategy", live_strat_names, index=strat_idx,
                disabled=adapter_pid is not None,
                key="live_strat_name",
            )

            # Shared params (editable)
            st.markdown('<p class="section-header">Shared Parameters</p>', unsafe_allow_html=True)
            sp1, sp2, sp3, sp4 = st.columns(4)
            with sp1:
                _contracts = int(strat.get("contracts", 1) or 1)
                live_contracts = st.number_input(
                    "Contracts", value=_contracts,
                    min_value=int(1), max_value=int(50), step=int(1),
                    disabled=is_locked, key="live_qty")
            with sp2:
                live_eod = st.text_input(
                    "EOD Flatten", value=str(strat.get("eod_flatten_time", "15:45")),
                    disabled=is_locked, key="live_eod")
            with sp3:
                _bar_size = int(strat.get("bar_size_minutes", 5) or 5)
                live_bar_size = st.number_input(
                    "Bar Size (min)", value=_bar_size,
                    min_value=int(1), max_value=int(60), step=int(1),
                    disabled=is_locked, key="live_bar_size")
            with sp4:
                _tick = float(strat.get("tick_size", 0.25) or 0.25)
                live_tick = st.number_input(
                    "Tick Size", value=_tick,
                    min_value=float(0.01), max_value=float(10.0), step=float(0.01),
                    format="%.2f",
                    disabled=is_locked, key="live_tick")

            # Dynamic strategy-specific params (editable via render_param_controls)
            # Pass config.yaml values as overrides when viewing the currently-configured strategy
            st.markdown(f'<p class="section-header">{selected_strat} Parameters</p>', unsafe_allow_html=True)
            if selected_strat in STRATEGIES:
                cfg_overrides = strat if selected_strat == current_strat else None
                live_specific = render_param_controls(
                    STRATEGIES[selected_strat]["params"], f"live_{selected_strat}",
                    overrides=cfg_overrides,
                )
            else:
                live_specific = {}

            # Risk limits (editable — must be above Save Config so variables are defined)
            st.markdown('<p class="section-header">Risk Limits</p>', unsafe_allow_html=True)
            rk1, rk2, rk3 = st.columns(3)
            live_max_loss = rk1.number_input(
                "Max Daily Loss ($)", value=float(risk.get("max_daily_loss", 500.0) or 500.0),
                min_value=float(50), max_value=float(10000), step=float(50),
                disabled=is_locked, key="live_max_loss", format="%.0f")
            live_max_qty = rk2.number_input(
                "Max Contracts", value=int(risk.get("max_contracts", 5) or 5),
                min_value=int(1), max_value=int(50), step=int(1),
                disabled=is_locked, key="live_max_qty")
            live_paper_mode = rk3.selectbox(
                "Paper Mode", options=[True, False],
                index=0 if cfg.get("paper_mode", True) else 1,
                disabled=is_locked, key="live_paper")

            # Save Config button
            strategy_changed = selected_strat != current_strat
            if strategy_changed:
                st.info(f"Strategy changed: **{current_strat}** → **{selected_strat}**. Click Save to apply.")

            if st.button("Save Config", type="primary" if strategy_changed else "secondary",
                         disabled=adapter_pid is not None,
                         key="live_save_cfg", use_container_width=False):
                import yaml
                # Build updated strategy block
                new_strat = {"name": selected_strat, "bar_size_minutes": live_bar_size}
                new_strat["contracts"] = live_contracts
                new_strat["eod_flatten_time"] = live_eod
                new_strat["tick_size"] = live_tick
                # Merge strategy-specific params
                for k, v in live_specific.items():
                    new_strat[k] = v
                # Build connection & risk from editable fields
                new_cfg = {
                    "rithmic": {
                        "uri": live_uri,
                        "system": live_system,
                        "user": live_user,
                        "password": live_password,
                        "exchange": live_exchange,
                        "symbol": live_symbol,
                        "account_id": live_acct,
                        "auto_roll": live_auto_roll,
                        "roll_days_before": live_roll_days,
                    },
                    "strategy": new_strat,
                    "risk": {
                        "max_daily_loss": live_max_loss,
                        "max_contracts": live_max_qty,
                        "stale_tick_seconds": int(risk.get("stale_tick_seconds", 30) or 30),
                    },
                    "paper_mode": live_paper_mode,
                    "log_dir": cfg.get("log_dir", "./logs"),
                }
                cfg_path = RITHMIC_DIR / "config.yaml"
                with open(cfg_path, "w") as f:
                    yaml.dump(new_cfg, f, default_flow_style=False, sort_keys=False)
                st.success(f"Config saved — strategy: **{selected_strat}**")
                st.rerun()

            st.markdown("")
            st.markdown('<p class="section-header">Launch</p>', unsafe_allow_html=True)

            lc1, lc2, lc3 = st.columns([2, 2, 2])
            with lc1:
                dry_run = st.toggle("Dry Run (no orders)", value=True, key="live_dry_run")
            with lc2:
                log_level = st.selectbox("Log Level", ["INFO", "DEBUG", "WARNING"],
                                         key="live_log_level")

            btn1, btn2, _ = st.columns([1, 1, 4])
            with btn1:
                if st.button("Start Adapter", type="primary", disabled=adapter_pid is not None,
                             key="live_start_btn", use_container_width=True):
                    cmd = [PYTHON, "-u", "run_live.py", "--log-level", log_level]
                    if dry_run:
                        cmd.append("--dry-run")

                    # Launch as background process
                    proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        cwd=str(RITHMIC_DIR),
                        text=True,
                        encoding="utf-8",
                        errors="replace",
                        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
                    )
                    st.session_state["live_pid"] = proc.pid
                    st.success(f"Adapter started (PID {proc.pid})" +
                               (" — DRY RUN mode" if dry_run else " — LIVE mode"))
                    st.rerun()

            with btn2:
                if st.button("Stop Adapter", type="secondary", disabled=adapter_pid is None,
                             key="live_stop_btn", use_container_width=True):
                    if adapter_pid:
                        try:
                            import psutil
                            p = psutil.Process(adapter_pid)
                            p.terminate()
                            p.wait(timeout=10)
                            st.success(f"Adapter stopped (PID {adapter_pid})")
                        except ImportError:
                            if sys.platform == "win32":
                                subprocess.run(["taskkill", "/PID", str(adapter_pid), "/F"],
                                               capture_output=True)
                            else:
                                os.kill(adapter_pid, 15)  # SIGTERM
                            st.success(f"Kill signal sent to PID {adapter_pid}")
                        except Exception as e:
                            st.error(f"Failed to stop: {e}")
                        st.rerun()

            if adapter_pid:
                st.info(f"Adapter is running (PID {adapter_pid}). "
                        "Check Position and Adapter Log tabs for real-time status.")

    # ------ POSITION MONITOR ------
    with lt_position:
        col_refresh, _ = st.columns([1, 5])
        with col_refresh:
            if st.button("Refresh", type="secondary", key="live_pos_refresh"):
                st.rerun()

        # Equity curve (always try to show)
        equity_data = _load_equity_log()
        if equity_data:
            eq_fig = build_live_equity_chart(equity_data)
            if eq_fig:
                st.plotly_chart(eq_fig, use_container_width=True, key="live_equity_chart")
        else:
            st.caption("Equity curve will appear once the adapter starts processing bars.")

        state = _load_live_state()
        if state is None:
            st.info("No live state found. Start the adapter to begin monitoring.")
        else:
            trade = state.get("trade", {})
            is_active = trade.get("entry_price", 0) > 0

            # Top metrics
            pm1, pm2, pm3, pm4, pm5 = st.columns(5)
            trade_dir = trade.get("direction", 1)
            dir_label = "SHORT" if trade_dir < 0 else "LONG"
            pm1.metric("Status", f"{dir_label}" if is_active else "FLAT")
            pm2.metric("Daily P&L", f"${state.get('daily_pnl', 0):,.2f}")
            pm3.metric("Trades Today", state.get("trades_today", 0))
            pm4.metric("Bars Processed", state.get("bar_count", 0))
            ema_val = state.get("ema_value")
            pm5.metric("EMA", f"{ema_val:.2f}" if ema_val is not None else "Warming up")

            if is_active:
                st.markdown('<p class="section-header">Active Trade</p>', unsafe_allow_html=True)
                tc1, tc2, tc3, tc4 = st.columns(4)
                tc1.metric("Entry", f"{trade['entry_price']:.2f}")
                tc2.metric("Stop", f"{trade.get('stop_price', 0):.2f}")
                tc3.metric("TP1", f"{trade.get('tp1_price', 0):.2f}")
                tc4.metric("TP2", f"{trade.get('tp2_price', 0):.2f}")

                ts1, ts2, ts3, ts4 = st.columns(4)
                ts1.metric("Risk", f"{trade.get('risk_points', 0):.1f} pts")
                ts2.metric("Qty", trade.get("initial_qty", 0))
                ts3.metric("BE Activated", "Yes" if trade.get("be_activated") else "No")
                ts4.metric("Partial Taken", "Yes" if trade.get("partial_taken") else "No")

                # Trade visualization (direction-aware)
                entry = trade["entry_price"]
                stop = trade.get("stop_price", 0)
                tp1 = trade.get("tp1_price", 0)
                tp2 = trade.get("tp2_price", 0)
                is_short = trade.get("direction", 1) < 0
                if stop > 0 and (tp2 > 0 or tp1 > 0):
                    tp_far = tp2 if tp2 > 0 else tp1
                    fig = go.Figure()
                    fig.add_hline(y=entry, line=dict(color="#636efa", width=2),
                                  annotation_text="Entry", annotation_position="right")
                    fig.add_hline(y=stop, line=dict(color="#ef553b", width=2, dash="dash"),
                                  annotation_text="Stop", annotation_position="right")
                    if tp1 > 0:
                        fig.add_hline(y=tp1, line=dict(color="#00cc96", width=1.5, dash="dot"),
                                      annotation_text="TP1", annotation_position="right")
                    if tp2 > 0:
                        fig.add_hline(y=tp2, line=dict(color="#00cc96", width=2),
                                      annotation_text="TP2", annotation_position="right")

                    if is_short:
                        # Short: stop above entry, targets below
                        fig.add_hrect(y0=entry, y1=stop,
                                      fillcolor="rgba(239,85,59,0.08)", line_width=0)
                        fig.add_hrect(y0=tp_far, y1=entry,
                                      fillcolor="rgba(0,204,150,0.05)", line_width=0)
                    else:
                        # Long: stop below entry, targets above
                        fig.add_hrect(y0=stop, y1=entry,
                                      fillcolor="rgba(239,85,59,0.08)", line_width=0)
                        fig.add_hrect(y0=entry, y1=tp_far,
                                      fillcolor="rgba(0,204,150,0.05)", line_width=0)

                    all_levels = [v for v in [stop, entry, tp1, tp2] if v > 0]
                    lo, hi = min(all_levels), max(all_levels)
                    margin = (hi - lo) * 0.05
                    fig.update_yaxes(range=[lo - margin, hi + margin])
                    _apply_dark_theme(fig, title=f"{'Short' if is_short else 'Long'} Trade Levels", height=300)
                    fig.update_xaxes(visible=False)
                    st.plotly_chart(fig, use_container_width=True, key="live_trade_levels")

            # Recent bar history
            bars = state.get("bars", [])
            if bars and len(bars) > 0:
                with st.expander(f"Bar History ({len(bars)} bars)", expanded=False):
                    recent = bars[-20:]
                    bar_df = pd.DataFrame(recent)
                    bar_df.index = range(len(bars) - len(recent), len(bars))
                    bar_df.index.name = "Bar #"
                    st.dataframe(bar_df.style.format("{:.2f}"),
                                 use_container_width=True, key="live_bar_hist")

            st.caption(f"Last saved: {state.get('saved_at', 'unknown')}")

    # ------ TRADE LOG ------
    with lt_trades:
        trades = _load_trade_log()
        if not trades:
            st.info("No completed trades logged yet.")
        else:
            st.markdown(f"**{len(trades)} completed trades**")
            trade_rows = []
            for t in reversed(trades):  # newest first
                trade_rows.append({
                    "Time": t.get("timestamp", "")[:19],
                    "Reason": t.get("reason", ""),
                    "Entry": t.get("entry_price", ""),
                    "Stop": t.get("stop_price", ""),
                    "Note": t.get("note", ""),
                })
            tdf = pd.DataFrame(trade_rows)
            st.dataframe(tdf, use_container_width=True, hide_index=True,
                         height=min(600, 45 + len(tdf) * 38),
                         key="live_trade_log")

    # ------ ADAPTER LOG ------
    with lt_log:
        log_file = _get_latest_log_file()

        lc1, lc2, _ = st.columns([1, 2, 3])
        with lc1:
            if st.button("Refresh Log", type="secondary", key="live_log_refresh"):
                st.rerun()
        with lc2:
            n_lines = st.selectbox("Lines", [25, 50, 100, 200], index=1, key="live_log_lines")

        if log_file:
            st.caption(f"Reading: `{log_file.name}`")
            log_text = _tail_log(log_file, n=n_lines)
            if log_text:
                st.code(log_text, language="text")
            else:
                st.info("Log file is empty.")
        else:
            st.info("No adapter log files found. Start the adapter to generate logs.")
