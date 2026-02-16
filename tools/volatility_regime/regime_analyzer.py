#!/usr/bin/env python3
"""
Volatility Regime Analyzer v1.0

Fetches market data (VIX, ATR, realized vol) and classifies the current
volatility regime into 4 buckets. Writes stop/target multipliers to a
JSON file that MotiveWave strategies read at runtime.

Dependencies: pip install -r requirements.txt
Usage:
    python regime_analyzer.py              # Analyze and write regime file
    python regime_analyzer.py --dry-run    # Show results without writing

DISCLAIMER: Educational heuristic for risk sizing. Not a regime model.
Data source: Yahoo Finance (not institutional grade, may have gaps).
This is NOT trading advice.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

# =============================================================================
# CONFIG - Tune these values to adjust regime sensitivity
# =============================================================================

# Assets to analyze (futures for ATR, VIX for implied vol)
ASSET_SYMBOL = "ES=F"           # Primary asset for ATR / realized vol
VIX_SYMBOL = "^VIX"
VIX9D_SYMBOL = "^VIX9D"        # Short-term VIX for term structure

DATA_HORIZON = "2y"             # History to fetch for percentile ranking
ATR_PERIOD = 14                 # ATR lookback (EMA-smoothed)
REALIZED_VOL_WINDOW = 20       # Trading days for realized vol
VIX_PERCENTILE_WINDOW = 252    # 1 year of trading days for percentile rank
DATA_FRESHNESS_DAYS = 3        # Warn if data is older than this

# Composite score weights (sum to 1.0 for clarity, but not required)
WEIGHTS = {
    "vix_percentile": 0.40,     # VIX percentile rank (252-day)
    "realized_vol_pctl": 0.30,  # Realized vol percentile
    "atr_pctl": 0.20,           # ATR-as-%-of-price percentile
    "vix_term_spread": 0.10,    # VIX vs VIX9D term structure signal
}

# Regime thresholds (composite score percentile boundaries)
# Score 0.0 = lowest vol environment, 1.0 = highest
REGIME_THRESHOLDS = {
    "Low":      (0.00, 0.25),
    "Normal":   (0.25, 0.50),
    "Elevated": (0.50, 0.75),
    "High":     (0.75, 1.01),
}

# Multipliers per regime: applied to MotiveWave strategy stop/target distances
REGIME_MULTIPLIERS = {
    "Low":      {"stop": 0.75, "target": 0.75},
    "Normal":   {"stop": 1.00, "target": 1.00},
    "Elevated": {"stop": 1.40, "target": 1.50},
    "High":     {"stop": 1.80, "target": 2.00},
}

# Output path (MotiveWave Extensions dir - same location as strategy JAR)
OUTPUT_PATH = Path("C:/Users/jung_/MotiveWave Extensions/volatility_regime.json")


# =============================================================================
# DATA FETCHING
# =============================================================================

def fetch_data():
    """Fetch asset + VIX data from Yahoo Finance."""
    warnings = []

    print(f"\n[1/3] Downloading {ASSET_SYMBOL} data ({DATA_HORIZON})...")
    asset_df = yf.download(ASSET_SYMBOL, period=DATA_HORIZON, interval="1d",
                           auto_adjust=False, progress=False)
    if asset_df.empty:
        raise ValueError(f"Failed to fetch {ASSET_SYMBOL} data.")

    # Flatten multi-level columns if present
    if isinstance(asset_df.columns, pd.MultiIndex):
        asset_df.columns = asset_df.columns.get_level_values(0)

    print(f"    Got {len(asset_df)} days of {ASSET_SYMBOL} data")

    print(f"[2/3] Downloading {VIX_SYMBOL} data ({DATA_HORIZON})...")
    vix_df = yf.download(VIX_SYMBOL, period=DATA_HORIZON, interval="1d",
                         auto_adjust=False, progress=False)
    if vix_df.empty:
        raise ValueError("Failed to fetch VIX data.")

    if isinstance(vix_df.columns, pd.MultiIndex):
        vix_df.columns = vix_df.columns.get_level_values(0)

    vix_close = vix_df["Close"].squeeze().ffill(limit=3).dropna()
    print(f"    Got {len(vix_close)} days of VIX data")

    print(f"[3/3] Downloading {VIX9D_SYMBOL} data...")
    vix9d_close = None
    try:
        vix9d_df = yf.download(VIX9D_SYMBOL, period=DATA_HORIZON, interval="1d",
                               auto_adjust=False, progress=False)
        if not vix9d_df.empty:
            if isinstance(vix9d_df.columns, pd.MultiIndex):
                vix9d_df.columns = vix9d_df.columns.get_level_values(0)
            vix9d_close = vix9d_df["Close"].squeeze().ffill(limit=3).dropna()
            print(f"    Got {len(vix9d_close)} days of VIX9D data")
        else:
            warnings.append("VIX9D data empty - term structure signal disabled")
    except Exception as e:
        warnings.append(f"VIX9D fetch failed ({e}) - term structure signal disabled")

    # Check data freshness
    last_date = asset_df.index[-1]
    if hasattr(last_date, 'date'):
        last_date_dt = last_date.date()
    else:
        last_date_dt = last_date
    days_stale = (datetime.now().date() - pd.Timestamp(last_date_dt).date()).days
    if days_stale > DATA_FRESHNESS_DAYS:
        warnings.append(f"Data is {days_stale} days old (last: {last_date_dt}). "
                        "Market may be closed or data feed delayed.")

    return asset_df, vix_close, vix9d_close, warnings


# =============================================================================
# REGIME ANALYSIS
# =============================================================================

def compute_atr(df, period=ATR_PERIOD):
    """Compute ATR using EMA smoothing."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    # Squeeze multi-level if needed
    if isinstance(high, pd.DataFrame):
        high = high.squeeze()
    if isinstance(low, pd.DataFrame):
        low = low.squeeze()
    if isinstance(close, pd.DataFrame):
        close = close.squeeze()

    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)

    atr = tr.ewm(span=period, adjust=False).mean()
    return atr


def compute_realized_vol(close, window=REALIZED_VOL_WINDOW):
    """Compute annualized realized volatility from log returns."""
    if isinstance(close, pd.DataFrame):
        close = close.squeeze()
    log_returns = np.log(close / close.shift(1)).dropna()
    realized_vol = log_returns.rolling(window).std() * np.sqrt(252)
    return realized_vol


def percentile_rank(series, window):
    """Compute rolling percentile rank (0-1) of the latest value."""
    if len(series.dropna()) < window:
        # Not enough data, use what we have
        window = max(len(series.dropna()) // 2, 20)

    recent = series.dropna().iloc[-window:]
    current = recent.iloc[-1]
    rank = (recent < current).sum() / len(recent)
    return rank


def analyze_regime(asset_df, vix_close, vix9d_close=None):
    """Compute composite volatility score and classify regime."""
    close = asset_df["Close"]
    if isinstance(close, pd.DataFrame):
        close = close.squeeze()

    # --- Signal 1: VIX percentile rank ---
    vix_pctl = percentile_rank(vix_close, VIX_PERCENTILE_WINDOW)
    current_vix = float(vix_close.dropna().iloc[-1])

    # --- Signal 2: Realized volatility percentile ---
    rv = compute_realized_vol(close)
    rv_pctl = percentile_rank(rv, VIX_PERCENTILE_WINDOW)
    current_rv = float(rv.dropna().iloc[-1]) * 100  # as percentage

    # --- Signal 3: ATR as % of price percentile ---
    atr = compute_atr(asset_df)
    atr_pct = (atr / close) * 100
    atr_pctl = percentile_rank(atr_pct, VIX_PERCENTILE_WINDOW)
    current_atr_pct = float(atr_pct.dropna().iloc[-1])

    # --- Signal 4: VIX term structure ---
    vix_term_signal = 0.5  # neutral default
    if vix9d_close is not None and len(vix9d_close) > 0:
        # Align dates
        common_idx = vix_close.index.intersection(vix9d_close.index)
        if len(common_idx) > 20:
            vix_aligned = vix_close.loc[common_idx]
            vix9d_aligned = vix9d_close.loc[common_idx]
            # When VIX9D > VIX, short-term fear is elevated (backwardation = stress)
            spread = (vix9d_aligned - vix_aligned) / vix_aligned
            spread_pctl = percentile_rank(spread, min(len(spread), VIX_PERCENTILE_WINDOW))
            vix_term_signal = spread_pctl

    # --- Composite score ---
    composite = (
        WEIGHTS["vix_percentile"] * vix_pctl +
        WEIGHTS["realized_vol_pctl"] * rv_pctl +
        WEIGHTS["atr_pctl"] * atr_pctl +
        WEIGHTS["vix_term_spread"] * vix_term_signal
    )
    composite = max(0.0, min(1.0, composite))  # clamp

    # --- Classify regime ---
    regime = "Normal"
    regime_bucket = 1
    for i, (name, (lo, hi)) in enumerate(REGIME_THRESHOLDS.items()):
        if lo <= composite < hi:
            regime = name
            regime_bucket = i
            break

    # --- Get multipliers ---
    mults = REGIME_MULTIPLIERS[regime]

    # Current asset price
    current_price = float(close.dropna().iloc[-1])

    details = {
        "vix_close": round(current_vix, 2),
        "vix_percentile": round(vix_pctl, 3),
        "realized_vol_20d": round(current_rv, 2),
        "realized_vol_pctl": round(rv_pctl, 3),
        "atr_14_pct": round(current_atr_pct, 3),
        "atr_pctl": round(atr_pctl, 3),
        "vix_term_signal": round(vix_term_signal, 3),
        "es_close": round(current_price, 2),
    }

    signals = {
        "vix_pctl": vix_pctl,
        "rv_pctl": rv_pctl,
        "atr_pctl": atr_pctl,
        "vix_term": vix_term_signal,
    }

    return regime, regime_bucket, composite, mults, details, signals


# =============================================================================
# OUTPUT
# =============================================================================

# VIX hysteresis filter thresholds
VIX_BLOCK_ABOVE = 30.0   # stop trading when VIX closes above this
VIX_RESUME_BELOW = 20.0  # resume trading when VIX closes below this


def compute_vix_filter(vix_close, previous_blocked=False):
    """
    Compute VIX hysteresis filter state.
    Once VIX > VIX_BLOCK_ABOVE, blocked=True until VIX < VIX_RESUME_BELOW.
    """
    if previous_blocked:
        # Currently blocked — only resume when VIX drops below threshold
        blocked = vix_close >= VIX_RESUME_BELOW
    else:
        # Currently active — block when VIX rises above threshold
        blocked = vix_close > VIX_BLOCK_ABOVE
    return blocked


def load_previous_vix_state(path):
    """Read previous vix_blocked state from existing regime file."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("vix_blocked", False)
    except Exception:
        return False


def build_output(regime, regime_bucket, composite, mults, details, vix_blocked):
    """Build the JSON output dict."""
    from datetime import timezone
    now = datetime.now().astimezone()

    return {
        "timestamp": now.isoformat(),
        "regime": regime,
        "regime_bucket": regime_bucket,
        "composite_score": round(composite, 4),
        "stop_multiplier": mults["stop"],
        "target_multiplier": mults["target"],
        "vix_blocked": vix_blocked,
        "details": details,
    }


def print_summary(regime, composite, mults, details, signals, warnings, vix_blocked=False):
    """Print a human-readable console summary."""
    print("\n" + "=" * 60)
    print("  VOLATILITY REGIME ANALYSIS")
    print("=" * 60)

    # Regime with color hint
    regime_icons = {"Low": "[ ]", "Normal": "[=]", "Elevated": "[!]", "High": "[!!!]"}
    icon = regime_icons.get(regime, "[?]")
    print(f"\n  Regime:      {icon} {regime}")
    print(f"  Composite:   {composite:.3f}")
    print(f"  Stop Mult:   {mults['stop']:.2f}x")
    print(f"  Target Mult: {mults['target']:.2f}x")
    print(f"  VIX Filter:  {'BLOCKED (no trading)' if vix_blocked else 'ACTIVE (trading allowed)'}")

    print(f"\n  --- Signals ---")
    print(f"  VIX:             {details['vix_close']:.1f}  (pctl: {signals['vix_pctl']:.1%})")
    print(f"  Realized Vol:    {details['realized_vol_20d']:.1f}%  (pctl: {signals['rv_pctl']:.1%})")
    print(f"  ATR/Price:       {details['atr_14_pct']:.3f}%  (pctl: {signals['atr_pctl']:.1%})")
    print(f"  VIX Term Str:    (signal: {signals['vix_term']:.1%})")
    print(f"  ES Close:        {details['es_close']:.2f}")

    if warnings:
        print(f"\n  --- Warnings ---")
        for w in warnings:
            print(f"  * {w}")

    print("\n" + "=" * 60)


def write_output(output_data, path):
    """Write regime JSON to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    print(f"\n  Wrote regime file: {path}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Volatility Regime Analyzer")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show regime without writing file")
    parser.add_argument("--output", type=str, default=None,
                        help=f"Override output path (default: {OUTPUT_PATH})")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else OUTPUT_PATH

    try:
        asset_df, vix_close, vix9d_close, warnings = fetch_data()
    except Exception as e:
        print(f"\nERROR: Failed to fetch data: {e}")
        sys.exit(1)

    regime, bucket, composite, mults, details, signals = analyze_regime(
        asset_df, vix_close, vix9d_close
    )

    # VIX hysteresis filter
    previous_blocked = load_previous_vix_state(output_path)
    current_vix = details["vix_close"]
    vix_blocked = compute_vix_filter(current_vix, previous_blocked)

    print_summary(regime, composite, mults, details, signals, warnings, vix_blocked)

    output_data = build_output(regime, bucket, composite, mults, details, vix_blocked)

    if args.dry_run:
        print("\n  [DRY RUN] Would write:")
        print(json.dumps(output_data, indent=2))
    else:
        write_output(output_data, output_path)

    print()


if __name__ == "__main__":
    main()
