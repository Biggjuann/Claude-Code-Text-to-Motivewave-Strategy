"""Abstract base class for all live trading strategy engines."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from shared_types import Signal, TradeState


class BaseLiveEngine(ABC):
    """Base class that all live strategy engines must implement.

    Each engine maintains its own bar history, indicator state, and trade
    state.  The adapter calls on_bar() after each completed bar and
    dispatches the returned signals to the OrderManager.
    """

    @abstractmethod
    def on_bar(self, bar_time: datetime, o: float, h: float, l: float,
               c: float, position_qty: int = 0) -> list[Signal]:
        """Process a completed bar and return trade signals."""

    @abstractmethod
    def get_state_snapshot(self) -> dict:
        """Return serializable state for crash-recovery persistence."""

    @abstractmethod
    def restore_state(self, trade_state: TradeState, bars: list[dict]) -> None:
        """Restore state from persistence."""

    @abstractmethod
    def check_eod_flatten(self, bar_time: datetime) -> bool:
        """Return True if we are in the EOD flatten window."""

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """Human-readable strategy name (e.g. 'MagicLine')."""

    # Shared concrete attributes that all engines expose
    trade: TradeState
    trades_today: int
    daily_pnl: float

    def update_daily_pnl(self, realized_pnl: float) -> None:
        """Update daily P&L from a closed trade."""
        self.daily_pnl += realized_pnl
