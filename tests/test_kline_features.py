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
        self.assertIn(
            result["structural_summary"]["technical_structure"]["classification"],
            {"constructive", "slightly_constructive"},
        )

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
        self.assertEqual(result["data_quality"]["price_data_status"], "usable_with_limitations")

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
        self.assertEqual(result["data_quality"]["volume_data_status"], "insufficient")
        self.assertEqual(result["data_quality"]["status"], "usable_with_limitations")
        self.assertEqual(result["data_quality"]["raw_rows_missing_volume"], 25)
        self.assertEqual(result["data_quality"]["final_rows_missing_volume"], 25)

    def test_sparse_volume_does_not_produce_good_quality_or_volume_signals(self):
        rows = make_rows(100)
        for row in rows[:-1]:
            row.pop("volume")
        path = self.write_json("sparse_volume.json", rows)
        result = kline_features.calculate_features(path)
        self.assertEqual(result["data_quality"]["price_data_status"], "good")
        self.assertEqual(result["data_quality"]["volume_data_status"], "insufficient")
        self.assertLess(result["data_quality"]["volume_coverage_ratio"], 0.5)
        self.assertNotEqual(result["data_quality"]["status"], "good")
        self.assertEqual(result["volume"]["state"], "insufficient_data")
        self.assertIsNone(result["structural_summary"]["technical_structure"]["price_volume_score"])

    def test_duplicate_volume_coverage_uses_final_deduplicated_series(self):
        tail = []
        base = date(2026, 1, 2)
        for index in range(4):
            close = 11 + index
            tail.append({
                "date": (base + timedelta(days=index)).isoformat(),
                "open": close - 0.5,
                "high": close + 1,
                "low": close - 1,
                "close": close,
                "volume": 100 + index,
            })
        rows = [
            {"date": "2026-01-01", "open": 10, "high": 11, "low": 9, "close": 10},
            {"date": "2026-01-01", "open": 10, "high": 11, "low": 9, "close": 10},
            {"date": "2026-01-01", "open": 10, "high": 11, "low": 9, "close": 10, "volume": 100},
            *tail,
        ]
        result = kline_features.calculate_features(self.write_json("dup_kept_has_volume.json", rows))
        self.assertEqual(result["data_quality"]["valid_rows"], 5)
        self.assertEqual(result["data_quality"]["raw_rows_missing_volume"], 2)
        self.assertEqual(result["data_quality"]["final_rows_missing_volume"], 0)
        self.assertEqual(result["data_quality"]["missing_volume_count"], 0)
        self.assertEqual(result["data_quality"]["volume_coverage_ratio"], 1.0)
        self.assertEqual(result["data_quality"]["volume_data_status"], "good")
        self.assertEqual(result["data_quality"]["duplicate_dates"], ["2026-01-01"])

        rows[2].pop("volume")
        result = kline_features.calculate_features(self.write_json("dup_kept_missing_volume.json", rows))
        self.assertEqual(result["data_quality"]["final_rows_missing_volume"], 1)
        self.assertEqual(result["data_quality"]["volume_coverage_ratio"], 0.8)
        self.assertEqual(result["data_quality"]["volume_data_status"], "usable_with_limitations")

    def test_volume_coverage_ratio_is_bounded_and_thresholds_are_inclusive(self):
        for valid_count, expected_status in ((49, "insufficient"), (50, "usable_with_limitations"), (94, "usable_with_limitations"), (95, "good")):
            rows = make_rows(100)
            for row in rows[valid_count:]:
                row.pop("volume")
            result = kline_features.calculate_features(self.write_json(f"coverage_{valid_count}.json", rows))
            self.assertGreaterEqual(result["data_quality"]["volume_coverage_ratio"], 0)
            self.assertLessEqual(result["data_quality"]["volume_coverage_ratio"], 1)
            self.assertEqual(result["data_quality"]["volume_data_status"], expected_status)

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
        self.assertEqual(result["volume"]["percentile_vs_prior_60d"], 1.0)
        self.assertEqual(result["volume"]["percentile_60d"], 1.0)
        self.assertEqual(result["volume"]["state"], "high")

    def test_price_volume_score_handles_down_pullback_breakout_and_failed_breakout(self):
        rows = make_rows(65, start=100, step=0)
        for row in rows[:-1]:
            row.update({"open": 100, "high": 105, "low": 95, "close": 100, "volume": 100})

        high_volume_down = [dict(row) for row in rows]
        high_volume_down[-1].update({"open": 101, "high": 102, "low": 89, "close": 90, "volume": 400})
        result = kline_features.calculate_features(self.write_json("high_volume_down.json", high_volume_down))
        self.assertLess(result["structural_summary"]["technical_structure"]["price_volume_score"], 0)

        low_volume_pullback = [dict(row) for row in rows]
        low_volume_pullback[-1].update({"open": 101, "high": 102, "low": 98, "close": 99, "volume": 50})
        result = kline_features.calculate_features(self.write_json("low_volume_pullback.json", low_volume_pullback))
        self.assertEqual(result["structural_summary"]["technical_structure"]["price_volume_score"], 0)

        breakout = [dict(row) for row in rows]
        breakout[-1].update({"open": 104, "high": 110, "low": 103, "close": 106, "volume": 400})
        result = kline_features.calculate_features(self.write_json("breakout_volume.json", breakout))
        self.assertGreater(result["structural_summary"]["technical_structure"]["price_volume_score"], 0)

        failed = [dict(row) for row in rows]
        failed[-1].update({"open": 104, "high": 110, "low": 99, "close": 100, "volume": 400})
        result = kline_features.calculate_features(self.write_json("failed_volume.json", failed))
        self.assertLess(result["structural_summary"]["technical_structure"]["price_volume_score"], 0)

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

    def test_daily_range_percentile_observation_boundaries(self):
        for count, expected in ((59, 58), (60, 59), (61, 60)):
            result = kline_features.calculate_features(self.write_json(f"range_{count}.json", make_rows(count)))
            self.assertEqual(result["volatility"]["daily_range_percentile_observations"], expected)

    def test_previous_close_source_and_conflict_warning(self):
        rows = make_rows(10, start=100, step=0)
        rows[-1].update({"open": 100, "high": 101, "low": 99, "close": 100, "pre_close": 80})
        result = kline_features.calculate_features(self.write_json("preclose_conflict.json", rows))
        self.assertFalse(result["pre_close_policy"]["verified_for_full_series"])
        self.assertEqual(result["pre_close_policy"]["default_source"], "previous_bar_close")
        self.assertEqual(result["latest_candle"]["previous_close_source"], "previous_bar_close")
        self.assertEqual(result["gap"]["previous_close_source"], "previous_bar_close")
        self.assertIn("conflicting_pre_close_vs_previous_bar_close", result["data_quality"]["warning_counts"])

        verified = kline_features.calculate_features(
            self.write_json("preclose_verified.json", rows),
            pre_close_adjustment_verified=True,
        )
        self.assertTrue(verified["pre_close_policy"]["verified_for_full_series"])
        self.assertEqual(verified["pre_close_policy"]["default_source"], "verified_pre_close")
        self.assertEqual(verified["latest_candle"]["previous_close_source"], "verified_pre_close")

    def test_pre_close_first_row_missing_field_and_multiple_conflicts(self):
        rows = make_rows(10, start=100, step=0)
        rows[0].pop("volume")
        rows[0]["pre_close"] = 99
        rows[1]["pre_close"] = 80
        rows[2]["pre_close"] = 120
        result = kline_features.calculate_features(self.write_json("preclose_multiple.json", rows))
        self.assertGreaterEqual(
            result["data_quality"]["warning_counts"].get("conflicting_pre_close_vs_previous_bar_close", 0),
            2,
        )
        self.assertEqual(result["latest_candle"]["previous_close_source"], "previous_bar_close")

        no_pre_close = make_rows(10, start=100, step=0)
        result = kline_features.calculate_features(self.write_json("no_preclose.json", no_pre_close))
        self.assertEqual(result["latest_candle"]["previous_close_source"], "previous_bar_close")

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

    def test_relative_strength_keeps_benchmark_and_sector_separate(self):
        stock = make_rows(65, start=100, step=1)
        benchmark = make_rows(65, start=100, step=0.1)
        sector = make_rows(65, start=100, step=3)
        result = kline_features.calculate_features(
            self.write_json("rs_stock.json", stock),
            benchmark=self.write_json("rs_benchmark.json", benchmark),
            sector=self.write_json("rs_sector.json", sector),
        )
        self.assertGreater(result["structural_summary"]["relative_context"]["benchmark_relative_strength_score"], 0)
        self.assertLess(result["structural_summary"]["relative_context"]["sector_relative_strength_score"], 0)
        self.assertTrue(result["relative_strength"]["relative_strength_conflict"])
        self.assertEqual(result["structural_summary"]["relative_context"]["classification"], "mixed")

    def test_relative_strength_handles_single_side_and_bad_optional_file(self):
        stock = self.write_json("single_stock.json", make_rows(65, start=100, step=1))
        sector = self.write_json("single_sector.json", make_rows(65, start=100, step=0.1))
        sector_only = kline_features.calculate_features(stock, sector=sector)
        self.assertIsNone(sector_only["structural_summary"]["relative_context"]["benchmark_relative_strength_score"])
        self.assertIsNotNone(sector_only["structural_summary"]["relative_context"]["sector_relative_strength_score"])
        self.assertTrue(sector_only["structural_summary"]["relative_context"]["based_on_single_comparison"])

        bad = self.root / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        bad_benchmark = kline_features.calculate_features(stock, benchmark=bad)
        self.assertEqual(bad_benchmark["relative_strength"]["benchmark"]["data_quality_status"], "insufficient")
        self.assertIsNone(bad_benchmark["structural_summary"]["relative_context"]["benchmark_relative_strength_score"])

    def test_relative_context_does_not_change_technical_classification(self):
        weak_stock = make_rows(65, start=100, step=0)
        for row in weak_stock[:-1]:
            row.update({"open": 100, "high": 105, "low": 95, "close": 100, "volume": 100})
        weak_stock[-1].update({"open": 99, "high": 101, "low": 88, "close": 90, "volume": 400})
        weak = kline_features.calculate_features(
            self.write_json("weak_abs.json", weak_stock),
            benchmark=self.write_json("weak_benchmark.json", make_rows(65, start=100, step=-0.5)),
        )
        self.assertIn(weak["structural_summary"]["technical_structure"]["classification"], {"weak", "slightly_weak"})
        self.assertIn(weak["structural_summary"]["relative_context"]["classification"], {"outperforming", "slightly_outperforming"})

        strong_stock = make_rows(65, start=100, step=1)
        weak_sector = make_rows(65, start=100, step=4)
        strong = kline_features.calculate_features(
            self.write_json("strong_abs.json", strong_stock),
            sector=self.write_json("strong_sector.json", weak_sector),
        )
        self.assertIn(
            strong["structural_summary"]["technical_structure"]["classification"],
            {"constructive", "slightly_constructive"},
        )
        self.assertIn(strong["structural_summary"]["relative_context"]["classification"], {"underperforming", "slightly_underperforming"})

    def test_warning_examples_are_capped_and_evidence_is_namespaced(self):
        rows = [{"date": "bad", "open": "x", "high": 1, "low": 1, "close": 1} for _ in range(30)]
        rows.extend(make_rows(25))
        result = kline_features.calculate_features(self.write_json("warnings.json", rows))
        self.assertTrue(result["data_quality"]["warnings_truncated"])
        self.assertLessEqual(len(result["data_quality"]["warning_examples"]), 10)
        evidence = result["structural_summary"]["evidence"]
        encoded = json.dumps(evidence)
        self.assertNotIn("None", encoded)
        for values in evidence.values():
            self.assertTrue(all(":" in item for item in values))

    def test_missing_relative_strength_dimensions_remain_null(self):
        result = kline_features.calculate_features(self.write_json("no_rs.json", make_rows(65)))
        self.assertIsNone(result["structural_summary"]["relative_context"]["benchmark_relative_strength_score"])
        self.assertIsNone(result["structural_summary"]["relative_context"]["sector_relative_strength_score"])
        self.assertEqual(result["structural_summary"]["relative_context"]["classification"], "insufficient_data")
        self.assertNotIn("relative_strength_score", result["structural_summary"])

    def test_comparison_quality_gating_and_common_date_boundaries(self):
        stock = self.write_json("cmp_stock.json", make_rows(65, start=100, step=1))
        too_short = self.write_json("too_short_benchmark.json", make_rows(4, start=100, step=1))
        short_result = kline_features.calculate_features(stock, benchmark=too_short)
        self.assertEqual(short_result["relative_strength"]["benchmark"]["price_data_status"], "insufficient")
        self.assertIsNone(short_result["relative_strength"]["benchmark"]["return_1d_difference"])
        self.assertIsNone(short_result["structural_summary"]["relative_context"]["benchmark_relative_strength_score"])

        malformed = [{"date": "bad", "open": "x", "high": 1, "low": 1, "close": 1} for _ in range(5)]
        malformed.extend(make_rows(65, start=100, step=0.2))
        usable_result = kline_features.calculate_features(stock, benchmark=self.write_json("usable_cmp.json", malformed))
        self.assertEqual(usable_result["relative_strength"]["benchmark"]["price_data_status"], "usable_with_limitations")
        self.assertIsNotNone(usable_result["relative_strength"]["benchmark"]["return_20d_difference"])
        self.assertTrue(usable_result["relative_strength"]["benchmark"]["limitations"])

        future = make_rows(25, start=100, step=0.2)
        for row in future:
            row["date"] = row["date"].replace("2026", "2027")
        no_common = kline_features.calculate_features(stock, benchmark=self.write_json("no_common.json", future))
        self.assertEqual(no_common["relative_strength"]["benchmark"]["common_observations"], 0)
        self.assertIsNone(no_common["relative_strength"]["benchmark"]["return_1d_difference"])

        exact = make_rows(21, start=100, step=0.2)
        exact_result = kline_features.calculate_features(
            self.write_json("exact_stock.json", make_rows(21, start=100, step=1)),
            benchmark=self.write_json("exact_benchmark.json", exact),
        )
        self.assertIsNotNone(exact_result["relative_strength"]["benchmark"]["return_1d_difference"])
        self.assertIsNotNone(exact_result["relative_strength"]["benchmark"]["return_5d_difference"])
        self.assertIsNotNone(exact_result["relative_strength"]["benchmark"]["return_20d_difference"])

        six = make_rows(6, start=100, step=0.2)
        six_result = kline_features.calculate_features(
            self.write_json("six_stock.json", make_rows(6, start=100, step=1)),
            benchmark=self.write_json("six_benchmark.json", six),
        )
        self.assertIsNotNone(six_result["relative_strength"]["benchmark"]["return_5d_difference"])
        self.assertIsNone(six_result["relative_strength"]["benchmark"]["return_20d_difference"])

    def test_output_has_no_prediction_or_recommendation_terms_and_no_paths(self):
        path = self.write_json("stock.json", make_rows(25))
        result = kline_features.calculate_features(path)
        encoded = json.dumps(result, ensure_ascii=False)
        for forbidden in ("buy", "sell", "target_price", "tomorrow", str(self.root)):
            self.assertNotIn(forbidden, encoded)
        json.loads(encoded)


if __name__ == "__main__":
    unittest.main()
