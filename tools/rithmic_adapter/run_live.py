"""Main async entry point for Rithmic Live Trading Adapter.

Wires together: config → Rithmic connection → bar aggregator →
strategy engine → order manager → state persistence.

Usage:
    python run_live.py                  # uses ./config.yaml
    python run_live.py --config my.yaml # custom config path
    python run_live.py --dry-run        # connect + stream bars, no orders
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from async_rithmic import RithmicClient, ReconnectionSettings

from config import RithmicConfig, load_config
from contract_roller import check_roll_needed, next_roll_date
from bar_aggregator import Bar, BarAggregator
from engines import create_engine
from engines.base import BaseLiveEngine
from shared_types import Action, TradeState, PositionInfo
from order_manager import OrderManager
from state_store import StateStore

ET = ZoneInfo("America/New_York")

log = logging.getLogger("rithmic_adapter")


# ==================== Logging Setup ====================

def setup_logging(log_dir: str, level: str = "INFO") -> None:
    """Configure logging to both console and file."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(ET).strftime("%Y%m%d")
    file_handler = logging.FileHandler(
        log_path / f"adapter_{date_str}.log", encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    # Reduce noise from async_rithmic internals
    logging.getLogger("rithmic").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("async_rithmic").setLevel(logging.WARNING)


# ==================== Main Application ====================

class LiveAdapter:
    """Orchestrates the live trading pipeline."""

    def __init__(self, config: RithmicConfig, dry_run: bool = False):
        self.cfg = config
        self.dry_run = dry_run

        # Components (initialized in start())
        self.client: RithmicClient | None = None
        self.aggregator: BarAggregator | None = None
        self.engine: BaseLiveEngine | None = None
        self.order_mgr: OrderManager | None = None
        self.state_store: StateStore | None = None

        # Shutdown coordination
        self._shutdown_event = asyncio.Event()
        self._last_tick_time: datetime | None = None

        # Daily loss tracking
        self._daily_loss_halt = False

    async def start(self) -> None:
        """Initialize all components, connect, and run the event loop."""
        cfg = self.cfg

        # Paper mode safety gate
        if not cfg.paper_mode and not self.dry_run:
            log.warning("=" * 60)
            log.warning("  LIVE TRADING MODE — paper_mode is OFF")
            log.warning("  Real money is at risk!")
            log.warning("=" * 60)

        # 1. Initialize strategy engine via factory
        self.engine = create_engine(cfg.strategy_name, cfg.strategy_params)
        self.state_store = StateStore(cfg.log_dir)
        self.aggregator = BarAggregator(
            bar_size_minutes=cfg.bar_size_minutes,
            on_bar=self._on_bar,
        )

        # 2. Connect to Rithmic
        log.info("Connecting to Rithmic: %s (%s)", cfg.uri, cfg.system)
        log.info("Symbol: %s/%s, Account: %s", cfg.symbol, cfg.exchange, cfg.account_id)
        log.info("Strategy: %s", cfg.strategy_name)
        log.info("Paper mode: %s, Dry run: %s", cfg.paper_mode, self.dry_run)
        log.info("Max daily loss: $%.0f, Max contracts: %d",
                 cfg.max_daily_loss, cfg.max_contracts)

        if cfg.auto_roll:
            nrd = next_roll_date(cfg.root_symbol, roll_days=cfg.roll_days_before)
            log.info("Auto-roll enabled: %s → %s (next roll: %s)",
                     cfg.root_symbol, cfg.symbol, nrd.isoformat())

        reconnection = ReconnectionSettings(
            max_retries=None,     # retry forever
            backoff_type="exponential",
            interval=2,
            max_delay=60,
            jitter_range=(0.5, 2.0),
        )

        app_name = f"{cfg.strategy_name}Adapter"
        self.client = RithmicClient(
            user=cfg.user,
            password=cfg.password,
            system_name=cfg.system,
            app_name=app_name,
            app_version="2.0",
            url=cfg.uri,
            reconnection_settings=reconnection,
        )

        # Register connection event handlers
        self.client.on_connected += self._on_connected
        self.client.on_disconnected += self._on_disconnected

        await self.client.connect()
        log.info("Connected to Rithmic")

        # 3. Initialize order manager
        self.order_mgr = OrderManager(
            client=self.client,
            account_id=cfg.account_id,
            exchange=cfg.exchange,
            symbol=cfg.symbol,
            max_contracts=cfg.max_contracts,
        )

        # 4. Wire order notification handlers
        self.client.on_exchange_order_notification += self.order_mgr.on_exchange_order_notification
        self.client.on_rithmic_order_notification += self.order_mgr.on_rithmic_order_notification

        # 5. Restore state from crash recovery
        await self._restore_state()

        # 6. Subscribe to tick data
        from async_rithmic import DataType
        self.client.on_tick += self._on_tick
        await self.client.subscribe_to_market_data(
            symbol=cfg.symbol,
            exchange=cfg.exchange,
            data_type=DataType.LAST_TRADE,
        )
        log.info("Subscribed to tick data: %s/%s", cfg.symbol, cfg.exchange)

        # 7. Subscribe to PnL updates
        self.client.on_instrument_pnl_update += self._on_pnl_update
        await self.client.subscribe_to_pnl_updates()

        # 8. Start stale-tick watchdog and auto-roll check
        stale_task = asyncio.create_task(self._stale_tick_watchdog())
        roll_task = None
        if cfg.auto_roll:
            roll_task = asyncio.create_task(self._roll_check_task())

        # 9. Wait for shutdown signal
        log.info("=" * 60)
        log.info("%s Live Adapter running. Press Ctrl+C to stop.", cfg.strategy_name)
        log.info("=" * 60)

        await self._shutdown_event.wait()

        # 10. Graceful shutdown
        log.info("Shutting down...")
        stale_task.cancel()
        if roll_task:
            roll_task.cancel()
        await self._shutdown()

    async def _shutdown(self) -> None:
        """Graceful shutdown: flatten, save state, disconnect."""
        if self.order_mgr and not self.dry_run:
            if self.engine and self.engine.trade.is_active:
                log.info("Flattening position before shutdown")
                await self.order_mgr.flatten_position()

        if self.aggregator:
            await self.aggregator.flush()

        if self.engine and self.state_store:
            snapshot = self.engine.get_state_snapshot()
            self.state_store.save(snapshot)

        if self.client:
            await self.client.disconnect()
            log.info("Disconnected from Rithmic")

    # ==================== Event Handlers ====================

    async def _on_tick(self, tick: dict) -> None:
        """Handle incoming tick from Rithmic TICKER plant.

        async_rithmic tick fields (from last_trade.proto):
          trade_price, trade_size, datetime, symbol, exchange, ...
        """
        # Filter to LAST_TRADE only (on_tick also fires for BBO)
        from async_rithmic import DataType
        if tick.get("data_type") != DataType.LAST_TRADE:
            return

        price = tick.get("trade_price", 0.0)
        size = tick.get("trade_size", 1)

        if price <= 0:
            return

        # async_rithmic adds 'datetime' key (timezone-aware) from ssboe/usecs
        ts = tick.get("datetime")
        if ts is None:
            now = datetime.now(ET)
        elif isinstance(ts, datetime):
            now = ts if ts.tzinfo else ts.replace(tzinfo=ET)
        elif isinstance(ts, (int, float)):
            now = datetime.fromtimestamp(ts, tz=ET)
        else:
            now = datetime.now(ET)

        self._last_tick_time = now
        await self.aggregator.on_tick(price, size, now)

    async def _on_bar(self, bar: Bar) -> None:
        """Handle completed bar from aggregator → strategy → orders."""
        bar_time = bar.timestamp
        log.info("BAR: %s O=%.2f H=%.2f L=%.2f C=%.2f V=%d",
                 bar_time.strftime("%H:%M"), bar.open, bar.high,
                 bar.low, bar.close, bar.volume)

        # Max daily loss check
        if self._daily_loss_halt:
            log.debug("Daily loss halt active — skipping bar")
            return

        position_qty = self.order_mgr.position.qty if self.order_mgr else 0

        signals = self.engine.on_bar(
            bar_time=bar_time,
            o=bar.open,
            h=bar.high,
            l=bar.low,
            c=bar.close,
            position_qty=position_qty,
        )

        if signals:
            for s in signals:
                log.info("SIGNAL: %s", s)
            if not self.dry_run and self.order_mgr:
                await self.order_mgr.execute_signals(signals, self.engine.trade)
            elif self.dry_run:
                log.info("DRY RUN: would execute %d signal(s)", len(signals))

        # Check max daily loss after processing signals
        daily_pnl = self.engine.daily_pnl
        if daily_pnl <= -self.cfg.max_daily_loss and not self._daily_loss_halt:
            log.warning("MAX DAILY LOSS REACHED: $%.2f (limit: $%.2f)",
                        daily_pnl, self.cfg.max_daily_loss)
            self._daily_loss_halt = True
            if self.order_mgr and not self.dry_run and self.engine.trade.is_active:
                log.warning("Flattening position due to max daily loss")
                await self.order_mgr.flatten_position()

        # Save state after every bar
        if self.state_store:
            snapshot = self.engine.get_state_snapshot()
            self.state_store.save(snapshot)

            unrealized = self.order_mgr.position.unrealized_pnl if self.order_mgr else 0.0
            self.state_store.log_equity(
                timestamp=bar_time.isoformat(),
                realized_pnl=self.engine.daily_pnl,
                unrealized_pnl=unrealized,
                position_qty=position_qty,
            )

    async def _on_pnl_update(self, update: dict) -> None:
        """Handle PnL updates from Rithmic PNL plant.

        async_rithmic PnL fields (from instrument_pnl_position_update.proto):
          symbol, net_quantity, avg_open_fill_price, day_pnl,
          day_open_pnl, day_closed_pnl, buy_qty, sell_qty, ...
        """
        symbol = update.get("symbol", "")
        if symbol != self.cfg.symbol:
            return

        qty = update.get("net_quantity", 0)
        avg_price = update.get("avg_open_fill_price", 0.0)
        unrealized = update.get("day_open_pnl", 0.0)

        if self.order_mgr:
            self.order_mgr.position = PositionInfo(
                qty=qty,
                avg_price=avg_price,
                unrealized_pnl=unrealized,
            )

        log.debug("PNL update: %s qty=%d avg=%.2f unrealized=%.2f",
                  symbol, qty, avg_price, unrealized)

    async def _on_connected(self, plant_type: str) -> None:
        log.info("Connected to %s plant", plant_type)

    async def _on_disconnected(self, plant_type: str) -> None:
        log.warning("Disconnected from %s plant — auto-reconnect will attempt",
                     plant_type)

    # ==================== State Recovery ====================

    async def _restore_state(self) -> None:
        """Restore state from disk and reconcile with broker position."""
        saved = self.state_store.load()
        if saved is None:
            return

        trade_dict = saved.get("trade", {})
        trade = TradeState.from_dict(trade_dict)

        bars = saved.get("bars", [])
        self.engine.trades_today = saved.get("trades_today", 0)
        self.engine.daily_pnl = saved.get("daily_pnl", 0.0)

        ema_val = saved.get("ema_value")
        if ema_val is not None and hasattr(self.engine, "ema_value"):
            self.engine.ema_value = ema_val
            self.engine.ema_count = saved.get("ema_count", 0)

        broker_pos = PositionInfo()
        try:
            broker_pos = await self.order_mgr.sync_position()
        except Exception:
            log.exception("Failed to sync broker position for reconciliation")

        trade = self.state_store.reconcile(trade, broker_pos)

        if trade.is_active or bars:
            self.engine.restore_state(trade, bars)

        if trade.is_active and self.order_mgr:
            self.order_mgr.stop_order_id = trade.stop_order_id
            self.order_mgr.tp1_order_id = trade.tp1_order_id
            self.order_mgr.tp2_order_id = trade.tp2_order_id

        # Reset daily loss halt based on restored PnL
        if self.engine.daily_pnl <= -self.cfg.max_daily_loss:
            log.warning("Daily loss limit already reached on restart: $%.2f",
                        self.engine.daily_pnl)
            self._daily_loss_halt = True

    # ==================== Auto-Roll ====================

    async def _roll_check_task(self) -> None:
        """Check once daily at 00:05 ET if a contract roll is needed."""
        while True:
            now = datetime.now(ET)
            # Schedule next check at 00:05 ET
            target = now.replace(hour=0, minute=5, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait_secs = (target - now).total_seconds()
            log.debug("Roll check scheduled in %.0f seconds (at %s ET)",
                      wait_secs, target.strftime("%Y-%m-%d %H:%M"))
            await asyncio.sleep(wait_secs)

            today = datetime.now(ET).date()
            should_roll, new_symbol = check_roll_needed(
                self.cfg.symbol, self.cfg.root_symbol,
                as_of=today, roll_days=self.cfg.roll_days_before,
            )
            if should_roll:
                log.info("CONTRACT ROLL TRIGGERED: %s → %s", self.cfg.symbol, new_symbol)
                await self._execute_roll(new_symbol)
            else:
                nrd = next_roll_date(self.cfg.root_symbol, as_of=today,
                                     roll_days=self.cfg.roll_days_before)
                log.info("Roll check: no roll needed. Current: %s, next roll: %s",
                         self.cfg.symbol, nrd.isoformat())

    async def _execute_roll(self, new_symbol: str) -> None:
        """Roll from the current contract to a new one."""
        old_symbol = self.cfg.symbol

        # 1. Flatten any open position
        if self.order_mgr and not self.dry_run:
            if self.engine and self.engine.trade.is_active:
                log.info("Flattening position for contract roll")
                await self.order_mgr.flatten_position()
            # Cancel any working orders
            await self.order_mgr.cancel_all()

        # 2. Unsubscribe from old symbol tick data
        from async_rithmic import DataType
        try:
            await self.client.unsubscribe_from_market_data(
                symbol=old_symbol,
                exchange=self.cfg.exchange,
                data_type=DataType.LAST_TRADE,
            )
        except Exception:
            log.warning("Failed to unsubscribe from %s (may already be unsubscribed)",
                        old_symbol)

        # 3. Update symbol references
        self.cfg.symbol = new_symbol
        if self.order_mgr:
            self.order_mgr.symbol = new_symbol

        # 4. Reset aggregator and engine daily state
        if self.aggregator:
            self.aggregator.reset()
        if self.engine:
            self.engine.reset_daily()

        # 5. Subscribe to new symbol tick data
        self.client.on_tick += self._on_tick  # idempotent in most event systems
        await self.client.subscribe_to_market_data(
            symbol=new_symbol,
            exchange=self.cfg.exchange,
            data_type=DataType.LAST_TRADE,
        )
        log.info("Subscribed to new symbol: %s/%s", new_symbol, self.cfg.exchange)

        # 6. Update config.yaml on disk so restarts use the new symbol
        self._update_config_yaml_symbol(new_symbol)

        log.info("=" * 60)
        log.info("CONTRACT ROLL COMPLETE: %s → %s", old_symbol, new_symbol)
        log.info("=" * 60)

    def _update_config_yaml_symbol(self, new_symbol: str) -> None:
        """Update the symbol in config.yaml on disk."""
        import yaml
        cfg_path = Path("config.yaml")
        if not cfg_path.exists():
            return
        try:
            with open(cfg_path) as f:
                raw = yaml.safe_load(f)
            # Store the root symbol (not the resolved one) so auto-roll
            # continues to work on next restart
            raw.setdefault("rithmic", {})["symbol"] = self.cfg.root_symbol
            with open(cfg_path, "w") as f:
                yaml.dump(raw, f, default_flow_style=False, sort_keys=False)
            log.debug("Updated config.yaml symbol to %s", self.cfg.root_symbol)
        except Exception:
            log.exception("Failed to update config.yaml after roll")

    # ==================== Watchdog ====================

    async def _stale_tick_watchdog(self) -> None:
        """Warn if no ticks received during RTH for stale_tick_seconds."""
        while True:
            await asyncio.sleep(self.cfg.stale_tick_seconds)

            now = datetime.now(ET)
            if now.weekday() >= 5:
                continue
            hour_min = now.hour * 60 + now.minute
            if not (9 * 60 + 30 <= hour_min <= 16 * 60):
                continue

            if self._last_tick_time is None:
                log.warning("No ticks received yet during RTH")
            else:
                elapsed = (now - self._last_tick_time).total_seconds()
                if elapsed > self.cfg.stale_tick_seconds:
                    log.warning("STALE DATA: no tick for %.0fs (last: %s)",
                                elapsed,
                                self._last_tick_time.strftime("%H:%M:%S"))


# ==================== Entry Point ====================

def main():
    parser = argparse.ArgumentParser(description="Rithmic Live Trading Adapter")
    parser.add_argument("--config", default="config.yaml",
                        help="Path to config YAML file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Connect and stream bars, but don't submit orders")
    parser.add_argument("--log-level", default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
                        help="Console log level")
    args = parser.parse_args()

    config = load_config(args.config)

    setup_logging(config.log_dir, args.log_level)

    log.info("Rithmic Adapter v2.0 — Strategy: %s", config.strategy_name)
    log.info("Config: %s", args.config)

    adapter = LiveAdapter(config, dry_run=args.dry_run)

    loop = asyncio.new_event_loop()

    def request_shutdown():
        log.info("Shutdown requested (signal)")
        adapter._shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, request_shutdown)
        except NotImplementedError:
            pass

    try:
        loop.run_until_complete(adapter.start())
    except KeyboardInterrupt:
        log.info("Keyboard interrupt — shutting down")
        adapter._shutdown_event.set()
        loop.run_until_complete(adapter._shutdown())
    finally:
        loop.close()


if __name__ == "__main__":
    main()
