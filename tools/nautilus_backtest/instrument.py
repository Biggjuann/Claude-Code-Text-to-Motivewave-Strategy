"""ES futures instrument definition for NautilusTrader backtesting."""

import pytz
import pandas as pd

from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
from nautilus_trader.model.currencies import USD
from nautilus_trader.model.enums import AssetClass
from nautilus_trader.model.instruments import FuturesContract
from nautilus_trader.model.objects import Price, Quantity


def create_es_instrument(
    venue: Venue = None,
    price_precision: int = 2,
    price_increment: str = "0.01",  # 0.01 for ratio-adjusted data, 0.25 for raw
    multiplier: int = 50,           # $50/point for ES, $5 for MES
) -> FuturesContract:
    """Create an ES futures contract instrument for backtesting."""
    if venue is None:
        venue = Venue("SIM")

    activation = pd.Timestamp("2008-01-01", tz=pytz.utc)
    expiration = pd.Timestamp("2027-01-01", tz=pytz.utc)

    return FuturesContract(
        instrument_id=InstrumentId(Symbol("ES"), venue),
        raw_symbol=Symbol("ES"),
        asset_class=AssetClass.INDEX,
        exchange="XCME",
        currency=USD,
        price_precision=price_precision,
        price_increment=Price.from_str(price_increment),
        multiplier=Quantity.from_int(multiplier),
        lot_size=Quantity.from_int(1),
        underlying="ES",
        activation_ns=activation.value,
        expiration_ns=expiration.value,
        ts_event=activation.value,
        ts_init=activation.value,
    )
