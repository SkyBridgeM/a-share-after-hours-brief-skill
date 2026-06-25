import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scripts import cleanup_reports


class CleanupReportsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.today = date(2026, 6, 25)
        self.policy = dict(cleanup_reports.DEFAULT_RETENTION_DAYS)

    def tearDown(self):
        self.temp.cleanup()

    def write_file(self, relative_path, content="x"):
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def plan(self, apply=False):
        return cleanup_reports.build_cleanup_plan(
            self.root, self.policy, self.today, apply=apply
        )

    def delete_paths(self, plan):
        return {item.path.relative_to(self.root).as_posix() for item in plan.delete}

    def skipped_reasons(self, plan):
        return {
            item.path.relative_to(self.root).as_posix(): item.reason
            for item in plan.skipped
        }

    def test_dry_run_lists_candidates_without_deleting(self):
        target = self.write_file("2026-05-01_A股盘后复盘.html")
        plan = self.plan()
        output = cleanup_reports.render_plan(plan)

        self.assertIn("Mode: DRY-RUN", output)
        self.assertIn("Files to delete: 1", output)
        self.assertIn("Estimated space to free:", output)
        self.assertTrue(target.exists())

    def test_apply_deletes_only_when_requested(self):
        target = self.write_file("2026-05-01_A股盘后复盘.html")
        dry_plan = self.plan(apply=False)
        self.assertIn("2026-05-01_A股盘后复盘.html", self.delete_paths(dry_plan))
        self.assertTrue(target.exists())

        apply_plan = self.plan(apply=True)
        failures = cleanup_reports.apply_cleanup(apply_plan)
        self.assertEqual(failures, [])
        self.assertFalse(target.exists())

    def test_current_month_files_are_skipped(self):
        self.write_file("2026-06-01_A股盘后复盘.html")
        plan = self.plan()
        self.assertEqual(self.delete_paths(plan), set())
        self.assertEqual(
            self.skipped_reasons(plan)["2026-06-01_A股盘后复盘.html"],
            "current month file",
        )

    def test_history_json_requires_monthly_summary_before_delete(self):
        self.write_file(
            "history/2026-02-01__002745-SZ.json",
            json.dumps({"report_date": "2026-02-01"}),
        )
        plan = self.plan()
        self.assertEqual(self.delete_paths(plan), set())
        self.assertEqual(
            self.skipped_reasons(plan)["history/2026-02-01__002745-SZ.json"],
            "monthly summary missing for history month",
        )

    def test_history_json_deletes_when_monthly_summary_exists(self):
        self.write_file("monthly-summary-2026-02.html", "<html></html>")
        self.write_file(
            "history/2026-02-01__002745-SZ.json",
            json.dumps({"report_date": "2026-02-01"}),
        )
        plan = self.plan()
        self.assertEqual(
            self.delete_paths(plan),
            {"history/2026-02-01__002745-SZ.json"},
        )

    def test_monthly_summary_is_kept_forever(self):
        self.write_file("2026-02_月度总结.html", "<html></html>")
        plan = self.plan()
        self.assertEqual(self.delete_paths(plan), set())
        self.assertEqual(
            self.skipped_reasons(plan)["2026-02_月度总结.html"],
            "monthly summary is kept forever",
        )

    def test_unknown_date_symlink_and_uncovered_files_are_skipped(self):
        self.write_file("no-date.html")
        self.write_file("notes.txt")
        source = self.write_file("2026-04-01_A股盘后复盘.html")
        symlink = self.root / "2026-04-01_symlink.html"
        symlink.symlink_to(source)

        plan = self.plan()
        reasons = self.skipped_reasons(plan)
        self.assertEqual(reasons["no-date.html"], "date not found")
        self.assertEqual(reasons["notes.txt"], "not covered by storage policy")
        self.assertEqual(reasons["2026-04-01_symlink.html"], "symlink skipped")

    def test_raw_data_cache_logs_and_charts_follow_category_retention(self):
        self.write_file("2026-05-01-data/raw.json")
        self.write_file("cache/2026-05-10-cache.json")
        self.write_file("logs/2026-05-01-run.log")
        self.write_file("charts/2026-05-01-chart.png")
        plan = self.plan()
        self.assertEqual(
            self.delete_paths(plan),
            {
                "2026-05-01-data/raw.json",
                "cache/2026-05-10-cache.json",
                "logs/2026-05-01-run.log",
                "charts/2026-05-01-chart.png",
            },
        )

    def test_run_state_json_txt_and_log_are_treated_as_logs(self):
        self.write_file("state/2026-05-01.json")
        self.write_file("run-state/2026-05-01.draft.json")
        self.write_file("runtime/2026-05-01.summary.txt")
        self.write_file("automation-state/2026-05-01.log")
        self.write_file("state/README.md")

        plan = self.plan()
        self.assertEqual(
            self.delete_paths(plan),
            {
                "state/2026-05-01.json",
                "run-state/2026-05-01.draft.json",
                "runtime/2026-05-01.summary.txt",
                "automation-state/2026-05-01.log",
            },
        )
        self.assertEqual(
            self.skipped_reasons(plan)["state/README.md"],
            "not covered by storage policy",
        )

    def test_nested_reports_html_is_recognized(self):
        self.write_file("somewhere/reports/2026-05-01__a-share-after-hours__002745-SZ.html")
        plan = self.plan()
        self.assertEqual(
            self.delete_paths(plan),
            {"somewhere/reports/2026-05-01__a-share-after-hours__002745-SZ.html"},
        )

    def test_nested_state_json_is_treated_as_logs(self):
        self.write_file("nested/workspace/state/2026-05-01.json")
        plan = self.plan()
        self.assertEqual(
            self.delete_paths(plan),
            {"nested/workspace/state/2026-05-01.json"},
        )

    def test_data_folder_is_treated_as_raw_data_before_state_logs(self):
        self.write_file("state/2026-05-01-data/raw.json")
        plan = self.plan()
        self.assertEqual(len(plan.delete), 1)
        self.assertEqual(plan.delete[0].category, "raw_data")
        self.assertEqual(
            plan.delete[0].path.relative_to(self.root).as_posix(),
            "state/2026-05-01-data/raw.json",
        )

    def test_plain_business_json_is_not_treated_as_logs(self):
        self.write_file("exports/2026-05-01-business.json")
        plan = self.plan()
        self.assertEqual(self.delete_paths(plan), set())
        self.assertEqual(
            self.skipped_reasons(plan)["exports/2026-05-01-business.json"],
            "not covered by storage policy",
        )


if __name__ == "__main__":
    unittest.main()
