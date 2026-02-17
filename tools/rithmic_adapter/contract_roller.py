"""Auto-roll contract manager for CME equity index futures.

Resolves root symbols (e.g. "ES") to front-month contracts (e.g. "ESM6")
and detects when it's time to roll to the next quarterly contract.

CME quarterly cycle: H=Mar, M=Jun, U=Sep, Z=Dec
Expiration: 3rd Friday of the contract month
Standard roll: 8 calendar days before expiration (typically 2nd Thursday)
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

# Quarterly month codes → month numbers
QUARTERLY_CODES = {"H": 3, "M": 6, "U": 9, "Z": 12}
CODE_BY_MONTH = {v: k for k, v in QUARTERLY_CODES.items()}
QUARTERLY_MONTHS = [3, 6, 9, 12]

DEFAULT_ROLL_DAYS_BEFORE = 8

# Pattern: 2-4 char root + 1 letter month code + 1 digit year
_SYMBOL_RE = re.compile(r"^([A-Z]{2,4})([HMUZ])(\d)$")


def _expiration_date(year: int, month: int) -> date:
    """Return the 3rd Friday of the given month/year (CME expiration)."""
    # Find the first day of the month, then the first Friday
    first_day = date(year, month, 1)
    # weekday(): Monday=0 ... Friday=4
    days_until_friday = (4 - first_day.weekday()) % 7
    first_friday = first_day + timedelta(days=days_until_friday)
    # 3rd Friday = first Friday + 14 days
    return first_friday + timedelta(days=14)


def _next_quarterly_month(month: int) -> tuple[int, bool]:
    """Return the next quarterly month and whether it wraps to next year.

    Returns (next_month, year_rolls_over).
    """
    for qm in QUARTERLY_MONTHS:
        if qm > month:
            return qm, False
    # Wrap to March of next year
    return 3, True


def _year_code(full_year: int) -> str:
    """Convert full year to single-digit code: 2026→'6', 2030→'0'."""
    return str(full_year % 10)


def _full_year(digit: int, reference_year: int) -> int:
    """Convert single-digit year code to full year relative to reference.

    Uses the reference year's decade, biased forward (e.g. if ref=2026
    and digit=5, return 2025 only if within 2 years back, else 2035).
    """
    decade = (reference_year // 10) * 10
    candidate = decade + digit
    # If candidate is more than 2 years in the past, it's next decade
    if candidate < reference_year - 2:
        candidate += 10
    return candidate


def parse_symbol(symbol: str) -> tuple[str, str, int]:
    """Parse a futures symbol into (root, month_code, full_year).

    Examples:
        'ESH6'   → ('ES', 'H', 2026)
        'MESH6'  → ('MES', 'H', 2026)
        'NQZ7'   → ('NQ', 'Z', 2027)
    """
    m = _SYMBOL_RE.match(symbol.upper())
    if not m:
        raise ValueError(f"Cannot parse futures symbol: {symbol!r}")
    root, month_code, year_digit = m.group(1), m.group(2), int(m.group(3))
    full_year = _full_year(year_digit, date.today().year)
    return root, month_code, full_year


def resolve_front_month(root: str, as_of: date | None = None,
                        roll_days: int = DEFAULT_ROLL_DAYS_BEFORE) -> str:
    """Resolve a root symbol to the current front-month contract.

    If today is within the roll window (expiry - roll_days), the front
    month is the NEXT quarterly contract.

    Examples:
        resolve_front_month("ES", date(2026, 2, 16)) → "ESH6"
        resolve_front_month("ES", date(2026, 3, 12)) → "ESM6"
    """
    today = as_of or date.today()
    root = root.upper()

    # Find the current or next quarterly month
    for qm in QUARTERLY_MONTHS:
        if qm >= ((today.month - 1) // 3 + 1) * 3:
            # This is the current quarter's contract month
            year = today.year
            expiry = _expiration_date(year, qm)
            roll_date = expiry - timedelta(days=roll_days)

            if today < roll_date:
                # Still in this contract
                return f"{root}{CODE_BY_MONTH[qm]}{_year_code(year)}"
            else:
                # In roll window — move to next contract
                next_month, wraps = _next_quarterly_month(qm)
                next_year = year + 1 if wraps else year
                return f"{root}{CODE_BY_MONTH[next_month]}{_year_code(next_year)}"
            break
    else:
        # Past December quarterly — next is March of next year
        year = today.year
        # Check December contract of current year
        expiry = _expiration_date(year, 12)
        roll_date = expiry - timedelta(days=roll_days)

        if today < roll_date:
            return f"{root}Z{_year_code(year)}"
        else:
            return f"{root}H{_year_code(year + 1)}"


def next_roll_date(root: str, as_of: date | None = None,
                   roll_days: int = DEFAULT_ROLL_DAYS_BEFORE) -> date:
    """Return the next upcoming roll date from the given date.

    The roll date is `roll_days` calendar days before the 3rd Friday
    expiration of the current front-month contract.
    """
    today = as_of or date.today()
    current_symbol = resolve_front_month(root, today, roll_days)
    _, month_code, year = parse_symbol(current_symbol)
    month = QUARTERLY_CODES[month_code]
    expiry = _expiration_date(year, month)
    return expiry - timedelta(days=roll_days)


def check_roll_needed(current_symbol: str, root: str,
                      as_of: date | None = None,
                      roll_days: int = DEFAULT_ROLL_DAYS_BEFORE) -> tuple[bool, str]:
    """Check if the current contract should be rolled.

    Returns (should_roll, new_symbol). Safe to call repeatedly — returns
    (False, current_symbol) if no roll is needed.
    """
    today = as_of or date.today()
    expected = resolve_front_month(root, today, roll_days)

    if expected.upper() != current_symbol.upper():
        return True, expected
    return False, current_symbol
