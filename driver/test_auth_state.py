import ast
import unittest
from pathlib import Path

from driver.auth_state import get_expiry_timestamp, is_expired


class AuthStateTest(unittest.TestCase):
    def test_timestamp_wins_over_stale_remaining_seconds(self):
        expiry = {
            "expiry_timestamp": 100.0,
            "remaining_seconds": 999999,
            "expiry_time": "1970-01-01 00:01:40",
        }

        self.assertTrue(is_expired(expiry, now=101.0))

    def test_future_timestamp_is_valid(self):
        expiry = {
            "expiry_timestamp": "200",
            "remaining_seconds": 0,
        }

        self.assertFalse(is_expired(expiry, now=199.0))

    def test_expiry_time_is_used_when_timestamp_is_missing(self):
        expiry = {"expiry_time": "2026-07-26 15:18:24"}

        self.assertEqual(
            get_expiry_timestamp(expiry),
            get_expiry_timestamp({"expiry_timestamp": get_expiry_timestamp(expiry)}),
        )

    def test_remaining_seconds_is_only_a_legacy_fallback(self):
        self.assertTrue(is_expired({"remaining_seconds": 0}, now=1.0))
        self.assertFalse(is_expired({"remaining_seconds": 1}, now=1.0))

    def test_gather_auth_guard_runs_before_internal_try(self):
        source = (
            Path(__file__).resolve().parents[1] / "core/wx/base.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(source)
        wx_gather = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef) and node.name == "WxGather"
        )
        start = next(
            node for node in wx_gather.body
            if isinstance(node, ast.FunctionDef) and node.name == "Start"
        )

        self.assertIsInstance(start.body[0], ast.If)
        self.assertEqual(ast.unparse(start.body[0].test), "not CanGetToken()")
        self.assertIsInstance(start.body[1], ast.Try)


if __name__ == "__main__":
    unittest.main()
