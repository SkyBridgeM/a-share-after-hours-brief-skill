#!/usr/bin/env python3
"""Calculate Pearson correlation from two K-line CSV/JSON files.

Inputs must contain date and close fields. The parser accepts common English and
Chinese field names so it can handle exported market data after light cleanup.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any


DATE_KEYS = ("date", "trade_date", "datetime", "日期", "交易日期", "时间")
CLOSE_KEYS = ("close", "close_price", "收盘价", "收盘", "前复权收盘价", "复权收盘价")
ADJUSTMENT_KEYS = ("adjustment", "adjustment_basis", "aftime", "复权方式", "价格类型")
EXTREME_RETURN_THRESHOLD = 0.2


def load_rows(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8-sig")
    if path.suffix.lower() == ".csv":
        return list(csv.DictReader(text.splitlines()))

    data = json.loads(text)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("data", "rows", "items", "result"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    raise ValueError(f"Cannot find row list in {path}")


def pick(row: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    lowered = {str(k).lower(): v for k, v in row.items()}
    for key in keys:
        value = lowered.get(key.lower())
        if value not in (None, ""):
            return value
    return None


def normalize_date(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    match = re.match(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    match = re.match(r"^(\d{4})(\d{2})(\d{2})", text)
    if match:
        year, month, day = (int(part) for part in match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    return None


def parse_close(value: Any) -> float | None:
    if value is None:
        return None
    try:
        close = float(str(value).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None
    return close if close > 0 else None


def detect_adjustment(rows: list[dict[str, Any]]) -> str:
    values: set[str] = set()
    for row in rows:
        if isinstance(row, dict):
            value = pick(row, ADJUSTMENT_KEYS)
            if value not in (None, ""):
                values.add(str(value).strip())
    if not values:
        return "unknown"
    return ", ".join(sorted(values))


def close_series(path: Path) -> tuple[dict[str, float], dict[str, Any]]:
    rows = load_rows(path)
    series: dict[str, float] = {}
    duplicate_dates: list[str] = []
    skipped = 0
    malformed_close = 0
    missing_date = 0
    out_of_order = False
    previous_date: str | None = None

    for row in rows:
        if not isinstance(row, dict):
            skipped += 1
            continue
        normalized_date = normalize_date(pick(row, DATE_KEYS))
        close = parse_close(pick(row, CLOSE_KEYS))
        if normalized_date is None:
            skipped += 1
            missing_date += 1
            continue
        if close is None:
            skipped += 1
            malformed_close += 1
            continue
        if previous_date is not None and normalized_date < previous_date:
            out_of_order = True
        previous_date = normalized_date
        if normalized_date in series:
            duplicate_dates.append(normalized_date)
        series[normalized_date] = close

    diagnostics = {
        "rows_total": len(rows),
        "rows_skipped": skipped,
        "missing_date_rows": missing_date,
        "malformed_close_rows": malformed_close,
        "duplicate_dates": sorted(set(duplicate_dates)),
        "chronological_order_valid": not out_of_order,
        "adjustment_basis": detect_adjustment(rows),
    }
    return dict(sorted(series.items())), diagnostics


def returns(
    series: dict[str, float],
    label_name: str,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    out: dict[str, float] = {}
    warnings: list[dict[str, Any]] = []
    prev_date: str | None = None
    prev_close: float | None = None
    for current_date, close in sorted(series.items()):
        if prev_close and prev_close > 0:
            value = close / prev_close - 1.0
            out[current_date] = value
            if abs(value) >= EXTREME_RETURN_THRESHOLD:
                warnings.append({
                    "series": label_name,
                    "date": current_date,
                    "previous_date": prev_date,
                    "return": round(value, 6),
                })
        prev_date = current_date
        prev_close = close
    return out, warnings


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n != len(ys) or n < 2:
        return None
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        return None
    return cov / denom


def label(value: float | None, n: int, min_observations: int) -> str:
    if value is None or n < min_observations:
        return "样本不足"
    if value > 0.75:
        return "高度正相关"
    if value >= 0.40:
        return "中等正相关"
    if value > -0.40:
        return "相关性较弱"
    return "负相关"


def calculate(stock_a: Path, stock_b: Path, min_observations: int = 30) -> dict[str, Any]:
    series_a, diag_a = close_series(stock_a)
    series_b, diag_b = close_series(stock_b)
    ret_a, extreme_a = returns(series_a, "stock_a")
    ret_b, extreme_b = returns(series_b, "stock_b")
    common_dates = sorted(set(ret_a) & set(ret_b))
    xs = [ret_a[d] for d in common_dates]
    ys = [ret_b[d] for d in common_dates]
    value = pearson(xs, ys)
    enough = len(common_dates) >= min_observations and value is not None

    adjustment_warning = None
    if diag_a["adjustment_basis"] != diag_b["adjustment_basis"]:
        adjustment_warning = {
            "stock_a": diag_a["adjustment_basis"],
            "stock_b": diag_b["adjustment_basis"],
        }

    return {
        "observations": len(common_dates),
        "correlation": round(value, 4) if enough and value is not None else None,
        "label": label(value, len(common_dates), min_observations),
        "method": "Pearson correlation of aligned daily returns",
        "common_start": common_dates[0] if common_dates else None,
        "common_end": common_dates[-1] if common_dates else None,
        "input_diagnostics": {
            "stock_a_rows_skipped": diag_a["rows_skipped"],
            "stock_b_rows_skipped": diag_b["rows_skipped"],
            "stock_a_missing_date_rows": diag_a["missing_date_rows"],
            "stock_b_missing_date_rows": diag_b["missing_date_rows"],
            "stock_a_malformed_close_rows": diag_a["malformed_close_rows"],
            "stock_b_malformed_close_rows": diag_b["malformed_close_rows"],
            "duplicate_dates": {
                "stock_a": diag_a["duplicate_dates"],
                "stock_b": diag_b["duplicate_dates"],
            },
            "chronological_order_valid": {
                "stock_a": diag_a["chronological_order_valid"],
                "stock_b": diag_b["chronological_order_valid"],
            },
            "adjustment_basis": {
                "stock_a": diag_a["adjustment_basis"],
                "stock_b": diag_b["adjustment_basis"],
            },
            "adjustment_basis_warning": adjustment_warning,
            "extreme_return_warnings": extreme_a + extreme_b,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stock_a", type=Path)
    parser.add_argument("stock_b", type=Path)
    parser.add_argument("--min-observations", type=int, default=30)
    args = parser.parse_args()

    print(json.dumps(
        calculate(args.stock_a, args.stock_b, args.min_observations),
        ensure_ascii=False,
        indent=2,
    ))


if __name__ == "__main__":
    main()
