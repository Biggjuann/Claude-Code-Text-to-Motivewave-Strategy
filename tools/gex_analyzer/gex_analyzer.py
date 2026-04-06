#!/usr/bin/env python3
"""
GEX (Gamma Exposure) Analyzer v2.0

Fetches SPX options data across all expirations, computes gamma exposure per strike,
identifies key levels (put wall, call wall, gamma flip, top-N gamma strikes),
and writes a JSON file for MotiveWave to read.

SPX options are used (not SPY) because institutional hedging flows that drive
GEX dynamics occur primarily in SPX/SPXW options. SPX strikes are already in
ES-equivalent index points — no conversion ratio needed.

Dependencies: pip install -r requirements.txt
Usage:
    python gex_analyzer.py              # Analyze and write gex_levels.json
    python gex_analyzer.py --dry-run    # Show results without writing
    python gex_analyzer.py --top-n 10   # Show top 10 gamma strikes

DISCLAIMER: Educational tool only. Options data from Yahoo Finance may have
gaps or delays. GEX calculations are approximate. Not trading advice.
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import yfinance as yf
from scipy.stats import norm

# =============================================================================
# CONFIG
# =============================================================================

SPX_SYMBOL = "^SPX"   # SPX index — options chain + spot price
ES_SYMBOL  = "ES=F"   # ES futures — current price for reference only

# Filters
STRIKE_RANGE_PCT = 0.15   # Only strikes within +-15% of spot (catches deep put walls)
MIN_OI = 10               # Minimum open interest to include

# Risk-free rate (approximate, update periodically)
RISK_FREE_RATE = 0.043

# Output path (MotiveWave Extensions dir)
OUTPUT_PATH = Path("C:/Users/jung_/MotiveWave Extensions/gex_levels.json")


# =============================================================================
# BLACK-SCHOLES GAMMA
# =============================================================================

def bs_gamma(S, K, T, r, sigma):
    """
    Black-Scholes gamma for a European option.

    Parameters:
        S: spot price
        K: strike price
        T: time to expiration (years)
        r: risk-free rate
        sigma: implied volatility (annualized)

    Returns:
        gamma value (same for calls and puts)
    """
    if T <= 0 or sigma <= 0 or S <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return gamma


# =============================================================================
# DATA FETCHING
# =============================================================================

def fetch_spx_spot():
    """Fetch current SPX index level and return the ticker object for options."""
    print("\n[1/4] Fetching SPX spot price...")
    ticker = yf.Ticker(SPX_SYMBOL)
    hist = ticker.history(period="5d")
    if hist.empty:
        # ^SPX occasionally goes stale on Yahoo Finance; fall back to ^GSPC
        print("    WARNING: ^SPX returned no data, falling back to ^GSPC...")
        gspc = yf.Ticker("^GSPC")
        hist = gspc.history(period="5d")
        if hist.empty:
            raise ValueError("Failed to fetch SPX price data (tried ^SPX and ^GSPC)")
    spot = float(hist["Close"].iloc[-1])
    print(f"    SPX spot: {spot:.2f}")
    return spot, ticker


def fetch_es_price():
    """Fetch current ES futures price for reference in output."""
    try:
        es_df = yf.download(ES_SYMBOL, period="2d", interval="1d",
                            auto_adjust=False, progress=False)
        if isinstance(es_df.columns, pd.MultiIndex):
            es_df.columns = es_df.columns.get_level_values(0)
        if not es_df.empty:
            return float(es_df["Close"].iloc[-1])
    except Exception:
        pass
    return 0.0


def fetch_options_chain(ticker, spot):
    """Fetch SPX options chain across ALL expirations and aggregate."""
    print("[2/4] Fetching SPX options chain (all expirations)...")

    expirations = ticker.options
    if not expirations:
        raise ValueError("No options expirations found for SPX")

    today_str = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()

    # After 4:15 PM ET, today's expirations have already expired at market close.
    # Skip them so the "nearest expiry" is always the next live session.
    now_et = datetime.now(ZoneInfo("America/New_York"))
    skip_today_exp = now_et.hour > 16 or (now_et.hour == 16 and now_et.minute >= 15)

    lo = spot * (1 - STRIKE_RANGE_PCT)
    hi = spot * (1 + STRIKE_RANGE_PCT)

    all_calls = []
    all_puts  = []
    expiry_dates_used = []

    for exp in expirations:
        if exp < today_str:
            continue
        if exp == today_str and skip_today_exp:
            continue

        try:
            chain = ticker.option_chain(exp)
        except Exception as e:
            print(f"    WARNING: Failed to fetch {exp}: {e}")
            continue

        exp_date = datetime.strptime(exp, "%Y-%m-%d")
        dte = max((exp_date - now).total_seconds() / (365.25 * 24 * 3600),
                  1 / (365.25 * 24 * 60))

        c = chain.calls[
            (chain.calls["strike"] >= lo) &
            (chain.calls["strike"] <= hi) &
            (chain.calls["openInterest"] >= MIN_OI)
        ].copy()
        if not c.empty:
            c["dte"]    = dte
            c["expiry"] = exp
            all_calls.append(c)

        p = chain.puts[
            (chain.puts["strike"] >= lo) &
            (chain.puts["strike"] <= hi) &
            (chain.puts["openInterest"] >= MIN_OI)
        ].copy()
        if not p.empty:
            p["dte"]    = dte
            p["expiry"] = exp
            all_puts.append(p)

        expiry_dates_used.append(exp)
        print(f"    {exp} (DTE {dte*365.25:5.1f}d): {len(c):3d} calls, {len(p):3d} puts")

    if not all_calls and not all_puts:
        raise ValueError("No options data after filtering across all expirations")

    calls = pd.concat(all_calls, ignore_index=True) if all_calls else pd.DataFrame()
    puts  = pd.concat(all_puts,  ignore_index=True) if all_puts  else pd.DataFrame()

    print(f"    Total: {len(expiry_dates_used)} expirations, "
          f"{len(calls)} call rows, {len(puts)} put rows")
    print(f"    Strike range: {lo:.0f} - {hi:.0f}")

    return calls, puts, expiry_dates_used


# =============================================================================
# GEX CALCULATION
# =============================================================================

def compute_gex(calls, puts, spot):
    """
    Compute Gamma Exposure (GEX) per strike, aggregated across all expirations.

    Formula (SqueezeMetrics white paper):
        Calls: GEX = Gamma x OI x 100 x Spot  (dealers long gamma -> positive)
        Puts:  GEX = Gamma x OI x 100 x Spot  (dealers short gamma -> negative)

    SPX contract multiplier is $100/point; multiplying by spot normalises to
    dollar GEX comparable to published figures.
    """
    print("[3/4] Computing GEX per strike (all expirations)...")

    # Compute median IV from all valid chain entries to use as fallback
    all_ivs = []
    for df in [calls, puts]:
        if not df.empty and "impliedVolatility" in df.columns:
            valid = df["impliedVolatility"].replace(0, np.nan).dropna()
            all_ivs.extend(valid.tolist())
    fallback_iv = float(np.median(all_ivs)) if all_ivs else 0.20
    print(f"    IV fallback (median chain IV): {fallback_iv:.3f}")

    call_records = []
    if not calls.empty:
        for _, row in calls.iterrows():
            K  = row["strike"]
            oi = row["openInterest"]
            dte = row["dte"]
            iv = row.get("impliedVolatility", fallback_iv)
            if iv <= 0 or np.isnan(iv):
                iv = fallback_iv
            gamma = bs_gamma(spot, K, dte, RISK_FREE_RATE, iv)
            gex   = gamma * oi * 100 * spot * (+1)
            call_records.append({"strike": K, "call_oi": int(oi), "call_gex": gex})

    put_records = []
    if not puts.empty:
        for _, row in puts.iterrows():
            K  = row["strike"]
            oi = row["openInterest"]
            dte = row["dte"]
            iv = row.get("impliedVolatility", fallback_iv)
            if iv <= 0 or np.isnan(iv):
                iv = fallback_iv
            gamma = bs_gamma(spot, K, dte, RISK_FREE_RATE, iv)
            gex   = gamma * oi * 100 * spot * (-1)
            put_records.append({"strike": K, "put_oi": int(oi), "put_gex": gex})

    call_df = pd.DataFrame(call_records).groupby("strike").agg(
        call_oi=("call_oi", "sum"), call_gex=("call_gex", "sum")
    ) if call_records else pd.DataFrame()

    put_df = pd.DataFrame(put_records).groupby("strike").agg(
        put_oi=("put_oi", "sum"), put_gex=("put_gex", "sum")
    ) if put_records else pd.DataFrame()

    if call_df.empty and put_df.empty:
        raise ValueError("No options data after filtering")

    gex_df = call_df.join(put_df, how="outer").fillna(0)
    gex_df["net_gex"] = gex_df.get("call_gex", 0) + gex_df.get("put_gex", 0)
    gex_df["abs_gex"] = gex_df["net_gex"].abs()

    print(f"    Unique strikes: {len(gex_df)}")
    return gex_df


# =============================================================================
# LEVEL IDENTIFICATION
# =============================================================================

def identify_levels(gex_df, spot, es_price, top_n=5):
    """
    Identify put wall, call wall, gamma flip, and top-N gamma strikes.

    SPX strikes are already in ES-equivalent index points, so no conversion
    ratio is needed. The strike value IS the chart level.
    """

    # Put wall: largest put GEX magnitude at strikes BELOW spot.
    # Dealers are short gamma here — as price drops toward this strike they buy
    # futures to re-hedge, creating a support floor.
    # Constrained to below-spot strikes so LEAPS OI above spot doesn't pollute.
    put_wall_strike = None
    put_wall_oi     = 0
    if "put_gex" in gex_df.columns:
        put_cols = gex_df[(gex_df["put_gex"] < 0) & (gex_df.index < spot)]
        if not put_cols.empty:
            put_wall_idx    = put_cols["put_gex"].idxmin()  # most negative = strongest
            put_wall_strike = float(put_wall_idx)
            put_wall_oi     = int(gex_df.loc[put_wall_idx, "put_oi"]) if "put_oi" in gex_df.columns else 0

    # Call wall: largest call GEX magnitude at strikes ABOVE spot.
    # Dealers are long gamma here — as price rises toward this strike they sell
    # futures to re-hedge, creating a resistance ceiling.
    # Constrained to above-spot strikes so LEAPS OI below spot doesn't pollute.
    call_wall_strike = None
    call_wall_oi     = 0
    if "call_gex" in gex_df.columns:
        call_cols = gex_df[(gex_df["call_gex"] > 0) & (gex_df.index > spot)]
        if not call_cols.empty:
            call_wall_idx    = call_cols["call_gex"].idxmax()  # most positive = strongest
            call_wall_strike = float(call_wall_idx)
            call_wall_oi     = int(gex_df.loc[call_wall_idx, "call_oi"]) if "call_oi" in gex_df.columns else 0

    # Gamma flip: strike where net GEX crosses zero (nearest to spot)
    gamma_flip_strike = None
    sorted_df = gex_df.sort_index()
    net_gex   = sorted_df["net_gex"]
    for i in range(1, len(net_gex)):
        prev_val = net_gex.iloc[i - 1]
        curr_val = net_gex.iloc[i]
        if prev_val * curr_val < 0:
            prev_strike = float(net_gex.index[i - 1])
            curr_strike = float(net_gex.index[i])
            frac        = abs(prev_val) / (abs(prev_val) + abs(curr_val))
            cross       = prev_strike + frac * (curr_strike - prev_strike)
            if gamma_flip_strike is None or abs(cross - spot) < abs(gamma_flip_strike - spot):
                gamma_flip_strike = cross

    # Top-N by absolute GEX — SPX strike IS the ES level
    top_strikes = gex_df.nlargest(top_n, "abs_gex")

    top_gamma_levels = []
    for strike, row in top_strikes.iterrows():
        net = float(row["net_gex"])
        top_gamma_levels.append({
            "spx_strike": float(strike),
            "es_level":   round(float(strike), 2),   # SPX strike == ES level
            "spy_strike": round(float(strike) / 10, 2),  # kept for JSON compat
            "net_gex":    round(net, 1),
            "type":       "CALL_HEAVY" if net > 0 else "PUT_HEAVY",
        })

    net_gex_total = float(gex_df["net_gex"].sum())

    def make_level(strike, oi_val, oi_key):
        if strike is None:
            return None
        return {
            "spx_strike": round(strike, 2),
            "es_level":   round(strike, 2),       # SPX strike == ES level
            "spy_strike": round(strike / 10, 2),  # kept for JSON compat
            oi_key:       oi_val,
        }

    return {
        "put_wall":         make_level(put_wall_strike,  put_wall_oi,  "put_oi"),
        "call_wall":        make_level(call_wall_strike, call_wall_oi, "call_oi"),
        "gamma_flip":       {"spx_strike": round(gamma_flip_strike, 2),
                             "es_level":   round(gamma_flip_strike, 2),
                             "spy_strike": round(gamma_flip_strike / 10, 2),
                             } if gamma_flip_strike else None,
        "top_gamma_levels": top_gamma_levels,
        "net_gex_total":    round(net_gex_total, 1),
        "gex_direction":    "POSITIVE" if net_gex_total > 0 else "NEGATIVE",
    }


# =============================================================================
# NEAR-TERM EXPIRY LEVELS
# =============================================================================

def compute_near_term_levels(calls, puts, spot, es_price, top_n=5):
    """
    Compute GEX levels for just the nearest expiry (typically today's or
    next session's weekly options). These gamma forces dominate near-term
    price action and often create a pin zone very different from the aggregate.
    """
    all_expiries = set()
    if not calls.empty and "expiry" in calls.columns:
        all_expiries.update(calls["expiry"].unique())
    if not puts.empty and "expiry" in puts.columns:
        all_expiries.update(puts["expiry"].unique())

    if not all_expiries:
        return None

    nearest_expiry = sorted(all_expiries)[0]

    near_calls = calls[calls["expiry"] == nearest_expiry].copy() if not calls.empty else pd.DataFrame()
    near_puts  = puts[puts["expiry"] == nearest_expiry].copy()  if not puts.empty else pd.DataFrame()

    if near_calls.empty and near_puts.empty:
        return None

    gex_df = compute_gex(near_calls, near_puts, spot)
    levels = identify_levels(gex_df, spot, es_price, top_n=top_n)

    dte = (datetime.strptime(nearest_expiry, "%Y-%m-%d") - datetime.now()).total_seconds() / (24 * 3600)
    levels["expiry"]   = nearest_expiry
    levels["dte_days"] = round(dte, 1)

    return levels


# =============================================================================
# OUTPUT
# =============================================================================

def build_output(spx_spot, es_price, levels, expiry_dates, num_strikes, near_term=None):
    """
    Build the JSON output dict.

    Top-level put_wall / call_wall / gamma_flip use the near-term expiry
    when available — these are the pinning levels for the current session
    and are what the MotiveWave study draws on the chart.

    Aggregate levels (all expirations) live under the "aggregate" key and
    are used by the morning briefing for the structural regime picture.
    """
    now = datetime.now().astimezone()

    # Near-term levels are primary (what the study draws); fall back to aggregate.
    nt = near_term or {}
    primary_put_wall   = nt.get("put_wall")   or levels["put_wall"]
    primary_call_wall  = nt.get("call_wall")  or levels["call_wall"]
    primary_gamma_flip = nt.get("gamma_flip") or levels["gamma_flip"]

    output = {
        "date":             now.strftime("%Y-%m-%d"),
        "timestamp":        now.isoformat(),
        "spx_spot":         round(spx_spot, 2),
        "es_price":         round(es_price, 2),
        # Primary levels = near-term expiry (what MotiveWave study reads)
        "put_wall":         primary_put_wall,
        "call_wall":        primary_call_wall,
        "gamma_flip":       primary_gamma_flip,
        # Top strikes + regime from aggregate (structural picture)
        "top_gamma_levels": levels["top_gamma_levels"],
        "net_gex_total":    levels["net_gex_total"],
        "gex_direction":    levels["gex_direction"],
        # Near-term expiry section (briefing + context)
        "near_term": {
            "expiry":        nt.get("expiry", expiry_dates[0] if expiry_dates else "N/A"),
            "dte_days":      nt.get("dte_days", 0),
            "put_wall":      nt.get("put_wall"),
            "call_wall":     nt.get("call_wall"),
            "gamma_flip":    nt.get("gamma_flip"),
            "net_gex_total": nt.get("net_gex_total", 0),
            "gex_direction": nt.get("gex_direction", "N/A"),
        } if near_term else None,
        # Aggregate section (briefing structural context)
        "aggregate": {
            "put_wall":      levels["put_wall"],
            "call_wall":     levels["call_wall"],
            "gamma_flip":    levels["gamma_flip"],
            "net_gex_total": levels["net_gex_total"],
            "gex_direction": levels["gex_direction"],
        },
        "metadata": {
            "num_expirations": len(expiry_dates),
            "nearest_expiry":  expiry_dates[0] if expiry_dates else "N/A",
            "farthest_expiry": expiry_dates[-1] if expiry_dates else "N/A",
            "num_strikes":     num_strikes,
            "risk_free_rate":  RISK_FREE_RATE,
            "data_source":     "yfinance (SPX options)",
        },
    }
    return output


def print_summary(output_data):
    """Print a human-readable console summary."""
    print("\n" + "=" * 60)
    print("  GEX GAMMA EXPOSURE LEVELS  (SPX/ES)")
    print("=" * 60)

    print(f"\n  Date:            {output_data['date']}")
    print(f"  SPX Spot:        {output_data['spx_spot']:.2f}")
    print(f"  ES Price:        {output_data['es_price']:.2f}")

    # Near-term expiry (primary — what the study draws)
    nt = output_data.get("near_term")
    if nt:
        print(f"\n  --- Near-Term Expiry: {nt['expiry']}  (DTE {nt['dte_days']:.1f}d) ---")
        print(f"  Net GEX:         {nt['net_gex_total']:,.0f}  ({nt['gex_direction']})")
        pw = nt.get("put_wall")
        cw = nt.get("call_wall")
        gf = nt.get("gamma_flip")
        print(f"  Put Wall:        ES {pw['es_level']:.2f}  (OI: {pw.get('put_oi',0):,})" if pw else "  Put Wall:        N/A")
        print(f"  Call Wall:       ES {cw['es_level']:.2f}  (OI: {cw.get('call_oi',0):,})" if cw else "  Call Wall:       N/A")
        print(f"  Gamma Flip:      ES {gf['es_level']:.2f}" if gf else "  Gamma Flip:      N/A")

    # Aggregate (structural regime)
    agg = output_data.get("aggregate", output_data)
    print(f"\n  --- Aggregate (All Expirations) ---")
    print(f"  Net GEX:         {agg['net_gex_total']:,.0f}  ({agg['gex_direction']})")
    pw = agg.get("put_wall")
    cw = agg.get("call_wall")
    gf = agg.get("gamma_flip")
    print(f"  Put Wall:        ES {pw['es_level']:.2f}  (OI: {pw.get('put_oi',0):,})" if pw else "  Put Wall:        N/A")
    print(f"  Call Wall:       ES {cw['es_level']:.2f}  (OI: {cw.get('call_oi',0):,})" if cw else "  Call Wall:       N/A")
    print(f"  Gamma Flip:      ES {gf['es_level']:.2f}" if gf else "  Gamma Flip:      N/A")

    top = output_data.get("top_gamma_levels", [])
    if top:
        print(f"\n  --- Top {len(top)} Gamma Strikes (Aggregate) ---")
        for i, lvl in enumerate(top, 1):
            print(f"  {i}. ES {lvl['es_level']:.2f}  GEX={lvl['net_gex']:+,.0f}  [{lvl['type']}]")

    meta = output_data.get("metadata", {})
    print(f"\n  Expirations:     {meta.get('num_expirations', 0)} "
          f"({meta.get('nearest_expiry', '?')} -> {meta.get('farthest_expiry', '?')})")
    print(f"  Unique Strikes:  {meta.get('num_strikes', 0)}")
    print(f"  Risk-Free Rate:  {meta.get('risk_free_rate', 0):.1%}")
    print(f"  Source:          {meta.get('data_source', '?')}")
    print("\n" + "=" * 60)


def write_output(output_data, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)
    print(f"\n  Wrote GEX levels: {path}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="GEX (Gamma Exposure) Analyzer")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show levels without writing file")
    parser.add_argument("--top-n", type=int, default=5,
                        help="Number of top gamma strikes (default: 5)")
    parser.add_argument("--output", type=str, default=None,
                        help=f"Override output path (default: {OUTPUT_PATH})")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else OUTPUT_PATH

    try:
        spx_spot, ticker              = fetch_spx_spot()
        es_price                      = fetch_es_price()
        calls, puts, expiry_dates     = fetch_options_chain(ticker, spx_spot)
        gex_df                        = compute_gex(calls, puts, spx_spot)
        levels                        = identify_levels(gex_df, spx_spot, es_price, top_n=args.top_n)
        near_term                     = compute_near_term_levels(calls, puts, spx_spot, es_price, top_n=args.top_n)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    output_data = build_output(spx_spot, es_price, levels, expiry_dates, len(gex_df), near_term=near_term)

    print_summary(output_data)

    if args.dry_run:
        print("\n  [DRY RUN] Would write:")
        print(json.dumps(output_data, indent=2))
    else:
        write_output(output_data, output_path)

    print()


if __name__ == "__main__":
    main()
