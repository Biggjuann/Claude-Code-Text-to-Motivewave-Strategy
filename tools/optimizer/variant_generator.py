"""
Strategy Variant Generator
Creates modified versions of strategies with different parameter settings for A/B testing.
"""

import os
import re
import json
import shutil
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime


class VariantGenerator:
    """Generates strategy variants with modified default parameters."""

    def __init__(self, source_dir: str):
        self.source_dir = Path(source_dir)
        self.strategies_dir = self.source_dir / "src" / "main" / "java" / "com" / "mw" / "studies"

    def read_strategy(self, strategy_file: str) -> str:
        """Read the source code of a strategy."""
        path = self.strategies_dir / strategy_file
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()

    def get_current_defaults(self, source: str) -> Dict:
        """Extract current default parameter values from source code."""
        defaults = {}

        # Pattern for IntegerDescriptor: new IntegerDescriptor(KEY, "Label", DEFAULT, min, max, step)
        int_pattern = re.compile(
            r'new IntegerDescriptor\(\s*([A-Z_]+)\s*,\s*"[^"]+"\s*,\s*(\d+)'
        )
        for match in int_pattern.finditer(source):
            key = match.group(1)
            value = int(match.group(2))
            defaults[key] = {"type": "int", "value": value}

        # Pattern for DoubleDescriptor
        double_pattern = re.compile(
            r'new DoubleDescriptor\(\s*([A-Z_]+)\s*,\s*"[^"]+"\s*,\s*([\d.]+)'
        )
        for match in double_pattern.finditer(source):
            key = match.group(1)
            value = float(match.group(2))
            defaults[key] = {"type": "double", "value": value}

        # Pattern for BooleanDescriptor
        bool_pattern = re.compile(
            r'new BooleanDescriptor\(\s*([A-Z_]+)\s*,\s*"[^"]+"\s*,\s*(true|false)'
        )
        for match in bool_pattern.finditer(source):
            key = match.group(1)
            value = match.group(2) == "true"
            defaults[key] = {"type": "bool", "value": value}

        return defaults

    def modify_defaults(self, source: str, changes: Dict) -> str:
        """Modify default values in the source code."""
        modified = source

        for param, new_value in changes.items():
            # Integer parameters
            int_pattern = re.compile(
                rf'(new IntegerDescriptor\(\s*{param}\s*,\s*"[^"]+"\s*,\s*)(\d+)'
            )
            if int_pattern.search(modified):
                modified = int_pattern.sub(rf'\g<1>{int(new_value)}', modified)
                continue

            # Double parameters
            double_pattern = re.compile(
                rf'(new DoubleDescriptor\(\s*{param}\s*,\s*"[^"]+"\s*,\s*)([\d.]+)'
            )
            if double_pattern.search(modified):
                modified = double_pattern.sub(rf'\g<1>{float(new_value)}', modified)
                continue

            # Boolean parameters
            bool_pattern = re.compile(
                rf'(new BooleanDescriptor\(\s*{param}\s*,\s*"[^"]+"\s*,\s*)(true|false)'
            )
            if bool_pattern.search(modified):
                bool_val = "true" if new_value else "false"
                modified = bool_pattern.sub(rf'\g<1>{bool_val}', modified)

        return modified

    def decouple_position_tracking(self, source: str) -> str:
        """
        Modify strategy to use internal position tracking instead of shared account position.
        This allows multiple variants to run simultaneously on the same chart without interfering.

        Changes made:
        1. Add 'private int myPosition = 0;' to trade state variables
        2. Add 'myPosition = 0;' to resetTradeState()
        3. Replace 'int position = ctx.getPosition();' with 'int position = myPosition;'
        4. Add 'myPosition = contracts;' after ctx.buy()
        5. Add 'myPosition -= halfQty;' after partial sells
        6. Remove external position close check
        """
        modified = source

        # 1. Add myPosition to trade state
        modified = re.sub(
            r'(private int lastResetDay = -1;)',
            r'\1\n\n    // Decoupled position tracking (for running multiple variants simultaneously)\n    private int myPosition = 0;',
            modified
        )

        # 2. Add myPosition reset
        modified = re.sub(
            r'(tp2Price = 0\.0;\s*\n\s*\})',
            r'tp2Price = 0.0;\n        myPosition = 0;\n    }',
            modified
        )

        # 3. Replace ctx.getPosition() with myPosition in onBarUpdate
        modified = re.sub(
            r'int position = ctx\.getPosition\(\);(\s*\n\s*// Time checks)',
            r'// Use internal position tracking (decoupled from account)\n        int position = myPosition;\1',
            modified
        )

        # 4. Replace ctx.getPosition() in manageExistingTrade
        modified = re.sub(
            r'(double close = series\.getClose\(index\);\s*\n\s*)int position = ctx\.getPosition\(\);',
            r'\1int position = myPosition;  // Use internal position tracking',
            modified
        )

        # 5. Add myPosition = contracts after buy
        modified = re.sub(
            r'(ctx\.buy\(contracts\);\s*\n\s*inTrade = true;)',
            r'ctx.buy(contracts);\n\n                inTrade = true;\n                myPosition = contracts;  // Track our own position',
            modified
        )
        # Clean up if double inTrade
        modified = re.sub(r'inTrade = true;\s*\n\s*inTrade = true;', 'inTrade = true;', modified)

        # 6. Add myPosition decrement after partial sell
        modified = re.sub(
            r'(ctx\.sell\(halfQty\);)\s*(\n\s*\}\s*\n\s*\}\s*\n\s*partialTaken = true;)',
            r'\1\n                    myPosition -= halfQty;  // Update internal position\2',
            modified
        )

        # 7. Remove external position check
        modified = re.sub(
            r'// Check if position closed externally\s*\n\s*if \(ctx\.getPosition\(\) == 0\) \{\s*\n\s*info\("Position closed externally"\);\s*\n\s*resetTradeState\(\);\s*\n\s*\}',
            '// Note: With decoupled position tracking, we manage our own state\n        // No need to check ctx.getPosition() for external closes',
            modified
        )

        return modified

    def create_variant(
        self,
        base_strategy: str,
        variant_name: str,
        param_changes: Dict,
        description: str = "",
        decouple_position: bool = True
    ) -> str:
        """
        Create a new strategy variant with modified parameters.

        Args:
            base_strategy: Filename of the base strategy (e.g., "MagicLineStrategy.java")
            variant_name: Name for the variant (will be appended, e.g., "MagicLineStrategy_v2.java")
            param_changes: Dict of parameter name -> new value
            description: Optional description of changes
            decouple_position: If True, modify to use internal position tracking (allows
                               running multiple variants simultaneously on same chart)

        Returns:
            Path to the created variant file
        """
        # Read base strategy
        source = self.read_strategy(base_strategy)

        # Modify defaults
        modified = self.modify_defaults(source, param_changes)

        # Decouple position tracking for A/B testing (run multiple variants simultaneously)
        if decouple_position:
            modified = self.decouple_position_tracking(modified)

        # Update class name and ID
        base_name = base_strategy.replace(".java", "")
        new_class_name = f"{base_name}_{variant_name}"

        # Update class declaration
        modified = re.sub(
            rf'public class {base_name}',
            f'public class {new_class_name}',
            modified
        )

        # Update study ID to avoid conflicts
        modified = re.sub(
            r'id = "([^"]+)"',
            f'id = "\\1_{variant_name.upper()}"',
            modified
        )

        # Update study name/label to distinguish in menu
        modified = re.sub(
            r'name = "([^"]+)"',
            f'name = "\\1_{variant_name.upper()}"',
            modified
        )

        # Add variant info comment
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        variant_header = f"""
/**
 * VARIANT: {variant_name}
 * Generated: {timestamp}
 * Base: {base_strategy}
 * Changes: {json.dumps(param_changes)}
 * Description: {description}
 */
"""
        # Insert after package declaration
        modified = re.sub(
            r'(package [^;]+;)',
            f'\\1\n{variant_header}',
            modified
        )

        # Write variant file
        variant_filename = f"{new_class_name}.java"
        variant_path = self.strategies_dir / variant_filename

        with open(variant_path, 'w', encoding='utf-8') as f:
            f.write(modified)

        return str(variant_path)

    def create_ab_test_set(
        self,
        base_strategy: str,
        test_param: str,
        test_values: List,
        description: str = ""
    ) -> List[str]:
        """
        Create a set of variants for A/B testing a single parameter.

        Args:
            base_strategy: Base strategy filename
            test_param: Parameter to test
            test_values: List of values to test
            description: Test description

        Returns:
            List of created variant file paths
        """
        variants = []

        for i, value in enumerate(test_values):
            variant_name = f"test_{test_param.lower()}_{i+1}"
            changes = {test_param: value}
            desc = f"Testing {test_param}={value}. {description}"

            path = self.create_variant(base_strategy, variant_name, changes, desc)
            variants.append(path)
            print(f"Created: {Path(path).name} with {test_param}={value}")

        return variants

    def generate_optimization_variants(
        self,
        base_strategy: str,
        recommendations: List[Dict]
    ) -> List[str]:
        """
        Generate variants based on optimization recommendations.

        Args:
            base_strategy: Base strategy filename
            recommendations: List of recommendation dicts from analyzer

        Returns:
            List of created variant file paths
        """
        all_variants = []
        variant_num = 1

        for rec in recommendations:
            if rec.get("priority") not in ("HIGH", "MEDIUM"):
                continue

            param = rec.get("param")
            test_values = rec.get("test_values", [])

            if not param or not test_values:
                continue

            # Handle compound params like "TP1_R / TP2_R"
            if "/" in str(param):
                # Skip compound params for now - would need special handling
                continue

            for value in test_values[:3]:  # Limit to 3 variants per param
                variant_name = f"opt_v{variant_num}"
                changes = {param: value}
                desc = rec.get("reason", "Optimization variant")

                try:
                    path = self.create_variant(base_strategy, variant_name, changes, desc)
                    all_variants.append(path)
                    print(f"Created variant {variant_num}: {param}={value}")
                    variant_num += 1
                except Exception as e:
                    print(f"Error creating variant for {param}={value}: {e}")

        return all_variants


def create_comparison_report(variants: List[str], results: Dict[str, Dict]) -> str:
    """
    Create an A/B comparison report after testing variants.

    Args:
        variants: List of variant file paths
        results: Dict mapping variant name to performance metrics

    Returns:
        Formatted comparison report
    """
    report = []
    report.append("=" * 70)
    report.append("A/B TEST COMPARISON REPORT")
    report.append("=" * 70)

    # Sort by total P&L
    sorted_results = sorted(
        results.items(),
        key=lambda x: x[1].get("total_pnl", 0),
        reverse=True
    )

    report.append(f"\n{'Variant':<30} {'P&L':>10} {'Win%':>8} {'PF':>8} {'Trades':>8}")
    report.append("-" * 70)

    for name, metrics in sorted_results:
        pnl = metrics.get("total_pnl", 0)
        win_rate = metrics.get("win_rate", 0)
        pf = metrics.get("profit_factor", 0)
        trades = metrics.get("total_trades", 0)

        report.append(f"{name:<30} {pnl:>+10.2f} {win_rate:>7.1f}% {pf:>8.2f} {trades:>8}")

    report.append("-" * 70)

    # Winner
    if sorted_results:
        winner = sorted_results[0]
        report.append(f"\nBEST PERFORMER: {winner[0]}")
        report.append(f"  Total P&L: {winner[1].get('total_pnl', 0):+.2f} points")

    return "\n".join(report)


if __name__ == "__main__":
    import sys

    # Default project directory
    project_dir = r"C:\Users\jung_\OneDrive\Claude Code Text to Motivewave Strategy"

    generator = VariantGenerator(project_dir)

    # Example: Read current Magic Line defaults
    source = generator.read_strategy("MagicLineStrategy.java")
    defaults = generator.get_current_defaults(source)

    print("Current Magic Line Strategy Defaults:")
    print("-" * 50)
    for key, info in sorted(defaults.items()):
        print(f"  {key}: {info['value']} ({info['type']})")

    print("\n" + "=" * 50)
    print("VARIANT GENERATOR READY")
    print("=" * 50)
    print("\nUsage examples:")
    print("  1. Create single variant:")
    print('     generator.create_variant("MagicLineStrategy.java", "wide_stops", {"STOP_BUFFER_TICKS": 30})')
    print("\n  2. Create A/B test set:")
    print('     generator.create_ab_test_set("MagicLineStrategy.java", "STOP_BUFFER_TICKS", [20, 25, 30, 35])')
    print("\n  3. Generate from recommendations:")
    print('     generator.generate_optimization_variants("MagicLineStrategy.java", recommendations)')
