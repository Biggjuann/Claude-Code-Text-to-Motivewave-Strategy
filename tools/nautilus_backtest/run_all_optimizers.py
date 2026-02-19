"""
Master Runner — Runs all 5 strategy optimizers sequentially.

1. Displacement Candle (verification with updated defaults)
2. Williams Volatility Breakout
3. IFVG Retest
4. MagicLine
5. SwingReclaim

Each optimizer saves results to its own CSV in results/ subdirectory.
Run time estimate: ~6-8 hours total (16 years × ~100 combos × 5 strategies).
"""

import subprocess
import sys
import time
from pathlib import Path

PYTHON = sys.executable
BASE_DIR = Path(__file__).parent

OPTIMIZERS = [
    ("Displacement Candle", "optimize_displacement_full.py"),
    ("Williams VB", "optimize_williams_full.py"),
    ("IFVG Retest", "optimize_ifvg_full.py"),
    ("MagicLine", "optimize_magicline_full.py"),
    ("SwingReclaim", "optimize_swingreclaim_full.py"),
]

print("=" * 80)
print("MASTER OPTIMIZER RUNNER — ALL STRATEGIES (2010-2026)")
print("=" * 80)
print(f"Python: {PYTHON}")
print(f"Base dir: {BASE_DIR}")
print(f"Strategies: {len(OPTIMIZERS)}")
print()

total_start = time.time()
results_summary = []

for idx, (name, script) in enumerate(OPTIMIZERS):
    print(f"\n{'='*80}")
    print(f"[{idx+1}/{len(OPTIMIZERS)}] Starting: {name}")
    print(f"{'='*80}\n")

    script_path = BASE_DIR / script
    if not script_path.exists():
        print(f"  ERROR: {script_path} not found, skipping.")
        results_summary.append((name, "SKIPPED", 0))
        continue

    start = time.time()
    try:
        result = subprocess.run(
            [PYTHON, "-u", str(script_path)],
            cwd=str(BASE_DIR),
            timeout=7200,  # 2 hour timeout per strategy
        )
        elapsed = time.time() - start
        status = "OK" if result.returncode == 0 else f"FAIL (rc={result.returncode})"
        results_summary.append((name, status, elapsed))
        print(f"\n  Completed {name} in {elapsed/60:.1f} minutes [{status}]")
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        results_summary.append((name, "TIMEOUT", elapsed))
        print(f"\n  TIMEOUT: {name} after {elapsed/60:.1f} minutes")
    except Exception as e:
        elapsed = time.time() - start
        results_summary.append((name, f"ERROR: {e}", elapsed))
        print(f"\n  ERROR: {name} - {e}")

total_elapsed = time.time() - total_start

print("\n\n" + "=" * 80)
print("OPTIMIZATION COMPLETE — SUMMARY")
print("=" * 80)
print(f"Total time: {total_elapsed/3600:.1f} hours ({total_elapsed/60:.0f} minutes)")
print()
print(f"{'Strategy':<25} {'Status':<15} {'Time':>10}")
print("-" * 55)
for name, status, elapsed in results_summary:
    print(f"{name:<25} {status:<15} {elapsed/60:>8.1f}m")

print("\n\nResults CSVs:")
result_files = [
    "results/displacement_full_sweep.csv",
    "results/williams_full_sweep/williams_full_sweep.csv",
    "results/ifvg_full_sweep/ifvg_full_sweep.csv",
    "results/magicline_full_sweep/magicline_full_sweep.csv",
    "results/swingreclaim_full_sweep/swingreclaim_full_sweep.csv",
]
for f in result_files:
    fp = BASE_DIR / f
    exists = "EXISTS" if fp.exists() else "MISSING"
    print(f"  [{exists}] {f}")

print("\nDone! Check individual CSVs for detailed results.")
