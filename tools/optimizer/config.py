"""
Optimization Configuration
Defines the parameter space and optimization settings.
"""

# Parameter ranges to explore
PARAM_SPACE = {
    "tp1_r": {
        "min": 0.5,
        "max": 2.0,
        "step": 0.25,
        "default": 1.0,
        "description": "TP1 R-multiple (first target)"
    },
    "tp2_r": {
        "min": 1.0,
        "max": 4.0,
        "step": 0.5,
        "default": 2.0,
        "description": "TP2 R-multiple (second target)"
    },
    "be_trigger_pts": {
        "min": 2.0,
        "max": 10.0,
        "step": 1.0,
        "default": 5.0,
        "description": "Breakeven trigger (points profit)"
    },
    "stop_buffer_ticks": {
        "min": 10,
        "max": 30,
        "step": 5,
        "default": 20,
        "description": "Stop buffer/distance (ticks)"
    },
    "partial_pct": {
        "min": 25,
        "max": 75,
        "step": 25,
        "default": 50,
        "description": "Partial exit percentage"
    }
}

# Number of variants to test per iteration (including baseline)
VARIANTS_PER_ITERATION = 4

# Variant slot names (must match Java file names and log labels)
VARIANT_SLOTS = [
    ("MagicLineStrategy", "Original", "Magic Line"),
    ("MagicLineStrategyV1", "V1", "ML-V1"),
    ("MagicLineStrategyV2", "V2", "ML-V2"),
    ("MagicLineStrategyV3", "V3", "ML-V3"),
]

# Variant names used in log parsing (must match VARIANT_NAMES in log_parser.py)
VARIANT_NAMES = ["Original", "V1", "V2", "V3"]

# Point value for P&L calculation
MES_POINT_VALUE = 5.0

# Paths
PROJECT_ROOT = r"C:\Users\jung_\OneDrive\Claude Code Text to Motivewave Strategy"
STRATEGY_DIR = PROJECT_ROOT + r"\src\main\java\com\mw\studies"
LOG_DIR = r"C:\Users\jung_\AppData\Roaming\MotiveWave\output"
RESULTS_DIR = PROJECT_ROOT + r"\tools\optimizer\results"
