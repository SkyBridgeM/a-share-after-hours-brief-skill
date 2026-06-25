#!/usr/bin/env python3
"""Clean local A-share after-hours report artifacts with a dry-run default."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


DEFAULT_RETENTION_DAYS = {
    "html": 30,
    "charts": 30,
    "raw_data": 14,
    "cache": 7,
    "logs": 14,
    "history_json": 90,
}

MONTHLY_SUMMARY_POLICY = "keep_forever"
MONTHLY_SUMMARY_EXTENSIONS = {".html", ".md", ".json"}
CHART_EXTENSIONS = {".png", ".jpg", ".jpeg", ".svg", ".webp", ".gif"}
RAW_DATA_EXTENSIONS = {".json", ".csv", ".tsv", ".xlsx", ".xls", ".parquet", ".txt"}

DATE_PATTERNS = (
    re.compile(r"(?<!\d)(20\d{2})[-_](0[1-9]|1[0-2])[-_](0[1-9]|[12]\d|3[01])(?!\d)"),
    re.compile(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])(?!\d)"),
)
MONTH_PATTERNS = (
    re.compile(r"monthly[-_ ]?summary[-_ ]?(20\d{2})[-_](0[1-9]|1[0-2])"),
    re.compile(r"(20\d{2})[-_](0[1-9]|1[0-2])[-_ ]?monthly[-_ ]?summary"),
    re.compile(r"(20\d{2})[-_](0[1-9]|1[0-2])[-_ ]?月度总结"),
    re.compile(r"月度总结[-_ ]?(20\d{2})[-_](0[1-9]|1[0-2])"),
)


@dataclass(frozen=True)
class CleanupItem:
    path: Path
    category: str
    file_date: date
    size_bytes: int
    reason: str


@dataclass(frozen=True)
class SkippedItem:
    path: Path
    category: str
    reason: str


@dataclass(frozen=True)
class CleanupPlan:
    root: Path
    apply: bool
    today: date
    delete: list[CleanupItem]
    skipped: list[SkippedItem]

    @property
    def total_bytes(self) -> int:
        return sum(item.size_bytes for item in self.delete)


def load_policy(path: Path | None) -> dict[str, int]:
    if path is None:
        return dict(DEFAULT_RETENTION_DAYS)
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    raw = data.get("retention_days", data)
    policy = dict(DEFAULT_RETENTION_DAYS)
    for key in DEFAULT_RETENTION_DAYS:
        value = raw.get(key, policy[key])
        if not isinstance(value, int) or value < 0:
            raise ValueError(f"retention_days.{key} must be a non-negative integer")
        policy[key] = value
    if data.get("monthly_summary", MONTHLY_SUMMARY_POLICY) != MONTHLY_SUMMARY_POLICY:
        raise ValueError('monthly_summary must be "keep_forever"')
    return policy


def parse_report_date_from_name(name: str) -> date | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(name)
        if not match:
            continue
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None
    return None


def parse_history_report_date(path: Path) -> date | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    report_date = data.get("report_date")
    if not isinstance(report_date, str):
        return None
    try:
        return date.fromisoformat(report_date[:10])
    except ValueError:
        return None


def detect_monthly_summary_month(path: Path) -> str | None:
    if path.suffix.lower() not in MONTHLY_SUMMARY_EXTENSIONS:
        return None
    normalized = path.stem.lower().replace(" ", "-")
    for pattern in MONTH_PATTERNS:
        match = pattern.search(normalized)
        if match:
            return f"{match.group(1)}-{match.group(2)}"
    return None


def collect_monthly_summary_months(root: Path) -> set[str]:
    months: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        month = detect_monthly_summary_month(path)
        if month:
            months.add(month)
    return months


def path_parts_lower(path: Path) -> list[str]:
    return [part.lower() for part in path.parts]


def classify_file(root: Path, path: Path, monthly_summary_months: set[str]) -> tuple[str | None, str | None]:
    if path.is_symlink():
        return None, "symlink skipped"
    if detect_monthly_summary_month(path):
        return "monthly_summary", "monthly summary is kept forever"

    rel = path.relative_to(root)
    parts = path_parts_lower(rel)
    suffix = path.suffix.lower()

    if len(parts) >= 2 and parts[-2] == "history" and suffix == ".json":
        return "history_json", None
    if any(part in {"cache", ".cache", "__pycache__"} for part in parts) or suffix in {".pyc", ".pyo"}:
        return "cache", None
    if any(part == "logs" for part in parts) or suffix == ".log":
        return "logs", None
    if any(part == "charts" for part in parts) or suffix in CHART_EXTENSIONS:
        return "charts", None
    if any(part in {"raw_data", "data"} or part.endswith("-data") for part in parts):
        if suffix in RAW_DATA_EXTENSIONS:
            return "raw_data", None
        return None, "raw data directory file type is not covered"
    if suffix == ".html" and rel.parent == Path("."):
        return "html", None

    return None, "not covered by storage policy"


def file_date(root: Path, path: Path, category: str) -> date | None:
    rel = path.relative_to(root)
    for part in reversed(rel.parts):
        parsed = parse_report_date_from_name(part)
        if parsed:
            return parsed
    if category == "history_json":
        return parse_history_report_date(path)
    return None


def format_size(num_bytes: int) -> str:
    units = ("B", "KB", "MB", "GB", "TB")
    size = float(num_bytes)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{num_bytes} B"


def build_cleanup_plan(root: Path, policy: dict[str, int], today: date, apply: bool = False) -> CleanupPlan:
    root = root.expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"root must be an existing directory: {root}")

    current_month = f"{today:%Y-%m}"
    monthly_summary_months = collect_monthly_summary_months(root)
    delete: list[CleanupItem] = []
    skipped: list[SkippedItem] = []

    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        try:
            path.relative_to(root)
        except ValueError:
            continue
        category, skip_reason = classify_file(root, path, monthly_summary_months)
        if category is None:
            skipped.append(SkippedItem(path, "unknown", skip_reason or "not covered"))
            continue
        if category == "monthly_summary":
            skipped.append(SkippedItem(path, category, skip_reason or "kept forever"))
            continue

        parsed_date = file_date(root, path, category)
        if parsed_date is None:
            skipped.append(SkippedItem(path, category, "date not found"))
            continue
        if f"{parsed_date:%Y-%m}" == current_month:
            skipped.append(SkippedItem(path, category, "current month file"))
            continue

        retention_days = policy[category]
        age_days = (today - parsed_date).days
        if age_days <= retention_days:
            skipped.append(SkippedItem(path, category, f"within {retention_days}-day retention"))
            continue

        if category == "history_json" and f"{parsed_date:%Y-%m}" not in monthly_summary_months:
            skipped.append(SkippedItem(path, category, "monthly summary missing for history month"))
            continue

        try:
            size_bytes = path.stat().st_size
        except OSError:
            skipped.append(SkippedItem(path, category, "cannot read file size"))
            continue
        delete.append(
            CleanupItem(
                path=path,
                category=category,
                file_date=parsed_date,
                size_bytes=size_bytes,
                reason=f"older than {retention_days} days",
            )
        )

    return CleanupPlan(root=root, apply=apply, today=today, delete=delete, skipped=skipped)


def render_plan(plan: CleanupPlan) -> str:
    mode = "APPLY" if plan.apply else "DRY-RUN"
    lines = [
        f"Mode: {mode}",
        f"Root: {plan.root}",
        f"Date: {plan.today.isoformat()}",
        "",
        f"Files to delete: {len(plan.delete)}",
    ]
    if plan.delete:
        for item in plan.delete:
            lines.append(
                f"- [{item.category}] {item.path} "
                f"({format_size(item.size_bytes)}, {item.file_date.isoformat()}, {item.reason})"
            )
    else:
        lines.append("- None")
    lines.extend([
        "",
        f"Estimated space to free: {format_size(plan.total_bytes)}",
        "",
        f"Skipped files: {len(plan.skipped)}",
    ])
    if plan.skipped:
        for item in plan.skipped:
            lines.append(f"- [{item.category}] {item.path} ({item.reason})")
    else:
        lines.append("- None")
    return "\n".join(lines)


def apply_cleanup(plan: CleanupPlan) -> list[tuple[Path, str]]:
    failures: list[tuple[Path, str]] = []
    for item in plan.delete:
        try:
            item.path.unlink()
        except OSError as exc:
            failures.append((item.path, str(exc)))
    return failures


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview or clean local A-share after-hours report artifacts."
    )
    parser.add_argument("--root", type=Path, required=True, help="Report output root to scan.")
    parser.add_argument("--policy", type=Path, help="Storage policy JSON file.")
    parser.add_argument("--apply", action="store_true", help="Actually delete files. Default is dry-run.")
    parser.add_argument(
        "--today",
        type=str,
        help="Override today's date as YYYY-MM-DD. Intended for tests and repeatable audits.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        today = date.fromisoformat(args.today) if args.today else datetime.now().date()
        policy = load_policy(args.policy)
        plan = build_cleanup_plan(args.root, policy, today, apply=args.apply)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    print(render_plan(plan))
    if not args.apply:
        print("\nDry-run only. Re-run with --apply to delete the listed files.")
        return 0

    failures = apply_cleanup(plan)
    print(f"\nDeleted files: {len(plan.delete) - len(failures)}")
    if failures:
        print(f"Delete failures: {len(failures)}")
        for path, reason in failures:
            print(f"- {path} ({reason})")
        return 1
    print("Delete failures: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
