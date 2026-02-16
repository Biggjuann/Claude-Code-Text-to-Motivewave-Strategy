"""
Magic Line Strategy Optimizer - Main Orchestrator v2.1
Coordinates the analysis -> recommendation -> variant generation -> testing loop.

Usage:
    python optimizer.py              # Interactive menu
    python optimizer.py analyze      # Parse logs and show results
    python optimizer.py cycle        # Full cycle: analyze + generate + build
    python optimizer.py cycle -r     # Full cycle + restart MotiveWave
    python optimizer.py build        # Build and deploy strategies
    python optimizer.py build -r     # Build + restart MotiveWave
    python optimizer.py restart      # Restart MotiveWave only
    python optimizer.py status       # Show optimization progress
"""

import os
import sys
import json
import subprocess
import argparse
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple

# MotiveWave executable path
MOTIVEWAVE_EXE = r"C:\Program Files (x86)\MotiveWave\MotiveWave.exe"

from log_parser import parse_all_logs, calculate_stats, print_comparison_report, Trade
from config import (
    PROJECT_ROOT, STRATEGY_DIR, LOG_DIR, RESULTS_DIR,
    PARAM_SPACE, VARIANT_SLOTS, VARIANT_NAMES, MES_POINT_VALUE
)


class StrategyOptimizer:
    """
    Main optimizer class that orchestrates the optimization loop.

    Workflow:
    1. Parse logs from replay sessions
    2. Analyze performance per variant
    3. Identify best parameters and generate new variants
    4. Build and deploy variants
    5. User runs replay tests on variants
    6. Repeat with new log data
    """

    def __init__(self):
        self.project_dir = Path(PROJECT_ROOT)
        self.log_dir = Path(LOG_DIR)
        self.results_dir = Path(RESULTS_DIR)
        self.results_dir.mkdir(exist_ok=True)

        # State tracking
        self.iteration = 0
        self.history: List[Dict] = []
        self.best_params: Dict[str, any] = {}
        self.best_pnl: float = float('-inf')
        self.best_variant: str = ""

        # State file for persistence
        self.state_file = self.results_dir / "optimizer_state.json"

    def load_state(self) -> bool:
        """Load previous optimizer state if exists."""
        if self.state_file.exists():
            try:
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.iteration = state.get("iteration", 0)
                    self.history = state.get("history", [])
                    self.best_params = state.get("best_params", {})
                    self.best_pnl = state.get("best_pnl", float('-inf'))
                    self.best_variant = state.get("best_variant", "")
                    print(f"Loaded state: iteration {self.iteration}, best=${self.best_pnl * MES_POINT_VALUE:,.2f}")
                    return True
            except Exception as e:
                print(f"Warning: Could not load state: {e}")
        return False

    def save_state(self):
        """Save optimizer state for persistence."""
        state = {
            "iteration": self.iteration,
            "history": self.history,
            "best_params": self.best_params,
            "best_pnl": self.best_pnl,
            "best_variant": self.best_variant,
            "last_updated": datetime.now().isoformat()
        }
        with open(self.state_file, 'w') as f:
            json.dump(state, f, indent=2)

    def analyze(self) -> Tuple[Dict[str, Dict], str]:
        """Analyze current performance from logs.

        Returns:
            Tuple of (stats_by_variant, best_variant_name)
        """
        print("\n" + "=" * 70)
        print("ANALYZING PERFORMANCE")
        print("=" * 70)

        trades_by_variant = parse_all_logs(str(self.log_dir), newest_only=True)
        print()
        print_comparison_report(trades_by_variant)

        # Calculate stats per variant
        stats_by_variant = {}
        best_variant = ""
        best_pnl = float('-inf')

        for variant in VARIANT_NAMES:
            trades = trades_by_variant.get(variant, [])
            stats = calculate_stats(trades)
            stats_by_variant[variant] = stats

            if stats["total_pnl_points"] > best_pnl:
                best_pnl = stats["total_pnl_points"]
                best_variant = variant

        # Update best if this is better
        if best_pnl > self.best_pnl:
            self.best_pnl = best_pnl
            self.best_variant = best_variant
            print(f"\n*** NEW BEST: {best_variant} with ${best_pnl * MES_POINT_VALUE:+,.2f} ***")

        # Record in history
        self.history.append({
            "iteration": self.iteration + 1,
            "timestamp": datetime.now().isoformat(),
            "results": {v: {"pnl": s["total_pnl_points"], "trades": s["total_trades"]}
                       for v, s in stats_by_variant.items()},
            "best_variant": best_variant,
            "best_pnl": best_pnl
        })

        self.save_state()
        return stats_by_variant, best_variant

    def generate_next_variants(self, stats_by_variant: Dict[str, Dict]) -> List[Dict]:
        """Generate parameter combinations for next iteration based on results.

        Uses the performance data to decide which parameters to adjust.
        """
        recommendations = []

        # Get current parameter values for each variant (from config)
        current_params = self._get_current_variant_params()

        # Analyze what worked
        sorted_variants = sorted(
            [(v, s["total_pnl_points"]) for v, s in stats_by_variant.items() if s["total_trades"] > 0],
            key=lambda x: x[1],
            reverse=True
        )

        if not sorted_variants:
            print("No trades found - can't generate recommendations")
            return []

        best_variant, best_pnl = sorted_variants[0]
        worst_variant, worst_pnl = sorted_variants[-1]

        print(f"\nBest performer: {best_variant} ({best_pnl:+.2f} pts)")
        print(f"Worst performer: {worst_variant} ({worst_pnl:+.2f} pts)")

        # Get the best variant's parameters as baseline
        best_params = current_params.get(best_variant, current_params.get("Original", {}))

        # Generate variations around the best
        for param, config in PARAM_SPACE.items():
            current_val = best_params.get(param, config["default"])

            # Try stepping up and down from current best
            step = config["step"]
            variations = [
                current_val - step,
                current_val,
                current_val + step,
            ]

            # Filter to valid range
            variations = [
                v for v in variations
                if config["min"] <= v <= config["max"]
            ]

            recommendations.append({
                "param": param,
                "values": variations,
                "baseline": current_val,
                "reason": f"Testing around best performer's value ({current_val})"
            })

        return recommendations

    def _get_current_variant_params(self) -> Dict[str, Dict]:
        """Read current parameter defaults from strategy files."""
        params = {}

        for java_file, variant_name, _ in VARIANT_SLOTS:
            file_path = self.project_dir / "src/main/java/com/mw/studies" / f"{java_file}.java"
            if file_path.exists():
                params[variant_name] = self._parse_java_defaults(str(file_path))

        return params

    def _parse_java_defaults(self, file_path: str) -> Dict:
        """Parse default values from a Java strategy file."""
        import re
        defaults = {}

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Map of config key to Java constant
        param_keys = {
            "tp1_r": "TP1_R",
            "tp2_r": "TP2_R",
            "be_trigger_pts": "BE_TRIGGER_PTS",
            "stop_buffer_ticks": "STOP_BUFFER_TICKS",
            "partial_pct": "PARTIAL_PCT"
        }

        for config_key, java_key in param_keys.items():
            # DoubleDescriptor pattern
            double_match = re.search(
                rf'new DoubleDescriptor\(\s*{java_key}\s*,\s*"[^"]+"\s*,\s*([\d.]+)',
                content
            )
            if double_match:
                defaults[config_key] = float(double_match.group(1))
                continue

            # IntegerDescriptor pattern
            int_match = re.search(
                rf'new IntegerDescriptor\(\s*{java_key}\s*,\s*"[^"]+"\s*,\s*(\d+)',
                content
            )
            if int_match:
                defaults[config_key] = int(int_match.group(1))

        return defaults

    def update_variant_params(self, variant_name: str, new_params: Dict) -> bool:
        """Update a variant's default parameters in its Java file."""
        import re

        # Find the right file
        java_file = None
        for jf, vn, _ in VARIANT_SLOTS:
            if vn == variant_name:
                java_file = jf
                break

        if not java_file:
            print(f"Unknown variant: {variant_name}")
            return False

        file_path = self.project_dir / "src/main/java/com/mw/studies" / f"{java_file}.java"
        if not file_path.exists():
            print(f"File not found: {file_path}")
            return False

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Map of config key to Java constant
        param_keys = {
            "tp1_r": "TP1_R",
            "tp2_r": "TP2_R",
            "be_trigger_pts": "BE_TRIGGER_PTS",
            "stop_buffer_ticks": "STOP_BUFFER_TICKS",
            "partial_pct": "PARTIAL_PCT"
        }

        modified = content
        for config_key, value in new_params.items():
            java_key = param_keys.get(config_key)
            if not java_key:
                continue

            # Try DoubleDescriptor
            double_pattern = re.compile(
                rf'(new DoubleDescriptor\(\s*{java_key}\s*,\s*"[^"]+"\s*,\s*)([\d.]+)'
            )
            if double_pattern.search(modified):
                modified = double_pattern.sub(rf'\g<1>{float(value)}', modified)
                continue

            # Try IntegerDescriptor
            int_pattern = re.compile(
                rf'(new IntegerDescriptor\(\s*{java_key}\s*,\s*"[^"]+"\s*,\s*)(\d+)'
            )
            if int_pattern.search(modified):
                modified = int_pattern.sub(rf'\g<1>{int(value)}', modified)

        # Write back
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(modified)

        print(f"Updated {variant_name}: {new_params}")
        return True

    def apply_recommendations(self, recommendations: List[Dict]) -> int:
        """Apply parameter recommendations to variant files.

        Uses V1, V2, V3 slots for testing variations.
        Original stays as baseline.
        """
        if not recommendations:
            return 0

        print("\n" + "=" * 70)
        print("APPLYING PARAMETER CHANGES")
        print("=" * 70)

        # Create parameter sets for each variant slot
        variant_params = []

        # Simple approach: each variant tests a different parameter variation
        param_idx = 0
        for variant in ["V1", "V2", "V3"]:
            if param_idx >= len(recommendations):
                break

            rec = recommendations[param_idx]
            param = rec["param"]
            values = rec["values"]

            # Pick the non-baseline value (prefer higher if available)
            baseline = rec["baseline"]
            test_val = None
            for v in values:
                if v != baseline:
                    test_val = v
                    if v > baseline:  # Prefer testing higher values
                        break

            if test_val is not None:
                new_params = {param: test_val}
                if self.update_variant_params(variant, new_params):
                    variant_params.append({
                        "variant": variant,
                        "params": new_params
                    })

            param_idx += 1

        return len(variant_params)

    def restart_motivewave(self, wait_seconds: int = 5) -> bool:
        """Restart MotiveWave to reload strategies."""
        print("\n" + "=" * 70)
        print("RESTARTING MOTIVEWAVE")
        print("=" * 70)

        try:
            # Kill MotiveWave
            print("Stopping MotiveWave...")
            result = subprocess.run(
                ["taskkill", "/IM", "MotiveWave.exe", "/F"],
                capture_output=True,
                text=True
            )

            if "SUCCESS" in result.stdout or "not found" in result.stderr.lower():
                print("MotiveWave stopped.")
            else:
                print(f"Warning: {result.stderr}")

            # Wait for clean shutdown
            print(f"Waiting {wait_seconds} seconds...")
            time.sleep(wait_seconds)

            # Restart MotiveWave
            print("Starting MotiveWave...")
            subprocess.Popen(
                [MOTIVEWAVE_EXE],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )

            print("MotiveWave started. Please wait for it to fully load before running replay.")
            return True

        except Exception as e:
            print(f"Error restarting MotiveWave: {e}")
            return False

    def build_and_deploy(self, restart: bool = False) -> bool:
        """Build and deploy the strategy JAR."""
        print("\n" + "=" * 70)
        print("BUILDING AND DEPLOYING")
        print("=" * 70)

        try:
            # Build using full path to gradlew.bat from project directory
            gradle_path = self.project_dir / "gradlew.bat"
            if not gradle_path.exists():
                print(f"gradlew.bat not found at {gradle_path}")
                return False

            result = subprocess.run(
                [str(gradle_path), "build", "deploy", "--no-daemon"],
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(self.project_dir)  # Run from project directory
            )

            if result.returncode == 0:
                print("Build successful!")
                print("Deployed to MotiveWave Extensions folder")

                # Optionally restart MotiveWave
                if restart:
                    self.restart_motivewave()

                return True
            else:
                print(f"Build failed:\n{result.stderr}")
                if result.stdout:
                    # Show relevant output
                    lines = result.stdout.split('\n')
                    errors = [l for l in lines if 'error' in l.lower() or 'Error' in l]
                    if errors:
                        print("Errors found:")
                        for e in errors[:10]:
                            print(f"  {e}")
                return False

        except subprocess.TimeoutExpired:
            print("Build timed out")
            return False
        except Exception as e:
            print(f"Build error: {e}")
            return False

    def run_cycle(self, restart: bool = False) -> Dict:
        """Run a full optimization cycle: analyze -> generate -> apply -> build."""
        self.iteration += 1
        print(f"\n{'='*70}")
        print(f"OPTIMIZATION CYCLE {self.iteration}")
        print(f"{'='*70}")

        # Step 1: Analyze current performance
        stats, best_variant = self.analyze()

        # Step 2: Generate recommendations
        recommendations = self.generate_next_variants(stats)

        if not recommendations:
            print("\nNo recommendations generated. Need more trade data.")
            self.save_state()
            return {"success": False, "reason": "No recommendations"}

        # Step 3: Apply to variant files
        applied = self.apply_recommendations(recommendations)

        if applied == 0:
            print("\nNo parameter changes applied.")
            self.save_state()
            return {"success": False, "reason": "No changes applied"}

        # Step 4: Build and deploy (with optional restart)
        if not self.build_and_deploy(restart=restart):
            return {"success": False, "reason": "Build failed"}

        self.save_state()

        print("\n" + "=" * 70)
        print("CYCLE COMPLETE - NEXT STEPS")
        print("=" * 70)
        print("\n1. Restart MotiveWave to load updated strategies")
        print("2. Run replay test on all variants (Original, V1, V2, V3)")
        print("3. Run optimizer again to analyze results")

        return {
            "success": True,
            "iteration": self.iteration,
            "variants_updated": applied
        }

    def show_status(self):
        """Display optimization progress."""
        print("\n" + "=" * 70)
        print("OPTIMIZATION STATUS")
        print("=" * 70)

        print(f"\nIterations completed: {self.iteration}")

        if self.best_variant:
            print(f"Best variant so far: {self.best_variant}")
            print(f"Best P&L: ${self.best_pnl * MES_POINT_VALUE:+,.2f} ({self.best_pnl:+.2f} pts)")

        if self.history:
            print("\nRecent history:")
            print(f"{'Iter':<6} {'Best Variant':<12} {'P&L ($)':>12}")
            print("-" * 35)
            for h in self.history[-5:]:
                pnl_dollars = h["best_pnl"] * MES_POINT_VALUE
                print(f"{h['iteration']:<6} {h['best_variant']:<12} ${pnl_dollars:>+10,.2f}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Magic Line Strategy Optimizer")
    parser.add_argument("command", nargs="?", default="menu",
                       choices=["menu", "analyze", "generate", "build", "cycle", "status", "restart"],
                       help="Command to run")
    parser.add_argument("-r", "--restart", action="store_true",
                       help="Restart MotiveWave after build/cycle")

    args = parser.parse_args()

    optimizer = StrategyOptimizer()
    optimizer.load_state()

    if args.command == "menu":
        # Interactive menu
        print("=" * 70)
        print("MAGIC LINE STRATEGY OPTIMIZER")
        print("=" * 70)
        print("\nOptions:")
        print("  1. Analyze - Parse logs and show performance")
        print("  2. Cycle  - Full optimization cycle (analyze + update + build)")
        print("  3. Build  - Build and deploy strategies")
        print("  4. Status - Show optimization progress")
        print("  q. Quit")

        choice = input("\nChoice [1]: ").strip() or "1"

        if choice == "1":
            optimizer.analyze()
        elif choice == "2":
            optimizer.run_cycle()
        elif choice == "3":
            optimizer.build_and_deploy()
        elif choice == "4":
            optimizer.show_status()
        elif choice.lower() == 'q':
            print("Goodbye!")
        else:
            print("Invalid choice")

    elif args.command == "analyze":
        optimizer.analyze()

    elif args.command == "cycle":
        optimizer.run_cycle(restart=args.restart)

    elif args.command == "build":
        optimizer.build_and_deploy(restart=args.restart)

    elif args.command == "restart":
        optimizer.restart_motivewave()

    elif args.command == "status":
        optimizer.show_status()


if __name__ == "__main__":
    main()
