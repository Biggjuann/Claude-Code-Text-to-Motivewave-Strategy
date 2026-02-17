"""Tick-to-bar aggregation for time-based OHLCV bars."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Coroutine
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")

log = logging.getLogger(__name__)


@dataclass
class Bar:
    """Completed OHLCV bar."""
    timestamp: datetime       # bar open time in ET
    open: float
    high: float
    low: float
    close: float
    volume: int
    tick_count: int

    def __repr__(self) -> str:
        return (
            f"Bar({self.timestamp.strftime('%H:%M')} "
            f"O={self.open:.2f} H={self.high:.2f} "
            f"L={self.low:.2f} C={self.close:.2f} V={self.volume})"
        )


class BarAggregator:
    """Aggregates ticks into time-based OHLCV bars.

    Args:
        bar_size_minutes: Bar period in minutes (e.g. 5 for 5-min bars).
        on_bar: Async callback invoked with completed Bar.
    """

    def __init__(
        self,
        bar_size_minutes: int,
        on_bar: Callable[[Bar], Coroutine[Any, Any, None]],
    ):
        self.bar_size = bar_size_minutes
        self.on_bar = on_bar

        # Current building bar
        self._bar_open_time: datetime | None = None
        self._bar_close_time: datetime | None = None
        self._open: float = 0.0
        self._high: float = 0.0
        self._low: float = 0.0
        self._close: float = 0.0
        self._volume: int = 0
        self._tick_count: int = 0

    def _bar_boundary(self, dt: datetime) -> datetime:
        """Compute the bar-open time for the bar containing dt."""
        minutes_since_midnight = dt.hour * 60 + dt.minute
        bar_start_min = (minutes_since_midnight // self.bar_size) * self.bar_size
        return dt.replace(
            hour=bar_start_min // 60,
            minute=bar_start_min % 60,
            second=0,
            microsecond=0,
        )

    async def on_tick(self, price: float, size: int, timestamp: datetime) -> None:
        """Process an incoming tick.

        Args:
            price: Trade price.
            size: Trade size (contracts).
            timestamp: Tick timestamp, converted to ET internally if needed.
        """
        # Ensure ET
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=ET)
        else:
            timestamp = timestamp.astimezone(ET)

        bar_open = self._bar_boundary(timestamp)
        bar_close = bar_open + timedelta(minutes=self.bar_size)

        # New bar period?
        if self._bar_open_time is None or bar_open != self._bar_open_time:
            # Emit previous bar if we have one
            if self._bar_open_time is not None and self._tick_count > 0:
                completed = Bar(
                    timestamp=self._bar_open_time,
                    open=self._open,
                    high=self._high,
                    low=self._low,
                    close=self._close,
                    volume=self._volume,
                    tick_count=self._tick_count,
                )
                log.debug("Bar complete: %s", completed)
                await self.on_bar(completed)

            # Start new bar
            self._bar_open_time = bar_open
            self._bar_close_time = bar_close
            self._open = price
            self._high = price
            self._low = price
            self._close = price
            self._volume = size
            self._tick_count = 1
        else:
            # Update current bar
            self._high = max(self._high, price)
            self._low = min(self._low, price)
            self._close = price
            self._volume += size
            self._tick_count += 1

    async def flush(self) -> None:
        """Force-emit the current building bar (e.g. at shutdown)."""
        if self._bar_open_time is not None and self._tick_count > 0:
            completed = Bar(
                timestamp=self._bar_open_time,
                open=self._open,
                high=self._high,
                low=self._low,
                close=self._close,
                volume=self._volume,
                tick_count=self._tick_count,
            )
            log.info("Flushing partial bar: %s", completed)
            await self.on_bar(completed)
            self._tick_count = 0

    def reset(self) -> None:
        """Clear all bar state."""
        self._bar_open_time = None
        self._bar_close_time = None
        self._open = 0.0
        self._high = 0.0
        self._low = 0.0
        self._close = 0.0
        self._volume = 0
        self._tick_count = 0
