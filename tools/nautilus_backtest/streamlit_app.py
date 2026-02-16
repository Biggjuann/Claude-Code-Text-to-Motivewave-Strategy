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
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

# ---------------------------------------------------------------------------
# Imports from results_manager
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from results_manager import load_positions, compute_stats, RESULTS_DIR, get_folder_size, format_size

NAUTILUS_DIR = Path(__file__).parent
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
}

/* Dark background overrides */
.stApp { background: #0e1117; }
header[data-testid="stHeader"] { background: #0e1117; }

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #131720 0%, #0e1117 100%);
    border-right: 1px solid #1e2530;
}
section[data-testid="stSidebar"] .stMarkdown h1 {
    background: linear-gradient(135deg, #00cc96 0%, #636efa 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-size: 1.5rem;
    font-weight: 700;
    letter-spacing: -0.02em;
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
.stDateInput > div > div > input {
    border-radius: 8px !important;
    border-color: #2a3040 !important;
    background: #161b22 !important;
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
        rows.append(stats)
    return rows


def build_results_dataframe(results_list):
    """Build a properly typed pandas DataFrame for the results table."""
    rows = []
    for r in results_list:
        pf = r["profit_factor"]
        rows.append({
            "Label": r["label"],
            "Strategy": r.get("strategy", ""),
            "Trades": int(r["trades"]),
            "Total P&L": round(r["total_pnl"], 0),
            "Win Rate": round(r["win_rate"], 1),
            "PF": round(pf, 2) if pf < 100 else None,
            "Sharpe": round(r["sharpe"], 2),
            "Max DD": round(r["max_dd"], 0),
            "Period": f"{r['start_date']}  {r['end_date']}" if r.get("start_date") else "",
        })
    return pd.DataFrame(rows)


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


def render_param_controls(params: dict, prefix: str) -> dict:
    """Render strategy-specific parameter controls."""
    values = {}
    keys = list(params.keys())
    col1, col2 = st.columns(2)
    for i, key in enumerate(keys):
        p = params[key]
        target = col1 if i % 2 == 0 else col2
        with target:
            if p["type"] == "int":
                values[key] = st.number_input(
                    p["label"], value=p["default"], min_value=p["min"],
                    max_value=p["max"], step=p["step"], key=f"{prefix}_{key}")
            elif p["type"] == "float":
                values[key] = st.number_input(
                    p["label"], value=p["default"], min_value=p["min"],
                    max_value=p["max"], step=p["step"], format="%.2f",
                    key=f"{prefix}_{key}")
            elif p["type"] == "bool":
                values[key] = st.toggle(p["label"], value=p["default"], key=f"{prefix}_{key}")
            elif p["type"] == "select":
                options = p["options"]
                labels = list(options.keys())
                idx = list(options.values()).index(p["default"])
                choice = st.selectbox(p["label"], labels, index=idx, key=f"{prefix}_{key}")
                values[key] = options[choice]
    return values


def build_cli_args(strategy_name, common, specific):
    """Build command-line argument list for a runner script."""
    args = [
        "--start", common["start"],
        "--end", common["end"],
        "--bar-minutes", str(common["bar_minutes"]),
        "--label", common["label"],
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
    initial_sidebar_state="expanded",
)

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ========================= SIDEBAR =========================

with st.sidebar:
    st.title("Backtest Dashboard")
    st.caption("NautilusTrader Suite")
    st.divider()

    results = load_all_results()
    folder_count = len(results)
    total_size = sum(r.get("size", 0) for r in results)

    sc1, sc2 = st.columns(2)
    sc1.metric("Results", folder_count)
    sc2.metric("Disk", format_size(total_size))

    st.divider()
    if st.button("Refresh", use_container_width=True, type="secondary"):
        load_all_results.clear()
        st.rerun()

# ========================= TABS =========================

tab_results, tab_run, tab_wf, tab_compare = st.tabs([
    "Results", "Run Backtest", "Walk-Forward", "Compare"
])

# ================================================================
# TAB 1 — RESULTS DASHBOARD
# ================================================================

with tab_results:
    if not results:
        st.info("No result folders found. Run a backtest first.")
    else:
        # Filters row
        col_filter, col_sort, _ = st.columns([2, 1, 1])
        with col_filter:
            name_filter = st.text_input("Filter", "", key="results_filter",
                                        placeholder="Search by name...",
                                        label_visibility="collapsed")
        with col_sort:
            sort_col = st.selectbox("Sort by", ["total_pnl", "sharpe", "win_rate",
                                                 "profit_factor", "max_dd", "trades", "label"],
                                    index=0, key="results_sort",
                                    label_visibility="collapsed")

        filtered = results
        if name_filter:
            search = name_filter.lower()
            filtered = [r for r in results if search in r["label"].lower()
                        or search in r.get("strategy", "").lower()]

        reverse = sort_col != "label"
        filtered.sort(key=lambda r: r.get(sort_col, 0), reverse=reverse)

        # Build proper DataFrame with column_config
        if filtered:
            tdf = build_results_dataframe(filtered)

            col_config = {
                "Label": st.column_config.TextColumn("Label", width="medium"),
                "Strategy": st.column_config.TextColumn("Strategy", width="small"),
                "Trades": st.column_config.NumberColumn("Trades", format="%d", width="small"),
                "Total P&L": st.column_config.NumberColumn(
                    "Total P&L", format="$%,.0f", width="small",
                ),
                "Win Rate": st.column_config.ProgressColumn(
                    "Win Rate", format="%.1f%%", min_value=0, max_value=100, width="small",
                ),
                "PF": st.column_config.NumberColumn("PF", format="%.2f", width="small"),
                "Sharpe": st.column_config.NumberColumn("Sharpe", format="%.2f", width="small"),
                "Max DD": st.column_config.NumberColumn("Max DD", format="$%,.0f", width="small"),
                "Period": st.column_config.TextColumn("Period", width="medium"),
            }

            event = st.dataframe(
                tdf,
                use_container_width=True,
                hide_index=True,
                height=min(420, 45 + len(tdf) * 38),
                column_config=col_config,
                on_select="rerun",
                selection_mode="single-row",
                key="results_table",
            )

            # Detail panel — use table selection or fallback to selectbox
            st.markdown("")  # spacer
            selected_idx = None
            if event and event.selection and event.selection.rows:
                selected_idx = event.selection.rows[0]

            labels = [r["label"] for r in filtered]

            if selected_idx is not None and selected_idx < len(labels):
                selected_label = labels[selected_idx]
            else:
                selected_label = labels[0] if labels else None

            if selected_label:
                selected = next((r for r in filtered if r["label"] == selected_label), None)

                if selected:
                    st.markdown(f"### {selected_label}")

                    # Metric cards row
                    c1, c2, c3, c4, c5, c6 = st.columns(6)
                    pnl_val = selected['total_pnl']
                    c1.metric("Total P&L", f"${pnl_val:,.0f}")
                    c2.metric("Sharpe", f"{selected['sharpe']:.2f}")
                    c3.metric("Win Rate", f"{selected['win_rate']:.1f}%")
                    pf = selected["profit_factor"]
                    c4.metric("Profit Factor", f"{pf:.2f}" if pf < 100 else "inf")
                    c5.metric("Max Drawdown", f"${selected['max_dd']:,.0f}")
                    c6.metric("Trades", f"{selected['trades']}")

                    # Charts
                    folder = RESULTS_DIR / selected_label
                    df = load_positions(folder)
                    if df is not None and len(df) > 0:
                        fig = build_equity_chart(df, title=f"{selected_label}")
                        st.plotly_chart(fig, use_container_width=True, key="detail_equity")

                        hm_col, hist_col = st.columns(2)
                        with hm_col:
                            hm_fig = build_monthly_heatmap(df)
                            if hm_fig:
                                st.plotly_chart(hm_fig, use_container_width=True, key="detail_heatmap")
                        with hist_col:
                            hist_fig = build_trade_histogram(df)
                            st.plotly_chart(hist_fig, use_container_width=True, key="detail_hist")

                    # Delete zone
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
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )

            for line in proc.stdout:
                log_lines.append(line.rstrip())
                display = "\n".join(log_lines[-30:])
                log_area.code(display, language="text")

            proc.wait()
            if proc.returncode == 0:
                status.update(label="Backtest completed!", state="complete")
                load_all_results.clear()
            else:
                status.update(label="Backtest failed!", state="error")


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
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )

            for line in proc.stdout:
                log_lines.append(line.rstrip())
                display = "\n".join(log_lines[-30:])
                log_area.code(display, language="text")

            proc.wait()
            if proc.returncode == 0:
                status.update(label="Walk-forward completed!", state="complete")
                load_all_results.clear()
                grid_path.unlink(missing_ok=True)
            else:
                status.update(label="Walk-forward failed!", state="error")


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
