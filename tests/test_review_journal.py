import json
import tempfile
import unittest
from pathlib import Path

from scripts import review_journal


def previous_record(report_date="2026-06-16", code="300750.SZ"):
    return {
        "schema_version": 1,
        "report_date": report_date,
        "generated_at": f"{report_date}T16:30:00+08:00",
        "stock_codes": [code],
        "market_context": {},
        "stocks": [{
            "code": code,
            "name": "宁德时代",
            "attribution": "mixed",
            "next_session_watch": {
                "watch_items": ["量能"],
                "confirmation_conditions": [
                    {"id": "confirm-a", "condition": "条件 A"},
                    {"id": "confirm-b", "condition": "条件 B"},
                ],
                "invalidation_conditions": [
                    {"id": "invalidate-a", "condition": "失效 A"}
                ],
            },
        }],
    }


def draft(results, code="300750.SZ", generated_at="2026-06-17T16:30:00+08:00"):
    return {
        "schema_version": 1,
        "report_date": "2026-06-17",
        "generated_at": generated_at,
        "market_context": {},
        "stocks": [{
            "code": code,
            "name": "宁德时代",
            "facts": {},
            "attribution": "mixed",
            "thesis_change": "未改变",
            "condition_results": results,
            "review_adjustment": "继续观察",
            "next_session_assessment": {
                "assessment_status": "assessable",
                "tendency": "向上",
                "confidence": "中等",
            },
            "next_session_watch": {
                "watch_items": ["量能"],
                "confirmation_conditions": [
                    {"id": "next-confirm", "condition": "下一次确认"}
                ],
                "invalidation_conditions": [
                    {"id": "next-invalidate", "condition": "下一次失效"}
                ],
            },
        }],
        "position_review": None,
    }


class ReviewJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.history = Path(self.temp.name)
        (self.history / "2026-06-16__300750-SZ.json").write_text(
            json.dumps(previous_record(), ensure_ascii=False),
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp.cleanup()

    def build_status(self, results):
        record = review_journal.build_record(draft(results), self.history, True)
        return record["stocks"][0]["previous_review"]["status"]

    def test_all_confirmation_conditions_met_is_verified(self):
        status = self.build_status([
            {"id": "confirm-a", "outcome": "met"},
            {"id": "confirm-b", "outcome": "met"},
            {"id": "invalidate-a", "outcome": "not_met"},
        ])
        self.assertEqual(status, "已验证")

    def test_some_confirmation_conditions_met_is_partially_verified(self):
        status = self.build_status([
            {"id": "confirm-a", "outcome": "met"},
            {"id": "confirm-b", "outcome": "not_met"},
            {"id": "invalidate-a", "outcome": "not_met"},
        ])
        self.assertEqual(status, "部分验证")

    def test_all_confirmation_conditions_not_met_is_not_verified(self):
        status = self.build_status([
            {"id": "confirm-a", "outcome": "not_met"},
            {"id": "confirm-b", "outcome": "not_met"},
            {"id": "invalidate-a", "outcome": "not_met"},
        ])
        self.assertEqual(status, "未验证")

    def test_any_invalidation_condition_met_is_invalidated(self):
        status = self.build_status([
            {"id": "confirm-a", "outcome": "not_met"},
            {"id": "confirm-b", "outcome": "not_met"},
            {"id": "invalidate-a", "outcome": "met"},
        ])
        self.assertEqual(status, "已失效")

    def test_unknown_condition_is_unable_to_judge(self):
        status = self.build_status([
            {"id": "confirm-a", "outcome": "met"},
            {"id": "confirm-b", "outcome": "unknown"},
            {"id": "invalidate-a", "outcome": "not_met"},
        ])
        self.assertEqual(status, "无法判断")

    def test_missing_condition_result_is_unable_to_judge(self):
        status = self.build_status([
            {"id": "confirm-a", "outcome": "met"},
            {"id": "invalidate-a", "outcome": "not_met"},
        ])
        self.assertEqual(status, "无法判断")

    def test_duplicate_condition_result_ids_error(self):
        with self.assertRaisesRegex(ValueError, "Duplicate condition result"):
            self.build_status([
                {"id": "confirm-a", "outcome": "met"},
                {"id": "confirm-a", "outcome": "met"},
                {"id": "confirm-b", "outcome": "met"},
                {"id": "invalidate-a", "outcome": "not_met"},
            ])

    def test_unknown_condition_ids_error(self):
        with self.assertRaisesRegex(ValueError, "Unknown previous condition id"):
            self.build_status([{"id": "other", "outcome": "met"}])

    def test_duplicate_stock_codes_error(self):
        current = draft([])
        current["stocks"].append(dict(current["stocks"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate stock code"):
            review_journal.build_record(current, self.history, False)

    def test_lookup_finds_latest_previous_review_across_stock_pools(self):
        other_pool = previous_record("2026-06-15", "300750.SZ")
        other_pool["stock_codes"] = ["300750.SZ", "600519.SH"]
        (self.history / "2026-06-15__300750-SZ_600519-SH.json").write_text(
            json.dumps(other_pool, ensure_ascii=False),
            encoding="utf-8",
        )
        result = review_journal.lookup_previous_with_meta(
            self.history, "2026-06-17", ["300750.SZ"]
        )
        self.assertEqual(result["results"]["300750.SZ"]["report_date"], "2026-06-16")

    def test_malformed_history_files_return_warnings(self):
        (self.history / "bad.json").write_text("{bad", encoding="utf-8")
        result = review_journal.lookup_previous_with_meta(
            self.history, "2026-06-17", ["300750.SZ"]
        )
        self.assertEqual(result["records_loaded"], 1)
        self.assertEqual(result["warnings"][0]["file"], "bad.json")
        self.assertEqual(result["warnings"][0]["reason"], "invalid JSON")

    def test_old_records_without_assessment_fields_remain_readable(self):
        result = review_journal.lookup_previous_with_meta(
            self.history, "2026-06-17", ["300750.SZ"]
        )
        self.assertEqual(result["results"]["300750.SZ"]["stock"]["code"], "300750.SZ")

    def test_generated_history_contains_no_absolute_paths(self):
        current = draft([])
        current["stocks"][0]["facts"]["local_path"] = "/tmp/private.html"
        with self.assertRaisesRegex(ValueError, "absolute path"):
            review_journal.build_record(current, self.history, False)

    def test_insufficient_evidence_requires_null_tendency(self):
        current = draft([])
        current["stocks"][0]["next_session_assessment"] = {
            "assessment_status": "insufficient_evidence",
            "tendency": "维持震荡",
            "confidence": "偏低",
        }
        with self.assertRaisesRegex(ValueError, "tendency must be null"):
            review_journal.build_record(current, self.history, False)

    def test_missing_assessment_defaults_to_insufficient_evidence(self):
        current = draft([])
        current["stocks"][0].pop("next_session_assessment")
        record = review_journal.build_record(current, self.history, False)
        assessment = record["stocks"][0]["next_session_assessment"]
        self.assertEqual(assessment["assessment_status"], "insufficient_evidence")
        self.assertIsNone(assessment["tendency"])


if __name__ == "__main__":
    unittest.main()
