import csv
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from scripts import kline_features


def make_rows(count=65, start=100.0, step=1.0, volume=1000):
    rows = []
    base = date(2026, 1, 1)
    for index in range(count):
        close = start + index * step
        open_ = close - 0.5
        high = close + 1
        low = close - 1
        rows.append({
            "date": (base + timedelta(days=index)).isoformat(),
            "open": round(open_, 4),
            "high": round(high, 4),
            "low": round(low, 4),
            "close": round(close, 4),
            "volume": volume + index * 10,
            "amount": 1000000 + index,
        })
    return rows


class KLineFeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write_json(self, name, data):
        path = self.root / name
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def write_csv(self, name, rows):
        path = self.root / name
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_json_list_and_calculations(self):
        path = self.write_json("stock.json", make_rows(65))
        result = kline_features.calculate_features(path, adjustment="forward")
        self.assertEqual(result["as_of_date"], "2026-03-06")
        self.assertEqual(result["adjustment"], "forward")
        self.assertAlmostEqual(result["returns"]["return_1d"], 1 / 163, places=6)
        self.assertAlmostEqual(result["moving_averages"]["ma5"], 162.0, places=6)
        self.assertEqual(result["trend"]["state"], "strong_uptrend")
        self.assertIn(result["structural_summary"]["classification"], {"constructive", "slightly_constructive"})

    def test_json_object_wrappers_and_chinese_fields(self):
        rows = [
            {"日期": "20260101", "开盘价": 10, "最高价": 11, "最低价": 9, "收盘价": 10, "成交量": 100},
            {"日期": "2026/01/02", "开盘价": 10, "最高价": 12, "最低价": 10, "收盘价": 11, "成交量": 120},
            {"日期": "2026-01-03 15:00:00", "开盘价": 11, "最高价": 13, "最低价": 10, "收盘价": 12, "成交量": 130},
            {"日期": "2026-01-04", "开盘价": 12, "最高价": 14, "最低价": 11, "收盘价": 13, "成交量": 140},
            {"日期": "2026-01-05", "开盘价": 13, "最高价": 15, "最低价": 12, "收盘价": 14, "成交量": 150},
        ]
        path = self.write_json("wrapped.json", {"data": rows})
        result = kline_features.calculate_features(path)
        self.assertEqual(result["data_quality"]["valid_rows"], 5)
        self.assertEqual(result["as_of_date"], "2026-01-05")

    def test_csv_reversed_input_duplicate_dates_and_bad_rows(self):
        rows = [
            {"date": "2026-01-03", "open": "12", "high": "13", "low": "11", "close": "12", "volume": "120"},
            {"date": "2026-01-02", "open": "11", "high": "12", "low": "10", "close": "11", "volume": "110"},
            {"date": "2026-01-02", "open": "11", "high": "12.5", "low": "10", "close": "11.5", "volume": "115"},
            {"date": "bad", "open": "x", "high": "12", "low": "10", "close": "11", "volume": "110"},
            {"date": "2026-01-01", "open": "10", "high": "11", "low": "9", "close": "10", "volume": "100"},
            {"date": "2026-01-04", "open": "12", "high": "10", "low": "11", "close": "12", "volume": "130"},
        ]
        path = self.write_csv("stock.csv", rows)
        result = kline_features.calculate_features(path)
        self.assertEqual(result["data_quality"]["duplicate_dates"], ["2026-01-02"])
        self.assertGreater(result["data_quality"]["chronological_corrections"], 0)
        self.assertEqual(result["data_quality"]["rows_skipped"], 2)

    def test_zero_range_candle_is_safe(self):
        rows = make_rows(4)
        rows.append({"date": "2026-01-05", "open": 10, "high": 10, "low": 10, "close": 10, "volume": 100})
        path = self.write_json("zero.json", rows)
        result = kline_features.calculate_features(path)
        self.assertEqual(result["latest_candle"]["close_zone"], "zero_range")
        self.assertIsNone(result["latest_candle"]["close_location"])

    def test_missing_volume_not_converted_from_amount(self):
        rows = make_rows(25)
        for row in rows:
            row.pop("volume")
            row["turnover_rate"] = 2.5
        path = self.write_json("novol.json", rows)
        result = kline_features.calculate_features(path)
        self.assertEqual(result["volume"]["state"], "insufficient_data")
        self.assertEqual(result["data_quality"]["missing_volume_count"], 25)

    def test_insufficient_data_behavior(self):
        path = self.write_json("short.json", make_rows(4))
        result = kline_features.calculate_features(path)
        self.assertEqual(result["data_quality"]["status"], "insufficient")
        self.assertEqual(result["trend"]["state"], "insufficient_data")
        self.assertIsNone(result["returns"]["return_5d"])

    def test_candle_shadow_and_close_location(self):
        rows = make_rows(5)
        rows[-1].update({"open": 10, "high": 20, "low": 0.1, "close": 18, "volume": 1000})
        path = self.write_json("candle.json", rows)
        result = kline_features.calculate_features(path)
        self.assertEqual(result["latest_candle"]["close_zone"], "near_high")
        self.assertGreater(result["latest_candle"]["upper_shadow_ratio"], 0)
        self.assertGreater(result["latest_candle"]["lower_shadow_ratio"], 0)

    def test_volume_ratios_exclude_latest_day_and_percentile(self):
        rows = make_rows(65, step=0.2, volume=100)
        for row in rows[:-1]:
            row["volume"] = 100
        rows[-1]["volume"] = 200
        path = self.write_json("vol.json", rows)
        result = kline_features.calculate_features(path)
        self.assertEqual(result["volume"]["ratio_vs_prior_5d"], 2.0)
        self.assertEqual(result["volume"]["ratio_vs_prior_20d"], 2.0)
        self.assertEqual(result["volume"]["percentile_60d"], 1.0)
        self.assertEqual(result["volume"]["state"], "high")

    def test_range_breakout_breakdown_and_failed_breakout(self):
        rows = make_rows(25, start=100, step=0)
        for row in rows[:-1]:
            row.update({"high": 105, "low": 95, "close": 100})
        rows[-1].update({"open": 104, "high": 110, "low": 99, "close": 106})
        breakout = kline_features.calculate_features(self.write_json("breakout.json", rows))
        self.assertEqual(breakout["range_structure"]["state"], "close_breakout")

        rows[-1].update({"open": 96, "high": 101, "low": 90, "close": 94})
        breakdown = kline_features.calculate_features(self.write_json("breakdown.json", rows))
        self.assertEqual(breakdown["range_structure"]["state"], "close_breakdown")

        rows[-1].update({"open": 101, "high": 110, "low": 99, "close": 100})
        failed = kline_features.calculate_features(self.write_json("failed.json", rows))
        self.assertEqual(failed["range_structure"]["state"], "intraday_failed_breakout")

    def test_sequences_and_ma20_reclaim_breakdown(self):
        rows = make_rows(25, start=100, step=0)
        for row in rows[-4:-1]:
            row.update({"open": 80, "high": 82, "low": 78, "close": 80})
        rows[-1].update({"open": 104, "high": 106, "low": 103, "close": 105})
        result = kline_features.calculate_features(self.write_json("seq.json", rows))
        self.assertGreaterEqual(result["sequence"]["consecutive_up_days"], 1)
        self.assertTrue(result["sequence"]["first_close_above_ma20_after_3_below"])

    def test_true_range_atr_volatility_and_abnormal_move(self):
        rows = make_rows(65, start=100, step=0.1)
        rows[-1].update({"open": 106, "high": 140, "low": 105, "close": 135})
        path = self.write_json("volatility.json", rows)
        result = kline_features.calculate_features(path)
        self.assertIsNotNone(result["volatility"]["return_volatility_20d"])
        self.assertIsNotNone(result["volatility"]["atr14"])
        self.assertIn(result["volatility"]["abnormal_move"], {"absolute_return_unusually_high", "true_range_unusually_high", "both"})

    def test_upward_and_downward_gaps(self):
        rows = make_rows(10, start=100, step=0)
        rows[-2].update({"high": 101, "low": 99, "close": 100})
        rows[-1].update({"open": 104, "high": 106, "low": 103, "close": 105})
        up = kline_features.calculate_features(self.write_json("gapup.json", rows))
        self.assertEqual(up["gap"]["type"], "full_upward_gap")

        rows[-1].update({"open": 96, "high": 97, "low": 94, "close": 96})
        down = kline_features.calculate_features(self.write_json("gapdown.json", rows))
        self.assertEqual(down["gap"]["type"], "full_downward_gap")

    def test_relative_strength_on_aligned_dates(self):
        stock = make_rows(30, start=100, step=1)
        benchmark = make_rows(30, start=100, step=0.5)
        stock_path = self.write_json("stock.json", stock)
        benchmark_path = self.write_json("benchmark.json", benchmark)
        result = kline_features.calculate_features(stock_path, benchmark=benchmark_path)
        self.assertEqual(result["relative_strength"]["benchmark"]["common_observations"], 30)
        self.assertGreater(result["relative_strength"]["benchmark"]["return_5d_difference"], 0)

    def test_output_has_no_prediction_or_recommendation_terms_and_no_paths(self):
        path = self.write_json("stock.json", make_rows(25))
        result = kline_features.calculate_features(path)
        encoded = json.dumps(result, ensure_ascii=False)
        for forbidden in ("buy", "sell", "target_price", "tomorrow", str(self.root)):
            self.assertNotIn(forbidden, encoded)
        json.loads(encoded)


if __name__ == "__main__":
    unittest.main()
