"""Rithmic order management — submit, track, modify, flatten.

Uses async_rithmic library for broker communication. Designed around
broker-held stop orders for crash safety.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from enum import Enum, auto

from async_rithmic import RithmicClient

from shared_types import Action, PositionInfo, Signal

log = logging.getLogger(__name__)


class OrderState(Enum):
    PENDING = auto()
    WORKING = auto()
    PARTIALLY_FILLED = auto()
    FILLED = auto()
    CANCELLED = auto()
    REJECTED = auto()


@dataclass
class TrackedOrder:
    order_id: str
    side: str            # "BUY" or "SELL"
    qty: int
    order_type: str      # "MARKET", "STOP", "LIMIT"
    price: float = 0.0
    state: OrderState = OrderState.PENDING
    filled_qty: int = 0
    reason: str = ""


class OrderManager:
    """Manages order lifecycle via Rithmic API.

    Responsibilities:
    - Submit market/stop/limit orders
    - Track order states and fills
    - Modify stop orders (BE, trail)
    - Flatten position (cancel all + market close)
    - Enforce max-position and single-position constraints
    """

    def __init__(
        self,
        client: RithmicClient,
        account_id: str,
        exchange: str,
        symbol: str,
        max_contracts: int = 5,
    ):
        self.client = client
        self.account_id = account_id
        self.exchange = exchange
        self.symbol = symbol
        self.max_contracts = max_contracts

        # Order tracking
        self.orders: dict[str, TrackedOrder] = {}
        self.position = PositionInfo()

        # Active broker order IDs for the current trade
        self.stop_order_id: str = ""
        self.tp1_order_id: str = ""
        self.tp2_order_id: str = ""

        # Callbacks
        self._on_fill_callbacks: list = []
        self._order_lock = asyncio.Lock()

    # ==================== Order Submission ====================

    async def submit_market_order(self, side: str, qty: int, reason: str = "") -> str:
        if qty <= 0:
            log.warning("Skipping market order with qty=%d", qty)
            return ""
        if qty > self.max_contracts:
            log.error("Order qty %d exceeds max %d — capping", qty, self.max_contracts)
            qty = self.max_contracts

        order_id = self._gen_order_id()
        async with self._order_lock:
            try:
                from async_rithmic import OrderType, TransactionType
                tx_type = TransactionType.BUY if side == "BUY" else TransactionType.SELL
                await self.client.submit_order(
                    order_id,
                    symbol=self.symbol,
                    exchange=self.exchange,
                    qty=qty,
                    order_type=OrderType.MARKET,
                    transaction_type=tx_type,
                    account_id=self.account_id,
                )
                tracked = TrackedOrder(
                    order_id=order_id, side=side, qty=qty,
                    order_type="MARKET", reason=reason,
                )
                self.orders[order_id] = tracked
                log.info("MARKET %s %d %s submitted: %s [%s]",
                         side, qty, self.symbol, order_id, reason)
                return order_id
            except Exception:
                log.exception("Failed to submit market order")
                return ""

    async def submit_stop_order(self, side: str, qty: int, stop_price: float,
                                reason: str = "") -> str:
        if qty <= 0:
            return ""

        order_id = self._gen_order_id()
        async with self._order_lock:
            try:
                from async_rithmic import OrderType, TransactionType
                tx_type = TransactionType.BUY if side == "BUY" else TransactionType.SELL
                await self.client.submit_order(
                    order_id,
                    symbol=self.symbol,
                    exchange=self.exchange,
                    qty=qty,
                    order_type=OrderType.STOP_MARKET,
                    transaction_type=tx_type,
                    trigger_price=stop_price,
                    account_id=self.account_id,
                )
                tracked = TrackedOrder(
                    order_id=order_id, side=side, qty=qty,
                    order_type="STOP", price=stop_price, reason=reason,
                )
                self.orders[order_id] = tracked
                log.info("STOP %s %d %s @%.2f submitted: %s [%s]",
                         side, qty, self.symbol, stop_price, order_id, reason)
                return order_id
            except Exception:
                log.exception("Failed to submit stop order")
                return ""

    async def submit_limit_order(self, side: str, qty: int, limit_price: float,
                                 reason: str = "") -> str:
        if qty <= 0:
            return ""

        order_id = self._gen_order_id()
        async with self._order_lock:
            try:
                from async_rithmic import OrderType, TransactionType
                tx_type = TransactionType.BUY if side == "BUY" else TransactionType.SELL
                await self.client.submit_order(
                    order_id,
                    symbol=self.symbol,
                    exchange=self.exchange,
                    qty=qty,
                    order_type=OrderType.LIMIT,
                    transaction_type=tx_type,
                    price=limit_price,
                    account_id=self.account_id,
                )
                tracked = TrackedOrder(
                    order_id=order_id, side=side, qty=qty,
                    order_type="LIMIT", price=limit_price, reason=reason,
                )
                self.orders[order_id] = tracked
                log.info("LIMIT %s %d %s @%.2f submitted: %s [%s]",
                         side, qty, self.symbol, limit_price, order_id, reason)
                return order_id
            except Exception:
                log.exception("Failed to submit limit order")
                return ""

    # ==================== Order Management ====================

    async def modify_stop(self, order_id: str, new_price: float) -> bool:
        if not order_id:
            log.warning("Cannot modify stop: no order_id")
            return False

        async with self._order_lock:
            try:
                await self.client.modify_order(
                    order_id=order_id,
                    trigger_price=new_price,
                )
                if order_id in self.orders:
                    self.orders[order_id].price = new_price
                log.info("Stop modified: %s → %.2f", order_id, new_price)
                return True
            except Exception:
                log.exception("Failed to modify stop %s", order_id)
                return False

    async def cancel_order(self, order_id: str) -> bool:
        if not order_id:
            return False

        async with self._order_lock:
            try:
                await self.client.cancel_order(order_id=order_id)
                if order_id in self.orders:
                    self.orders[order_id].state = OrderState.CANCELLED
                log.info("Order cancelled: %s", order_id)
                return True
            except Exception:
                log.exception("Failed to cancel order %s", order_id)
                return False

    async def flatten_position(self) -> None:
        log.info("FLATTEN: cancelling all orders and closing position")

        try:
            await self.client.cancel_all_orders()
            log.info("All orders cancelled")
        except Exception:
            log.exception("Error cancelling all orders")

        try:
            await self.client.exit_position(
                symbol=self.symbol,
                exchange=self.exchange,
            )
            log.info("Position exit submitted for %s", self.symbol)
        except Exception:
            log.exception("Error exiting position")

        self.stop_order_id = ""
        self.tp1_order_id = ""
        self.tp2_order_id = ""
        self.position = PositionInfo()

    # ==================== Signal Execution ====================

    async def execute_signals(self, signals: list[Signal], trade_state) -> None:
        """Execute a list of strategy signals.

        Handles both long and short entries based on signal action.
        BUY signals → long entry, SELL signals with qty > 0 → short entry or partial exit.
        """
        for signal in signals:
            if signal.action == Action.FLATTEN:
                await self.flatten_position()

            elif signal.action == Action.BUY and signal.qty > 0:
                # Could be a long entry or a short partial cover
                if trade_state.direction >= 0:
                    # Long entry
                    entry_id = await self.submit_market_order(
                        "BUY", signal.qty, signal.reason,
                    )
                    if entry_id and trade_state.is_active:
                        # Submit broker-held stop loss (SELL side for long)
                        stop_id = await self.submit_stop_order(
                            "SELL", signal.qty, trade_state.stop_price,
                            reason="Initial stop loss",
                        )
                        trade_state.stop_order_id = stop_id
                        self.stop_order_id = stop_id

                        if trade_state.tp1_price > 0 and trade_state.tp1_price > trade_state.entry_price:
                            partial_pct = 25
                            partial_qty = max(1, int(signal.qty * partial_pct / 100))
                            if partial_qty < signal.qty:
                                tp1_id = await self.submit_limit_order(
                                    "SELL", partial_qty, trade_state.tp1_price,
                                    reason="TP1 target",
                                )
                                trade_state.tp1_order_id = tp1_id
                                self.tp1_order_id = tp1_id
                else:
                    # Short partial cover (BUY to reduce short position)
                    await self.submit_market_order(
                        "BUY", signal.qty, signal.reason,
                    )

            elif signal.action == Action.SELL:
                if signal.qty == 0 and signal.price > 0:
                    # Modify existing stop (BE move)
                    if self.stop_order_id:
                        await self.modify_stop(self.stop_order_id, signal.price)
                elif signal.qty > 0:
                    if trade_state.direction <= 0 and trade_state.entry_price == 0:
                        # Short entry
                        entry_id = await self.submit_market_order(
                            "SELL", signal.qty, signal.reason,
                        )
                        if entry_id and trade_state.is_active:
                            # Submit broker-held stop loss (BUY side for short)
                            stop_id = await self.submit_stop_order(
                                "BUY", signal.qty, trade_state.stop_price,
                                reason="Initial stop loss",
                            )
                            trade_state.stop_order_id = stop_id
                            self.stop_order_id = stop_id

                            if trade_state.tp1_price > 0 and trade_state.tp1_price < trade_state.entry_price:
                                partial_pct = 25
                                partial_qty = max(1, int(signal.qty * partial_pct / 100))
                                if partial_qty < signal.qty:
                                    tp1_id = await self.submit_limit_order(
                                        "BUY", partial_qty, trade_state.tp1_price,
                                        reason="TP1 target",
                                    )
                                    trade_state.tp1_order_id = tp1_id
                                    self.tp1_order_id = tp1_id
                    else:
                        # Long partial exit
                        await self.submit_market_order(
                            "SELL", signal.qty, signal.reason,
                        )
                        if trade_state.partial_taken and trade_state.tp2_price > 0:
                            if self.stop_order_id:
                                await self.modify_stop(
                                    self.stop_order_id, trade_state.entry_price,
                                )
                            remaining = trade_state.initial_qty - signal.qty
                            if remaining > 0:
                                tp2_id = await self.submit_limit_order(
                                    "SELL", remaining, trade_state.tp2_price,
                                    reason="TP2 target",
                                )
                                trade_state.tp2_order_id = tp2_id
                                self.tp2_order_id = tp2_id

    # ==================== Position Query ====================

    async def sync_position(self) -> PositionInfo:
        """Query broker for current position and update local state."""
        try:
            positions = await self.client.list_positions(
                account_id=self.account_id,
            )
            if positions:
                for pos in positions:
                    sym = pos.get("symbol", "")
                    if sym == self.symbol:
                        qty = pos.get("net_quantity", 0)
                        avg = pos.get("avg_open_fill_price", 0.0)
                        pnl = pos.get("day_pnl", 0.0)
                        self.position = PositionInfo(
                            qty=qty, avg_price=avg, unrealized_pnl=pnl,
                        )
                        log.info("Position synced: qty=%d avg=%.2f pnl=%.2f",
                                 qty, avg, pnl)
                        return self.position

            log.info("No open position for %s", self.symbol)
            self.position = PositionInfo()
            return self.position
        except Exception:
            log.exception("Failed to sync position")
            return self.position

    # ==================== Event Handlers ====================

    async def on_exchange_order_notification(self, data: dict) -> None:
        """Handle exchange order notifications (fills, cancels, rejects).

        The async_rithmic library fires on_exchange_order_notification for
        fill confirmations from the exchange. Field names come from the
        exchange_order_notification.proto protobuf definition.
        """
        # Match by user_tag (our order_id)
        order_id = data.get("user_tag", "")
        if order_id not in self.orders:
            # Log untracked notifications for debugging
            notify_type = data.get("notify_type", "")
            if notify_type:
                log.debug("Untracked exchange notification: type=%s data=%s",
                          notify_type, data)
            return

        tracked = self.orders[order_id]
        notify_type = data.get("notify_type", "")

        # Fill notification
        fill_qty = data.get("fill_size", 0)
        fill_price = data.get("fill_price", 0.0)

        if fill_qty > 0:
            tracked.filled_qty += fill_qty
            if tracked.filled_qty >= tracked.qty:
                tracked.state = OrderState.FILLED
                log.info("Order FILLED: %s %s %d @%.2f [%s]",
                         tracked.side, tracked.order_type, tracked.qty,
                         fill_price, tracked.reason)
            else:
                tracked.state = OrderState.PARTIALLY_FILLED
                log.info("Order PARTIAL: %s %d/%d @%.2f",
                         order_id, tracked.filled_qty, tracked.qty, fill_price)

            for cb in self._on_fill_callbacks:
                await cb(tracked, data)

        # Rejection
        if "reject" in str(notify_type).lower():
            tracked.state = OrderState.REJECTED
            log.error("Order REJECTED: %s — %s",
                      order_id, data.get("text", "unknown"))

    async def on_rithmic_order_notification(self, data: dict) -> None:
        """Handle Rithmic-level order notifications (status updates).

        Covers working, cancelled, and other status transitions.
        """
        order_id = data.get("user_tag", "")
        if order_id not in self.orders:
            return

        tracked = self.orders[order_id]
        status = data.get("status", "")

        if status == "CANCELLED":
            tracked.state = OrderState.CANCELLED
            log.info("Order CANCELLED: %s [%s]", order_id, tracked.reason)

    def on_fill(self, callback) -> None:
        self._on_fill_callbacks.append(callback)

    # ==================== Helpers ====================

    @staticmethod
    def _gen_order_id() -> str:
        return f"RA_{uuid.uuid4().hex[:12]}"
