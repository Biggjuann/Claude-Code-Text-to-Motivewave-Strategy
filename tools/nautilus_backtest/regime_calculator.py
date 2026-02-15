"""
Historical Volatility Regime Calculator.

Computes daily regime classification from ES and VIX bar data,
matching the logic in tools/volatility_regime/regime_analyzer.py.
Returns a dict of {date_str: {"stop": mult, "target": mult, "regime": name}}.
"""

import zipfile

import numpy as np
import pandas as pd


# Same config as regime_analyzer.py
ATR_PERIOD = 14
REALIZED_VOL_WINDOW = 20
PERCENTILE_WINDOW = 252

WEIGHTS = {
    "vix_percentile": 0.40,
    "realized_vol_pctl": 0.30,
    "atr_pctl": 0.20,
    "vix_term_spread": 0.10,  # neutral 0.5 (no VIX9D in historical data)
}

REGIME_THRESHOLDS = [
    ("Low", 0.00, 0.25),
    ("Normal", 0.25, 0.50),
    ("Elevated", 0.50, 0.75),
    ("High", 0.75, 1.01),
]

REGIME_MULTIPLIERS = {
    "Low": {"stop": 0.75, "target": 0.75},
    "Normal": {"stop": 1.00, "target": 1.00},
    "Elevated": {"stop": 1.40, "target": 1.50},
    "High": {"stop": 1.80, "target": 2.00},
}


def load_daily_from_1min_zip(zip_path: str, has_volume: bool = True) -> pd.DataFrame:
    """Load 1-min bars from zip, resample to daily OHLCV."""
    with zipfile.ZipFile(zip_path) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            if has_volume:
                names = ["timestamp", "open", "high", "low", "close", "volume"]
            else:
                names = ["timestamp", "open", "high", "low", "close"]
            df = pd.read_csv(f, header=None, names=names, parse_dates=["timestamp"])

    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.set_index("timestamp")
    df = df.sort_index()

    # Resample to daily
    daily = df.resample("1D").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
    }).dropna()

    if has_volume:
        daily["volume"] = df["volume"].resample("1D").sum()

    return daily


def compute_atr(daily: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    """EMA-smoothed ATR."""
    prev_close = daily["close"].shift(1)
    tr = pd.concat([
        daily["high"] - daily["low"],
        (daily["high"] - prev_close).abs(),
        (daily["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def compute_realized_vol(close: pd.Series, window: int = REALIZED_VOL_WINDOW) -> pd.Series:
    """Annualized realized volatility from log returns."""
    log_ret = np.log(close / close.shift(1)).dropna()
    return log_ret.rolling(window).std() * np.sqrt(252)


def rolling_percentile(series: pd.Series, window: int = PERCENTILE_WINDOW) -> pd.Series:
    """Rolling percentile rank (0-1) for each value."""
    def pctl(arr):
        if len(arr) < 20:
            return np.nan
        current = arr[-1]
        return (arr[:-1] < current).sum() / (len(arr) - 1)

    return series.rolling(window, min_periods=60).apply(pctl, raw=True)


def compute_daily_regimes(
    es_zip_path: str,
    vix_zip_path: str,
    start_date: str = None,
    end_date: str = None,
) -> dict:
    """
    Compute daily volatility regime from historical ES and VIX data.

    Returns dict: {
        "YYYY-MM-DD": {"stop": float, "target": float, "regime": str, "composite": float},
        ...
    }
    """
    print("Computing daily volatility regimes...")

    # Load and resample to daily
    print("  Loading ES daily bars from 1-min data...")
    es_daily = load_daily_from_1min_zip(es_zip_path, has_volume=True)
    print(f"  ES: {len(es_daily)} days ({es_daily.index[0].date()} to {es_daily.index[-1].date()})")

    print("  Loading VIX daily bars from 1-min data...")
    vix_daily = load_daily_from_1min_zip(vix_zip_path, has_volume=False)
    print(f"  VIX: {len(vix_daily)} days ({vix_daily.index[0].date()} to {vix_daily.index[-1].date()})")

    # Compute indicators on full history (need warm-up for percentiles)
    vix_close = vix_daily["close"]
    es_close = es_daily["close"]

    # Signal 1: VIX percentile rank
    vix_pctl = rolling_percentile(vix_close, PERCENTILE_WINDOW)

    # Signal 2: Realized vol percentile
    rv = compute_realized_vol(es_close)
    rv_pctl = rolling_percentile(rv, PERCENTILE_WINDOW)

    # Signal 3: ATR as % of price percentile
    atr = compute_atr(es_daily)
    atr_pct = (atr / es_close) * 100
    atr_pctl = rolling_percentile(atr_pct, PERCENTILE_WINDOW)

    # Signal 4: VIX term structure — neutral 0.5 (no VIX9D in historical data)
    vix_term = 0.5

    # Align all signals on common dates
    signals = pd.DataFrame({
        "vix_pctl": vix_pctl,
        "rv_pctl": rv_pctl,
        "atr_pctl": atr_pctl,
    }).dropna()

    # Composite score
    signals["composite"] = (
        WEIGHTS["vix_percentile"] * signals["vix_pctl"]
        + WEIGHTS["realized_vol_pctl"] * signals["rv_pctl"]
        + WEIGHTS["atr_pctl"] * signals["atr_pctl"]
        + WEIGHTS["vix_term_spread"] * vix_term
    ).clip(0.0, 1.0)

    # Classify regime
    def classify(score):
        for name, lo, hi in REGIME_THRESHOLDS:
            if lo <= score < hi:
                return name
        return "Normal"

    signals["regime"] = signals["composite"].apply(classify)
    signals["stop_mult"] = signals["regime"].map(lambda r: REGIME_MULTIPLIERS[r]["stop"])
    signals["target_mult"] = signals["regime"].map(lambda r: REGIME_MULTIPLIERS[r]["target"])

    # Filter to requested date range
    if start_date:
        signals = signals[signals.index >= pd.Timestamp(start_date)]
    if end_date:
        signals = signals[signals.index < pd.Timestamp(end_date)]

    # Build lookup dict keyed by date string
    regime_lookup = {}
    for date, row in signals.iterrows():
        date_str = date.strftime("%Y-%m-%d")
        regime_lookup[date_str] = {
            "stop": row["stop_mult"],
            "target": row["target_mult"],
            "regime": row["regime"],
            "composite": round(row["composite"], 3),
        }

    # Summary
    regime_counts = signals["regime"].value_counts()
    print(f"  Computed {len(regime_lookup)} daily regimes:")
    for regime_name in ["Low", "Normal", "Elevated", "High"]:
        count = regime_counts.get(regime_name, 0)
        pct = count / len(signals) * 100 if len(signals) > 0 else 0
        print(f"    {regime_name:>10}: {count:>4} days ({pct:.1f}%)")

    return regime_lookup


def load_daily_vix(vix_zip_path: str) -> dict:
    """
    Load VIX 1-min data and return daily closes as {"YYYY-MM-DD": float}.
    """
    vix_daily = load_daily_from_1min_zip(vix_zip_path, has_volume=False)
    vix_lookup = {}
    for date, row in vix_daily.iterrows():
        vix_lookup[date.strftime("%Y-%m-%d")] = round(row["close"], 2)
    print(f"  Loaded {len(vix_lookup)} daily VIX closes")
    return vix_lookup
