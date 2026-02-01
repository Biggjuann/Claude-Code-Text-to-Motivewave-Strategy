#!/usr/bin/env python3
"""
MW Study Validator

Validates generated MotiveWave studies and strategies for common issues.
Can be run standalone or integrated into the build process.

Usage:
    python validate.py                    # Validate all Java files
    python validate.py MyStudy.java       # Validate specific file
    python validate.py --jar build/libs/MWGeneratedStudies-0.1.0.jar
"""

import argparse
import re
import sys
import zipfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SRC_DIR = PROJECT_ROOT / "src" / "main" / "java"


@dataclass
class ValidationResult:
    """Result of validating a single file."""
    file_path: Path
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    def add_error(self, msg: str, line: int = None):
        prefix = f"Line {line}: " if line else ""
        self.errors.append(f"{prefix}{msg}")

    def add_warning(self, msg: str, line: int = None):
        prefix = f"Line {line}: " if line else ""
        self.warnings.append(f"{prefix}{msg}")

    def add_info(self, msg: str):
        self.info.append(msg)


class StudyValidator:
    """Validates MotiveWave study/strategy Java files."""

    # Required patterns for studies
    REQUIRED_PATTERNS = {
        'package': r'^package\s+[\w.]+;',
        'study_header': r'@StudyHeader\s*\(',
        'extends_study': r'extends\s+Study\b',
        'initialize_method': r'public\s+void\s+initialize\s*\(\s*Defaults',
        'calculate_method': r'protected\s+void\s+calculate\s*\(\s*int\s+\w+\s*,\s*DataContext',
    }

    # Additional required patterns for strategies
    STRATEGY_PATTERNS = {
        'strategy_true': r'strategy\s*=\s*true',
        'on_signal': r'public\s+void\s+onSignal\s*\(\s*OrderContext',
    }

    # Dangerous patterns to warn about
    WARNING_PATTERNS = {
        'system_out': (r'System\.out\.print', "Use debug() instead of System.out"),
        'system_err': (r'System\.err\.print', "Use debug() instead of System.err"),
        'thread_sleep': (r'Thread\.sleep', "Avoid Thread.sleep in studies"),
        'infinite_loop': (r'while\s*\(\s*true\s*\)', "Potential infinite loop"),
    }

    # Common mistakes
    MISTAKE_PATTERNS = {
        'wrong_data_context': (
            r'OrderContext\s+\w+\)[\s\S]*?\.getDataSeries\(\)',
            "Use ctx.getDataContext().getDataSeries() in OrderContext methods"
        ),
        'missing_null_check': (
            r'series\.(sma|ema|ma|atr)\([^)]+\)\s*[;.]',
            "MA/ATR results can be null - add null check"
        ),
    }

    def validate_file(self, file_path: Path) -> ValidationResult:
        """Validate a single Java file."""
        result = ValidationResult(file_path)

        if not file_path.exists():
            result.add_error(f"File not found: {file_path}")
            return result

        content = file_path.read_text(encoding='utf-8')
        lines = content.split('\n')

        # Check required patterns
        self._check_required_patterns(content, result)

        # Check if it's a strategy
        is_strategy = bool(re.search(r'strategy\s*=\s*true', content))
        if is_strategy:
            self._check_strategy_patterns(content, result)
            result.add_info("Detected as STRATEGY")
        else:
            result.add_info("Detected as STUDY")

        # Check for warnings
        self._check_warning_patterns(content, lines, result)

        # Check for common mistakes
        self._check_mistake_patterns(content, result)

        # Check JavaDoc
        self._check_javadoc(content, result)

        # Check Values enum
        self._check_values_enum(content, result)

        # Check signal declaration consistency
        if is_strategy:
            self._check_signals(content, result)

        return result

    def _check_required_patterns(self, content: str, result: ValidationResult):
        """Check for required code patterns."""
        for name, pattern in self.REQUIRED_PATTERNS.items():
            if not re.search(pattern, content, re.MULTILINE):
                result.add_error(f"Missing required pattern: {name}")

    def _check_strategy_patterns(self, content: str, result: ValidationResult):
        """Check strategy-specific patterns."""
        for name, pattern in self.STRATEGY_PATTERNS.items():
            if not re.search(pattern, content, re.MULTILINE):
                result.add_error(f"Strategy missing required pattern: {name}")

        # Check for onActivate and onDeactivate (warnings, not errors)
        if not re.search(r'public\s+void\s+onActivate', content):
            result.add_warning("Strategy should implement onActivate()")
        if not re.search(r'public\s+void\s+onDeactivate', content):
            result.add_warning("Strategy should implement onDeactivate()")

    def _check_warning_patterns(self, content: str, lines: List[str], result: ValidationResult):
        """Check for patterns that warrant warnings."""
        for name, (pattern, message) in self.WARNING_PATTERNS.items():
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line):
                    result.add_warning(message, line=i)

    def _check_mistake_patterns(self, content: str, result: ValidationResult):
        """Check for common coding mistakes."""
        # Note: These are informational, not errors
        for name, (pattern, message) in self.MISTAKE_PATTERNS.items():
            if re.search(pattern, content, re.DOTALL):
                result.add_warning(message)

    def _check_javadoc(self, content: str, result: ValidationResult):
        """Check for proper JavaDoc documentation."""
        # Check for class-level JavaDoc
        if not re.search(r'/\*\*[\s\S]*?\*/\s*@StudyHeader', content):
            result.add_warning("Missing JavaDoc before @StudyHeader")
        else:
            # Check for required JavaDoc sections
            javadoc_match = re.search(r'/\*\*([\s\S]*?)\*/', content)
            if javadoc_match:
                javadoc = javadoc_match.group(1)
                if 'INPUTS' not in javadoc:
                    result.add_warning("JavaDoc missing INPUTS section")
                if 'OUTPUTS' not in javadoc and 'PLOTS' not in javadoc:
                    result.add_warning("JavaDoc missing OUTPUTS/PLOTS section")

    def _check_values_enum(self, content: str, result: ValidationResult):
        """Check Values enum consistency."""
        # Extract Values enum members
        values_match = re.search(r'enum\s+Values\s*\{([^}]+)\}', content)
        if not values_match:
            result.add_error("Missing Values enum")
            return

        values_content = values_match.group(1)
        values = [v.strip() for v in re.findall(r'(\w+)', values_content)]

        # Check if declared values are used
        for value in values:
            pattern = f'Values\\.{value}'
            if not re.search(pattern, content):
                result.add_warning(f"Values.{value} declared but never used")

    def _check_signals(self, content: str, result: ValidationResult):
        """Check signal declaration and usage consistency."""
        # Extract Signals enum members
        signals_match = re.search(r'enum\s+Signals\s*\{([^}]+)\}', content)
        if not signals_match:
            result.add_warning("Strategy should have Signals enum")
            return

        signals_content = signals_match.group(1)
        signals = [s.strip() for s in re.findall(r'(\w+)', signals_content)]

        # Check if signals are declared in runtime descriptor
        for signal in signals:
            if not re.search(f'declareSignal\\s*\\(\\s*Signals\\.{signal}', content):
                result.add_warning(f"Signal {signal} not declared in runtime descriptor")

        # Check if signals are used in onSignal
        if 'onSignal' in content:
            for signal in signals:
                if not re.search(f'signal\\s*==\\s*Signals\\.{signal}', content):
                    result.add_warning(f"Signal {signal} not handled in onSignal()")


class JarValidator:
    """Validates a built JAR file."""

    def validate_jar(self, jar_path: Path) -> ValidationResult:
        """Validate a JAR file."""
        result = ValidationResult(jar_path)

        if not jar_path.exists():
            result.add_error(f"JAR not found: {jar_path}")
            return result

        try:
            with zipfile.ZipFile(jar_path, 'r') as zf:
                names = zf.namelist()

                # Check for class files
                class_files = [n for n in names if n.endswith('.class')]
                if not class_files:
                    result.add_error("No .class files in JAR")
                else:
                    result.add_info(f"Contains {len(class_files)} class files")

                # Check for properties files
                props_files = [n for n in names if n.endswith('.properties')]
                if not props_files:
                    result.add_warning("No .properties files in JAR (localization)")
                else:
                    result.add_info(f"Contains {len(props_files)} properties files")

                # Check for expected study classes
                study_classes = [n for n in class_files
                               if 'Study' in n or 'Strategy' in n]
                result.add_info(f"Study/Strategy classes: {len(study_classes)}")

                # List main classes
                main_classes = [n for n in class_files
                              if '$' not in n and n.count('/') >= 3]
                for cls in main_classes[:10]:  # Limit output
                    result.add_info(f"  - {cls}")

        except zipfile.BadZipFile:
            result.add_error("Invalid JAR file (not a valid ZIP)")

        return result


def validate_all_sources() -> List[ValidationResult]:
    """Validate all Java source files."""
    validator = StudyValidator()
    results = []

    java_files = list(SRC_DIR.rglob("*.java"))
    for java_file in java_files:
        # Skip package-info files
        if java_file.name == 'package-info.java':
            continue
        results.append(validator.validate_file(java_file))

    return results


def print_results(results: List[ValidationResult]):
    """Print validation results."""
    total_errors = 0
    total_warnings = 0

    for result in results:
        print(f"\n{'='*60}")
        print(f"File: {result.file_path.name}")
        print('='*60)

        # Info
        for info in result.info:
            print(f"  [INFO] {info}")

        # Warnings
        for warning in result.warnings:
            print(f"  [WARN] {warning}")
            total_warnings += 1

        # Errors
        for error in result.errors:
            print(f"  [ERROR] {error}")
            total_errors += 1

        if result.is_valid:
            print("  [OK] Validation passed")
        else:
            print("  [FAIL] Validation failed")

    print(f"\n{'='*60}")
    print(f"SUMMARY: {len(results)} files, {total_errors} errors, {total_warnings} warnings")
    print('='*60)

    return total_errors == 0


def main():
    parser = argparse.ArgumentParser(description="Validate MotiveWave studies")
    parser.add_argument('files', nargs='*', help='Specific files to validate')
    parser.add_argument('--jar', help='Validate a JAR file')
    parser.add_argument('--quiet', '-q', action='store_true', help='Only show errors')

    args = parser.parse_args()

    results = []

    if args.jar:
        jar_validator = JarValidator()
        results.append(jar_validator.validate_jar(Path(args.jar)))
    elif args.files:
        validator = StudyValidator()
        for file_path in args.files:
            results.append(validator.validate_file(Path(file_path)))
    else:
        results = validate_all_sources()

    success = print_results(results)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
