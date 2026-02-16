"""Load ES OHLCV from zipped CSV into NautilusTrader Bar objects.

Supports resampling from 1-min source to any bar size (default: 5-min).
"""

import zipfile
import pandas as pd

from nautilus_trader.model.data import BarType
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.persistence.wranglers import BarDataWrangler


def resample_to_5min(df: pd.DataFrame) -> pd.DataFrame:
    """Resample 1-min OHLCV DataFrame to 5-min bars.

    Expects UTC-indexed DataFrame with open/high/low/close/volume columns.
    """
    resampled = df.resample("5min").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    return resampled


def load_es_dataframe(zip_path: str) -> pd.DataFrame:
    """
    Load full ES 1-min CSV from zip and return UTC-indexed DataFrame.

    No date filtering or bar wrangling — just raw OHLCV with UTC timestamps.
    Call this ONCE, then use wrangle_bars_from_df() to slice windows.

    CSV format (no header): datetime,open,high,low,close,volume
    Timestamps are US Eastern time, converted to UTC.
    """
    print(f"Reading CSV from {zip_path}...")
    with zipfile.ZipFile(zip_path) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            df = pd.read_csv(
                f,
                header=None,
                names=["timestamp", "open", "high", "low", "close", "volume"],
                parse_dates=["timestamp"],
            )

    # Localize ET timestamps to UTC
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["timestamp"] = df["timestamp"].dt.tz_localize(
        "America/New_York", ambiguous="NaT", nonexistent="shift_forward"
    )
    df["timestamp"] = df["timestamp"].dt.tz_convert("UTC")
    df = df.dropna(subset=["timestamp"])
    df = df.set_index("timestamp")
    df = df.sort_index()

    print(f"Loaded {len(df):,} bars from {df.index[0]} to {df.index[-1]}")
    return df


def wrangle_bars_from_df(
    df: pd.DataFrame,
    instrument: FuturesContract,
    start_date: str = None,
    end_date: str = None,
    bar_minutes: int = 5,
):
    """
    Filter a pre-loaded DataFrame by date range, optionally resample, and
    wrangle into Bar objects.

    Args:
        bar_minutes: Bar size in minutes. If > 1, resamples from 1-min source.

    Returns (list[Bar], BarType).
    """
    filtered = df

    if start_date:
        start_ts = pd.Timestamp(start_date, tz="UTC")
        filtered = filtered[filtered.index >= start_ts]
    if end_date:
        end_ts = pd.Timestamp(end_date, tz="UTC")
        filtered = filtered[filtered.index < end_ts]

    if bar_minutes > 1:
        filtered = filtered.resample(f"{bar_minutes}min").agg({
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }).dropna()

    bar_spec = f"{bar_minutes}-MINUTE-LAST"

    if len(filtered) == 0:
        bar_type = BarType.from_str(f"{instrument.id}-{bar_spec}-EXTERNAL")
        return [], bar_type

    bar_type = BarType.from_str(f"{instrument.id}-{bar_spec}-EXTERNAL")
    wrangler = BarDataWrangler(bar_type=bar_type, instrument=instrument)
    ts_delta = bar_minutes * 60_000_000_000  # ns per bar
    bars = wrangler.process(filtered, ts_init_delta=ts_delta)

    return bars, bar_type


def load_es_bars(
    zip_path: str,
    instrument: FuturesContract,
    start_date: str = None,
    end_date: str = None,
    bar_minutes: int = 5,
):
    """
    Load ES bars from zipped CSV into NautilusTrader Bar objects.

    Convenience wrapper: loads full CSV, filters, optionally resamples, wrangles.
    For walk-forward testing, use load_es_dataframe() + wrangle_bars_from_df() instead.

    Args:
        bar_minutes: Bar size in minutes. Default 5 (resamples from 1-min source).

    Returns (list[Bar], BarType).
    """
    df = load_es_dataframe(zip_path)
    bars, bar_type = wrangle_bars_from_df(df, instrument, start_date, end_date, bar_minutes=bar_minutes)
    print(f"Created {len(bars):,} NautilusTrader {bar_minutes}-min Bar objects")
    return bars, bar_type
