"""JSON file-based state persistence for crash recovery.

Saves trade state, bar history, and position info after every bar.
On startup, loads state and allows reconciliation with broker position.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from shared_types import PositionInfo, TradeState

log = logging.getLogger(__name__)


class StateStore:
    """Persist strategy state to disk for crash recovery.

    State is written atomically (write-to-temp then rename) to prevent
    corruption from mid-write crashes.
    """

    def __init__(self, log_dir: str = "./logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.log_dir / "state.json"
        self._trade_log_file = self.log_dir / "trades.jsonl"
        self._equity_log_file = self.log_dir / "equity.jsonl"

    def save(self, state_snapshot: dict) -> None:
        state_snapshot["saved_at"] = datetime.now().isoformat()

        tmp_file = self.state_file.with_suffix(".tmp")
        try:
            with open(tmp_file, "w") as f:
                json.dump(state_snapshot, f, indent=2)
            tmp_file.replace(self.state_file)
            log.debug("State saved: trade_active=%s", state_snapshot.get("trade", {}).get("entry_price", 0) > 0)
        except Exception:
            log.exception("Failed to save state")

    def load(self) -> Optional[dict]:
        if not self.state_file.exists():
            log.info("No saved state found")
            return None

        try:
            with open(self.state_file) as f:
                state = json.load(f)
            log.info("State loaded from %s (saved at %s)",
                     self.state_file, state.get("saved_at", "unknown"))
            return state
        except Exception:
            log.exception("Failed to load state — starting fresh")
            return None

    def clear(self) -> None:
        if self.state_file.exists():
            self.state_file.unlink()
            log.info("State cleared")

    def log_trade(self, trade_info: dict) -> None:
        trade_info["timestamp"] = datetime.now().isoformat()
        try:
            with open(self._trade_log_file, "a") as f:
                f.write(json.dumps(trade_info) + "\n")
            log.info("Trade logged: %s", trade_info.get("reason", ""))
        except Exception:
            log.exception("Failed to log trade")

    def log_equity(self, timestamp: str, realized_pnl: float,
                   unrealized_pnl: float, position_qty: int) -> None:
        record = {
            "ts": timestamp,
            "realized": realized_pnl,
            "unrealized": unrealized_pnl,
            "total": realized_pnl + unrealized_pnl,
            "qty": position_qty,
        }
        try:
            with open(self._equity_log_file, "a") as f:
                f.write(json.dumps(record) + "\n")
        except Exception:
            log.exception("Failed to log equity tick")

    def load_equity_log(self) -> list[dict]:
        if not self._equity_log_file.exists():
            return []
        records = []
        try:
            with open(self._equity_log_file) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        except Exception:
            log.exception("Failed to load equity log")
        return records

    def reconcile(self, saved_trade: TradeState, broker_position: PositionInfo) -> TradeState:
        """Reconcile saved state with broker-reported position.

        Handles mismatches from fills that occurred while disconnected.
        Supports both long (qty > 0) and short (qty < 0) positions.
        """
        if not saved_trade.is_active:
            if broker_position.qty != 0:
                log.warning(
                    "No saved trade but broker shows position: qty=%d avg=%.2f. "
                    "Manual intervention may be needed.",
                    broker_position.qty, broker_position.avg_price,
                )
            return saved_trade

        if broker_position.qty == 0:
            log.warning(
                "Saved trade active (entry=%.2f) but broker position is flat. "
                "Trade was likely stopped out while disconnected.",
                saved_trade.entry_price,
            )
            self.log_trade({
                "reason": "reconcile_flat",
                "entry_price": saved_trade.entry_price,
                "stop_price": saved_trade.stop_price,
                "note": "Position closed while disconnected",
            })
            return TradeState()  # Reset

        # Check qty mismatch (use absolute values for comparison)
        broker_abs_qty = abs(broker_position.qty)
        if broker_abs_qty != saved_trade.initial_qty:
            log.warning(
                "Position qty mismatch: saved=%d, broker=%d. "
                "Partial fill may have occurred while disconnected.",
                saved_trade.initial_qty, broker_position.qty,
            )
            if broker_abs_qty < saved_trade.initial_qty:
                saved_trade.partial_taken = True
                saved_trade.be_activated = True
                saved_trade.trail_active = True
                log.info("Assuming partial was taken — activating trail mode")

        log.info("Reconciled: trade active, entry=%.2f, broker_qty=%d",
                 saved_trade.entry_price, broker_position.qty)
        return saved_trade
