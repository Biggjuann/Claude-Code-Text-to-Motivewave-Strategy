"""Economic event calendar for margin analysis.

Loads hardcoded FOMC/CPI/PPI/GDP/PCE/Retail dates from JSON,
auto-generates NFP (first Friday of each month), and computes
elevated margin windows around each event.
"""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pytz

ET = pytz.timezone("America/New_York")
UTC = pytz.utc

_DEFAULT_JSON = Path(__file__).parent / "economic_events.json"


def _first_friday(year: int, month: int) -> date:
    """Return the first Friday of the given month."""
    d = date(year, month, 1)
    # Monday=0 ... Friday=4
    days_ahead = 4 - d.weekday()
    if days_ahead < 0:
        days_ahead += 7
    return d + timedelta(days=days_ahead)


def _generate_nfp_events(start_year: int = 2020, end_year: int = 2026) -> list[dict]:
    """Generate NFP (Non-Farm Payrolls) events: first Friday of each month at 08:30 ET."""
    events = []
    for year in range(start_year, end_year + 1):
        for month in range(1, 13):
            d = _first_friday(year, month)
            events.append({
                "date": d.isoformat(),
                "time_et": "08:30",
                "type": "NFP",
                "description": "Non-Farm Payrolls",
            })
    return events


def load_economic_events(json_path: str = None) -> list[dict]:
    """Load economic events from JSON and append auto-generated NFP dates.

    Returns list of dicts with keys: date, time_et, type, description.
    """
    path = Path(json_path) if json_path else _DEFAULT_JSON
    with open(path) as f:
        data = json.load(f)

    events = data.get("events", [])

    # Add NFP events (auto-computed first Fridays)
    nfp_events = _generate_nfp_events()
    events.extend(nfp_events)

    # Sort by date
    events.sort(key=lambda e: e["date"])
    return events


def get_elevated_margin_windows(
    events: list[dict],
    start_date: str,
    end_date: str,
) -> list[tuple]:
    """Compute elevated margin windows for events in the date range.

    Elevated window: starts 5 PM ET the day before the event,
    ends 4 hours after the release time.

    Returns list of (start_utc, end_utc, event_type, event_description).
    """
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)
    windows = []

    for event in events:
        event_date = date.fromisoformat(event["date"])
        if event_date < start or event_date >= end:
            continue

        # Parse release time
        h, m = map(int, event["time_et"].split(":"))

        # Window start: 5 PM ET the day before
        day_before = event_date - timedelta(days=1)
        window_start_et = ET.localize(datetime(day_before.year, day_before.month, day_before.day, 17, 0))

        # Window end: 4 hours after release
        release_et = ET.localize(datetime(event_date.year, event_date.month, event_date.day, h, m))
        window_end_et = release_et + timedelta(hours=4)

        # Convert to UTC
        window_start_utc = window_start_et.astimezone(UTC)
        window_end_utc = window_end_et.astimezone(UTC)

        windows.append((
            window_start_utc,
            window_end_utc,
            event["type"],
            event.get("description", event["type"]),
        ))

    return windows


def is_elevated_margin(timestamp_utc, windows: list[tuple]) -> tuple:
    """Check if a UTC timestamp falls within any elevated margin window.

    Returns (is_elevated: bool, event_type: str|None, description: str|None).
    """
    for start_utc, end_utc, event_type, description in windows:
        if start_utc <= timestamp_utc <= end_utc:
            return True, event_type, description
    return False, None, None
