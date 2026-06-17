import csv
import json
import tempfile
import unittest
from pathlib import Path

from scripts import correlation


class CorrelationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_json(self, name, rows):
        path = self.root / name
        path.write_text(json.dumps(rows), encoding="utf-8")
        return path

    def write_csv(self, name, rows):
        path = self.root / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_normal_aligned_return_series(self):
        a = self.write_json("a.json", [
            {"date": "2026-01-01", "close": 10},
            {"date": "2026-01-02", "close": 11},
            {"date": "2026-01-03", "close": 12},
        ])
        b = self.write_json("b.json", [
            {"date": "2026-01-01", "close": 20},
            {"date": "2026-01-02", "close": 22},
            {"date": "2026-01-03", "close": 24},
        ])
        result = correlation.calculate(a, b, min_observations=2)
        self.assertEqual(result["observations"], 2)
        self.assertEqual(result["correlation"], 1.0)

    def test_fewer_than_minimum_observations(self):
        a = self.write_json("a.json", [{"date": "20260101", "close": 10}, {"date": "20260102", "close": 11}])
        b = self.write_json("b.json", [{"date": "20260101", "close": 20}, {"date": "20260102", "close": 21}])
        result = correlation.calculate(a, b, min_observations=30)
        self.assertEqual(result["label"], "样本不足")
        self.assertIsNone(result["correlation"])

    def test_zero_variance_series(self):
        a = self.write_json("a.json", [
            {"date": "2026-01-01", "close": 10},
            {"date": "2026-01-02", "close": 10},
            {"date": "2026-01-03", "close": 10},
        ])
        b = self.write_json("b.json", [
            {"date": "2026-01-01", "close": 20},
            {"date": "2026-01-02", "close": 21},
            {"date": "2026-01-03", "close": 22},
        ])
        result = correlation.calculate(a, b, min_observations=2)
        self.assertIsNone(result["correlation"])
        self.assertEqual(result["label"], "样本不足")

    def test_duplicate_dates_are_reported(self):
        a = self.write_json("a.json", [
            {"date": "2026-01-01", "close": 10},
            {"date": "2026-01-01", "close": 10.5},
            {"date": "2026-01-02", "close": 11},
        ])
        b = self.write_json("b.json", [
            {"date": "2026-01-01", "close": 20},
            {"date": "2026-01-02", "close": 22},
        ])
        result = correlation.calculate(a, b, min_observations=1)
        self.assertEqual(result["input_diagnostics"]["duplicate_dates"]["stock_a"], ["2026-01-01"])

    def test_mixed_supported_date_formats(self):
        a = self.write_json("a.json", [
            {"date": "20260101", "close": 10},
            {"date": "2026/01/02", "close": 11},
            {"date": "2026-01-03 15:00:00", "close": 12},
        ])
        b = self.write_json("b.json", [
            {"date": "2026-01-01", "close": 20},
            {"date": "20260102", "close": 22},
            {"date": "2026/01/03", "close": 24},
        ])
        result = correlation.calculate(a, b, min_observations=2)
        self.assertEqual(result["common_start"], "2026-01-02")
        self.assertEqual(result["common_end"], "2026-01-03")

    def test_missing_and_malformed_close_values(self):
        a = self.write_json("a.json", [
            {"date": "2026-01-01", "close": 10},
            {"date": "2026-01-02", "close": ""},
            {"date": "2026-01-03", "close": "bad"},
        ])
        b = self.write_json("b.json", [
            {"date": "2026-01-01", "close": 20},
            {"date": "2026-01-02", "close": 21},
            {"date": "2026-01-03", "close": 22},
        ])
        result = correlation.calculate(a, b, min_observations=1)
        self.assertEqual(result["input_diagnostics"]["stock_a_rows_skipped"], 2)
        self.assertEqual(result["input_diagnostics"]["stock_a_malformed_close_rows"], 2)

    def test_extreme_return_warning_behavior(self):
        a = self.write_json("a.json", [
            {"date": "2026-01-01", "close": 10},
            {"date": "2026-01-02", "close": 13},
        ])
        b = self.write_json("b.json", [
            {"date": "2026-01-01", "close": 20},
            {"date": "2026-01-02", "close": 21},
        ])
        result = correlation.calculate(a, b, min_observations=1)
        self.assertEqual(len(result["input_diagnostics"]["extreme_return_warnings"]), 1)

    def test_uses_returns_not_raw_price_levels(self):
        a = self.write_csv("a.csv", [
            {"date": "2026-01-01", "close": "10"},
            {"date": "2026-01-02", "close": "20"},
            {"date": "2026-01-03", "close": "10"},
        ])
        b = self.write_csv("b.csv", [
            {"date": "2026-01-01", "close": "100"},
            {"date": "2026-01-02", "close": "50"},
            {"date": "2026-01-03", "close": "100"},
        ])
        result = correlation.calculate(a, b, min_observations=2)
        self.assertEqual(result["correlation"], -1.0)


if __name__ == "__main__":
    unittest.main()
