"""Configuration for Rithmic Live Trading Adapter.

Slim base config for connection/risk/operational settings.
Strategy-specific parameters live in strategy_params dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class RithmicConfig:
    # Connection
    uri: str = "wss://rituz00100.rithmic.com:443"
    system: str = "Rithmic Paper Trading"
    user: str = ""
    password: str = ""
    exchange: str = "CME"
    symbol: str = "ESH6"
    account_id: str = ""

    # Strategy selection
    strategy_name: str = "MagicLine"
    bar_size_minutes: int = 5

    # Risk
    max_daily_loss: float = 500.0
    max_contracts: int = 5
    stale_tick_seconds: int = 30

    # Auto-roll
    auto_roll: bool = True
    roll_days_before: int = 8
    root_symbol: str = ""  # derived from symbol if not explicitly set

    # Operational
    paper_mode: bool = True
    log_dir: str = "./logs"

    # Strategy-specific parameters (passed to the engine as-is)
    strategy_params: dict = field(default_factory=dict)


def load_config(path: str | Path = "config.yaml") -> RithmicConfig:
    """Load configuration from a YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}\n"
            f"Copy config.yaml.example to config.yaml and fill in your credentials."
        )

    with open(path) as f:
        raw = yaml.safe_load(f)

    rithmic = raw.get("rithmic", {})
    strategy = raw.get("strategy", {})
    risk = raw.get("risk", {})

    # Shared keys that live on RithmicConfig
    shared_keys = {"name", "bar_size_minutes"}

    # Everything else in the strategy block is strategy-specific
    strategy_params = {k: v for k, v in strategy.items() if k not in shared_keys}

    # Also merge risk params into strategy_params so engines can access them
    strategy_params["max_daily_loss"] = risk.get("max_daily_loss", 500.0)
    strategy_params["max_contracts"] = risk.get("max_contracts", 5)

    # Resolve auto-roll settings
    raw_symbol = rithmic.get("symbol", RithmicConfig.symbol)
    auto_roll = rithmic.get("auto_roll", True)
    roll_days_before = rithmic.get("roll_days_before", 8)

    # Determine root_symbol and resolve front-month if auto_roll enabled
    if auto_roll:
        from contract_roller import resolve_front_month, parse_symbol, _SYMBOL_RE
        # If user gave a full symbol like "ESH6", extract the root
        if _SYMBOL_RE.match(raw_symbol.upper()):
            root_symbol, _, _ = parse_symbol(raw_symbol)
        else:
            root_symbol = raw_symbol.upper()
        resolved_symbol = resolve_front_month(root_symbol, roll_days=roll_days_before)
    else:
        root_symbol = raw_symbol
        resolved_symbol = raw_symbol

    cfg = RithmicConfig(
        # Connection
        uri=rithmic.get("uri", RithmicConfig.uri),
        system=rithmic.get("system", RithmicConfig.system),
        user=rithmic.get("user", ""),
        password=rithmic.get("password", ""),
        exchange=rithmic.get("exchange", RithmicConfig.exchange),
        symbol=resolved_symbol,
        account_id=rithmic.get("account_id", ""),
        # Auto-roll
        auto_roll=auto_roll,
        roll_days_before=roll_days_before,
        root_symbol=root_symbol,
        # Strategy
        strategy_name=strategy.get("name", RithmicConfig.strategy_name),
        bar_size_minutes=strategy.get("bar_size_minutes", RithmicConfig.bar_size_minutes),
        # Risk
        max_daily_loss=risk.get("max_daily_loss", RithmicConfig.max_daily_loss),
        max_contracts=risk.get("max_contracts", RithmicConfig.max_contracts),
        stale_tick_seconds=risk.get("stale_tick_seconds", RithmicConfig.stale_tick_seconds),
        # Operational
        paper_mode=raw.get("paper_mode", RithmicConfig.paper_mode),
        log_dir=raw.get("log_dir", RithmicConfig.log_dir),
        # Strategy-specific
        strategy_params=strategy_params,
    )

    # Validate required fields
    errors = []
    if not cfg.user or cfg.user == "your_username":
        errors.append("rithmic.user is not set")
    if not cfg.password or cfg.password == "your_password":
        errors.append("rithmic.password is not set")
    if not cfg.account_id or cfg.account_id == "YOUR_ACCOUNT":
        errors.append("rithmic.account_id is not set")
    if not cfg.symbol and not cfg.root_symbol:
        errors.append("rithmic.symbol is not set")
    if cfg.bar_size_minutes < 1:
        errors.append("strategy.bar_size_minutes must be >= 1")
    if cfg.max_contracts < 1:
        errors.append("risk.max_contracts must be >= 1")
    if cfg.max_daily_loss <= 0:
        errors.append("risk.max_daily_loss must be > 0")

    if errors:
        raise ValueError(
            "Config validation failed:\n  " + "\n  ".join(errors) + "\n\n"
            "Edit config.yaml to fix these issues."
        )

    return cfg
