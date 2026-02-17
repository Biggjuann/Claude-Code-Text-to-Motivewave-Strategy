"""Unit tests for contract_roller.py — CME futures auto-roll logic."""

import sys
import unittest
from datetime import date

# Ensure contract_roller is importable from this directory
sys.path.insert(0, ".")

from contract_roller import (
    _expiration_date,
    check_roll_needed,
    next_roll_date,
    parse_symbol,
    resolve_front_month,
)


class TestExpirationDate(unittest.TestCase):
    """Test 3rd Friday calculation."""

    def test_march_2026(self):
        # March 2026: 1st is Sunday → 1st Friday is Mar 6 → 3rd Friday is Mar 20
        self.assertEqual(_expiration_date(2026, 3), date(2026, 3, 20))

    def test_june_2026(self):
        # June 2026: 1st is Monday → 1st Friday is Jun 5 → 3rd Friday is Jun 19
        self.assertEqual(_expiration_date(2026, 6), date(2026, 6, 19))

    def test_september_2026(self):
        # September 2026: 1st is Tuesday → 1st Friday is Sep 4 → 3rd Friday is Sep 18
        self.assertEqual(_expiration_date(2026, 9), date(2026, 9, 18))

    def test_december_2026(self):
        # December 2026: 1st is Tuesday → 1st Friday is Dec 4 → 3rd Friday is Dec 18
        self.assertEqual(_expiration_date(2026, 12), date(2026, 12, 18))


class TestParseSymbol(unittest.TestCase):
    """Test futures symbol parsing."""

    def test_es_h6(self):
        root, code, year = parse_symbol("ESH6")
        self.assertEqual(root, "ES")
        self.assertEqual(code, "H")
        self.assertEqual(year, 2026)

    def test_mes_h6(self):
        root, code, year = parse_symbol("MESH6")
        self.assertEqual(root, "MES")
        self.assertEqual(code, "H")
        self.assertEqual(year, 2026)

    def test_nq_z7(self):
        root, code, year = parse_symbol("NQZ7")
        self.assertEqual(root, "NQ")
        self.assertEqual(code, "Z")
        self.assertEqual(year, 2027)

    def test_lowercase(self):
        root, code, year = parse_symbol("esh6")
        self.assertEqual(root, "ES")
        self.assertEqual(code, "H")

    def test_invalid_raises(self):
        with self.assertRaises(ValueError):
            parse_symbol("INVALID")

    def test_4char_root(self):
        root, code, year = parse_symbol("MNQM6")
        self.assertEqual(root, "MNQ")
        self.assertEqual(code, "M")
        self.assertEqual(year, 2026)


class TestResolveFrontMonth(unittest.TestCase):
    """Test front-month contract resolution."""

    def test_early_feb_before_roll(self):
        # Feb 16, 2026 — well before H6 roll window (Mar 12)
        result = resolve_front_month("ES", date(2026, 2, 16))
        self.assertEqual(result, "ESH6")

    def test_inside_roll_window(self):
        # Mar 12, 2026 — exactly 8 days before Mar 20 expiry → should roll to M6
        result = resolve_front_month("ES", date(2026, 3, 12))
        self.assertEqual(result, "ESM6")

    def test_just_before_roll(self):
        # Mar 11, 2026 — 9 days before Mar 20 → still H6
        result = resolve_front_month("ES", date(2026, 3, 11))
        self.assertEqual(result, "ESH6")

    def test_mes_root_before_roll(self):
        # June 1 is before June roll window (Jun 11) → still M6
        result = resolve_front_month("MES", date(2026, 6, 1))
        self.assertEqual(result, "MESM6")

    def test_mes_root_in_roll_window(self):
        # June 11 is inside roll window (Jun 19 - 8) → U6
        result = resolve_front_month("MES", date(2026, 6, 11))
        self.assertEqual(result, "MESU6")

    def test_nq_september(self):
        result = resolve_front_month("NQ", date(2026, 7, 1))
        self.assertEqual(result, "NQU6")

    def test_year_rollover(self):
        # Dec 10, 2026 — 8 days before Dec 18 expiry → roll to H7
        result = resolve_front_month("ES", date(2026, 12, 10))
        self.assertEqual(result, "ESH7")

    def test_early_december(self):
        # Dec 1, 2026 — before roll window → still Z6
        result = resolve_front_month("ES", date(2026, 12, 1))
        self.assertEqual(result, "ESZ6")

    def test_custom_roll_days(self):
        # With 15-day roll window: Mar 5 is 15 days before Mar 20 → roll to M6
        result = resolve_front_month("ES", date(2026, 3, 5), roll_days=15)
        self.assertEqual(result, "ESM6")

        # With 5-day roll window: Mar 14 is 6 days before → still H6
        result = resolve_front_month("ES", date(2026, 3, 14), roll_days=5)
        self.assertEqual(result, "ESH6")

        # Mar 15 is 5 days before → roll to M6
        result = resolve_front_month("ES", date(2026, 3, 15), roll_days=5)
        self.assertEqual(result, "ESM6")


class TestNextRollDate(unittest.TestCase):
    """Test next roll date calculation."""

    def test_next_roll_from_feb(self):
        # From Feb 16 — next roll is Mar 12 (Mar 20 expiry - 8 days)
        result = next_roll_date("ES", date(2026, 2, 16))
        self.assertEqual(result, date(2026, 3, 12))

    def test_next_roll_after_march_roll(self):
        # From Mar 13 (already rolled to M6) — next roll is Jun 11 (Jun 19 - 8)
        result = next_roll_date("ES", date(2026, 3, 13))
        self.assertEqual(result, date(2026, 6, 11))


class TestCheckRollNeeded(unittest.TestCase):
    """Test roll-needed detection."""

    def test_no_roll_needed(self):
        should_roll, new_sym = check_roll_needed("ESH6", "ES", date(2026, 2, 16))
        self.assertFalse(should_roll)
        self.assertEqual(new_sym, "ESH6")

    def test_roll_needed(self):
        should_roll, new_sym = check_roll_needed("ESH6", "ES", date(2026, 3, 12))
        self.assertTrue(should_roll)
        self.assertEqual(new_sym, "ESM6")

    def test_already_rolled(self):
        should_roll, new_sym = check_roll_needed("ESM6", "ES", date(2026, 3, 15))
        self.assertFalse(should_roll)
        self.assertEqual(new_sym, "ESM6")

    def test_idempotent(self):
        # Calling multiple times returns the same result
        for _ in range(3):
            should_roll, new_sym = check_roll_needed("ESH6", "ES", date(2026, 3, 12))
            self.assertTrue(should_roll)
            self.assertEqual(new_sym, "ESM6")


if __name__ == "__main__":
    unittest.main()
