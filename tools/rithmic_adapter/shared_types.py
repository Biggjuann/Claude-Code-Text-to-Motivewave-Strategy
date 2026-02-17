"""Shared data types for the Rithmic live trading adapter.

Extracted from strategy_engine.py so all engines and infrastructure
modules can import from a single location.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class Action(Enum):
    BUY = auto()
    SELL = auto()
    FLATTEN = auto()


@dataclass
class Signal:
    """Trade signal emitted by a strategy engine."""
    action: Action
    qty: int
    reason: str
    price: float = 0.0   # for stop/limit orders; 0 = market

    def __repr__(self) -> str:
        px = f" @{self.price:.2f}" if self.price > 0 else ""
        return f"Signal({self.action.name} {self.qty}{px} [{self.reason}])"


@dataclass
class TradeState:
    """Active trade state."""
    entry_price: float = 0.0
    stop_price: float = 0.0
    tp1_price: float = 0.0
    tp2_price: float = 0.0
    risk_points: float = 0.0
    initial_qty: int = 0
    partial_taken: bool = False
    be_activated: bool = False
    trail_active: bool = False
    direction: int = 0  # 1=long, -1=short, 0=flat

    # Broker order IDs for live order management
    stop_order_id: str = ""
    tp1_order_id: str = ""
    tp2_order_id: str = ""

    @property
    def is_active(self) -> bool:
        return self.entry_price > 0.0

    def to_dict(self) -> dict:
        return {
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "tp1_price": self.tp1_price,
            "tp2_price": self.tp2_price,
            "risk_points": self.risk_points,
            "initial_qty": self.initial_qty,
            "partial_taken": self.partial_taken,
            "be_activated": self.be_activated,
            "trail_active": self.trail_active,
            "direction": self.direction,
            "stop_order_id": self.stop_order_id,
            "tp1_order_id": self.tp1_order_id,
            "tp2_order_id": self.tp2_order_id,
        }

    @classmethod
    def from_dict(cls, d: dict) -> TradeState:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


@dataclass
class PositionInfo:
    """Broker-reported position."""
    qty: int = 0
    avg_price: float = 0.0
    unrealized_pnl: float = 0.0
