#!/usr/bin/env python3
"""Maintain portable JSON history for A-share after-hours reviews."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
VALID_OUTCOMES = {"met", "not_met", "unknown"}
VALID_ATTRIBUTIONS = {
    "market_beta",
    "sector",
    "stock_specific",
    "mixed",
    "unknown",
}


def parse_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected true/false, got {value!r}")


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def normalize_code(code: str) -> str:
    value = str(code).strip().upper()
    if not re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", value):
        raise ValueError(f"Invalid A-share code: {code!r}")
    return value


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def history_filename(report_date: str, codes: list[str]) -> str:
    safe_codes = [code.replace(".", "-") for code in sorted(set(codes))]
    return f"{report_date}__{'_'.join(safe_codes)}.json"


def iter_records(history_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    records: list[tuple[Path, dict[str, Any]]] = []
    if not history_dir.exists():
        return records
    for path in sorted(history_dir.glob("*.json")):
        try:
            record = load_json(path)
            parse_iso_date(str(record["report_date"]))
            if isinstance(record.get("stocks"), list):
                records.append((path, record))
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return records


def stock_map(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for stock in record.get("stocks", []):
        if not isinstance(stock, dict) or "code" not in stock:
            continue
        try:
            result[normalize_code(str(stock["code"]))] = stock
        except ValueError:
            continue
    return result


def lookup_previous(
    history_dir: Path, before_date: str, codes: list[str]
) -> dict[str, dict[str, Any] | None]:
    cutoff = parse_iso_date(before_date)
    normalized = [normalize_code(code) for code in codes]
    candidates: dict[str, list[tuple[date, str, dict[str, Any]]]] = {
        code: [] for code in normalized
    }
    for _, record in iter_records(history_dir):
        record_date = parse_iso_date(str(record["report_date"]))
        if record_date >= cutoff:
            continue
        generated_at = str(record.get("generated_at", ""))
        by_code = stock_map(record)
        for code in normalized:
            stock = by_code.get(code)
            if stock is not None:
                candidates[code].append((record_date, generated_at, {
                    "report_date": record["report_date"],
                    "generated_at": generated_at,
                    "stock": stock,
                }))
    return {
        code: max(items, key=lambda item: (item[0], item[1]))[2] if items else None
        for code, items in candidates.items()
    }


def condition_catalog(previous_stock: dict[str, Any]) -> dict[str, str]:
    watch = previous_stock.get("next_session_watch") or {}
    catalog: dict[str, str] = {}
    for kind in ("confirmation_conditions", "invalidation_conditions"):
        for item in watch.get(kind, []):
            if not isinstance(item, dict):
                continue
            condition_id = str(item.get("id", "")).strip()
            if not condition_id:
                raise ValueError(f"Previous {kind} contains a condition without id")
            if condition_id in catalog:
                raise ValueError(f"Duplicate previous condition id: {condition_id}")
            catalog[condition_id] = kind
    return catalog


def evaluate_previous(
    previous: dict[str, Any] | None,
    results: list[dict[str, Any]],
    adjustment: str,
) -> dict[str, Any]:
    if previous is None:
        return {
            "previous_date": None,
            "status": "无历史基线",
            "evidence": [],
            "adjustment": adjustment,
        }

    previous_stock = previous["stock"]
    catalog = condition_catalog(previous_stock)
    by_id: dict[str, dict[str, Any]] = {}
    for item in results:
        if not isinstance(item, dict):
            raise ValueError("condition_results entries must be objects")
        condition_id = str(item.get("id", "")).strip()
        outcome = str(item.get("outcome", "")).strip()
        if condition_id not in catalog:
            raise ValueError(f"Unknown previous condition id: {condition_id}")
        if outcome not in VALID_OUTCOMES:
            raise ValueError(f"Invalid outcome for {condition_id}: {outcome}")
        if condition_id in by_id:
            raise ValueError(f"Duplicate condition result: {condition_id}")
        by_id[condition_id] = {
            "id": condition_id,
            "kind": catalog[condition_id],
            "outcome": outcome,
            "evidence": str(item.get("evidence", "")).strip(),
        }

    if not catalog or set(by_id) != set(catalog):
        status = "无法判断"
    else:
        invalidation_met = any(
            item["kind"] == "invalidation_conditions" and item["outcome"] == "met"
            for item in by_id.values()
        )
        confirmations = [
            item for item in by_id.values()
            if item["kind"] == "confirmation_conditions"
        ]
        any_unknown = any(item["outcome"] == "unknown" for item in by_id.values())
        confirmations_met = sum(item["outcome"] == "met" for item in confirmations)

        if invalidation_met:
            status = "已失效"
        elif any_unknown:
            status = "无法判断"
        elif confirmations and confirmations_met == len(confirmations):
            status = "已验证"
        elif confirmations_met > 0:
            status = "部分验证"
        else:
            status = "未验证"

    return {
        "previous_date": previous["report_date"],
        "status": status,
        "evidence": list(by_id.values()),
        "adjustment": adjustment,
    }


def validate_next_watch(stock: dict[str, Any]) -> None:
    watch = stock.get("next_session_watch")
    if not isinstance(watch, dict):
        raise ValueError(f"{stock['code']} requires next_session_watch")
    seen: set[str] = set()
    for kind in ("confirmation_conditions", "invalidation_conditions"):
        items = watch.get(kind)
        if not isinstance(items, list):
            raise ValueError(f"{stock['code']} {kind} must be a list")
        for item in items:
            if not isinstance(item, dict):
                raise ValueError(f"{stock['code']} {kind} entries must be objects")
            condition_id = str(item.get("id", "")).strip()
            condition = str(item.get("condition", "")).strip()
            if not condition_id or not condition:
                raise ValueError(f"{stock['code']} conditions require id and condition")
            if condition_id in seen:
                raise ValueError(f"{stock['code']} duplicate condition id: {condition_id}")
            seen.add(condition_id)
    if not isinstance(watch.get("watch_items"), list):
        raise ValueError(f"{stock['code']} watch_items must be a list")


def build_record(
    draft: dict[str, Any],
    history_dir: Path,
    compare_previous: bool,
) -> dict[str, Any]:
    if int(draft.get("schema_version", SCHEMA_VERSION)) != SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {draft.get('schema_version')}")
    report_date = str(draft.get("report_date", ""))
    parse_iso_date(report_date)
    stocks = draft.get("stocks")
    if not isinstance(stocks, list) or not stocks:
        raise ValueError("stocks must be a non-empty list")

    codes: list[str] = []
    for stock in stocks:
        if not isinstance(stock, dict):
            raise ValueError("stocks entries must be objects")
        code = normalize_code(str(stock.get("code", "")))
        stock["code"] = code
        if code in codes:
            raise ValueError(f"Duplicate stock code: {code}")
        codes.append(code)
        if stock.get("attribution", "unknown") not in VALID_ATTRIBUTIONS:
            raise ValueError(f"{code} has invalid attribution")
        validate_next_watch(stock)

    previous = (
        lookup_previous(history_dir, report_date, codes)
        if compare_previous
        else {code: None for code in codes}
    )
    for stock in stocks:
        code = stock["code"]
        results = stock.pop("condition_results", [])
        if not isinstance(results, list):
            raise ValueError(f"{code} condition_results must be a list")
        adjustment = str(stock.pop("review_adjustment", "")).strip()
        stock["previous_review"] = evaluate_previous(
            previous.get(code), results, adjustment
        )

    draft["schema_version"] = SCHEMA_VERSION
    draft["stock_codes"] = sorted(codes)
    draft.setdefault("market_context", {})
    draft.setdefault("position_review", None)
    return draft


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def default_history_dir(output_html: Path) -> Path:
    return output_html.expanduser().resolve().parent / "history"


def command_lookup(args: argparse.Namespace) -> None:
    codes = [item for item in args.stocks.split(",") if item.strip()]
    result = lookup_previous(args.history_dir, args.before_date, codes)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def command_build(args: argparse.Namespace) -> None:
    draft = load_json(args.input)
    history_dir = args.history_dir or default_history_dir(args.output_html)
    record = build_record(draft, history_dir, args.compare_previous)
    codes = [stock["code"] for stock in record["stocks"]]
    target = history_dir / history_filename(record["report_date"], codes)
    if args.history:
        atomic_write_json(target, record)
    print(json.dumps({
        "saved": args.history,
        "history_file": str(target) if args.history else None,
        "record": record,
    }, ensure_ascii=False, indent=2))


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    lookup = subparsers.add_parser("lookup")
    lookup.add_argument("--history-dir", type=Path, required=True)
    lookup.add_argument("--before-date", required=True)
    lookup.add_argument("--stocks", required=True)
    lookup.set_defaults(func=command_lookup)

    build = subparsers.add_parser("build")
    build.add_argument("--input", type=Path, required=True)
    build.add_argument("--output-html", type=Path, required=True)
    build.add_argument("--history-dir", type=Path)
    build.add_argument("--history", type=parse_bool, default=True)
    build.add_argument("--compare-previous", type=parse_bool, default=True)
    build.set_defaults(func=command_build)
    return parser


def main() -> None:
    args = make_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
