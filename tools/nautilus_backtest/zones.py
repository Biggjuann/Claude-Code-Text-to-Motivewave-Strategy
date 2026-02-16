"""Zone data structures for BrianStonk ICT strategy.

Ported from BrianStonkModularStrategy.java Zone/LiquidityTarget classes.
"""

from dataclasses import dataclass, field
from enum import IntEnum


class ZoneType(IntEnum):
    OB = 0
    BREAKER = 1
    FVG = 2
    IFVG = 3
    BPR = 4


# Bias constants
BIAS_BULLISH = 1
BIAS_BEARISH = -1
BIAS_NEUTRAL = 0


@dataclass
class Zone:
    top: float
    bottom: float
    bar_index: int
    is_bullish: bool
    zone_type: ZoneType
    is_valid: bool = True
    violated: bool = False

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def height(self) -> float:
        return abs(self.top - self.bottom)


@dataclass
class LiquidityTarget:
    price: float
    target_type: str   # "SESSION_HIGH", "SESSION_LOW", "SWING_HIGH", "SWING_LOW"
    is_bullish_draw: bool
