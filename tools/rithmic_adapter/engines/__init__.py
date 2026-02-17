"""Engine registry and factory for live trading strategy engines."""

from __future__ import annotations

from engines.base import BaseLiveEngine


def _lazy_registry() -> dict[str, type[BaseLiveEngine]]:
    """Build the strategy name -> engine class mapping.

    Imports are deferred to avoid circular-import issues and to keep
    startup fast when only one engine is needed.
    """
    from engines.magicline import MagicLineLiveEngine
    from engines.lb_short import LBShortLiveEngine
    from engines.ifvg import IFVGLiveEngine
    from engines.swingreclaim import SwingReclaimLiveEngine
    from engines.jadecap import JadeCapLiveEngine
    from engines.brianstonk import BrianStonkLiveEngine

    return {
        "MagicLine": MagicLineLiveEngine,
        "LB Short": LBShortLiveEngine,
        "IFVG": IFVGLiveEngine,
        "SwingReclaim": SwingReclaimLiveEngine,
        "JadeCap": JadeCapLiveEngine,
        "BrianStonk": BrianStonkLiveEngine,
    }


# Canonical list of strategy names (for UI dropdowns, etc.)
STRATEGY_NAMES: list[str] = [
    "MagicLine",
    "LB Short",
    "IFVG",
    "SwingReclaim",
    "JadeCap",
    "BrianStonk",
]


def create_engine(name: str, params: dict) -> BaseLiveEngine:
    """Instantiate a live engine by strategy name.

    Args:
        name: Strategy name (must match a key in the registry).
        params: Strategy-specific parameters dict passed to the engine ctor.

    Returns:
        An initialized engine instance.

    Raises:
        ValueError: If the strategy name is not registered.
    """
    registry = _lazy_registry()
    cls = registry.get(name)
    if cls is None:
        available = ", ".join(sorted(registry.keys()))
        raise ValueError(
            f"Unknown strategy '{name}'. Available: {available}"
        )
    return cls(params)
