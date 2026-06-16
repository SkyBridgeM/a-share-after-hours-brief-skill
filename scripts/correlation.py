#!/usr/bin/env python3
"""Calculate Pearson correlation from two K-line CSV/JSON files.

Inputs must contain date and close fields. The parser accepts common English and
Chinese field names so it can handle exported Wind results after light cleanup.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any


DATE_KEYS = ("date", "trade_date", "datetime", "日期", "交易日期", "时间")
CLOSE_KEYS = ("close", "close_price", "收盘价", "收盘", "前复权收盘价", "复权收盘价")


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


def parse_close(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(str(value).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def close_series(path: Path) -> dict[str, float]:
    series: dict[str, float] = {}
    for row in load_rows(path):
        if not isinstance(row, dict):
            continue
        date = pick(row, DATE_KEYS)
        close = parse_close(pick(row, CLOSE_KEYS))
        if date is None or close is None or close <= 0:
            continue
        series[str(date)[:10]] = close
    return dict(sorted(series.items()))


def returns(series: dict[str, float]) -> dict[str, float]:
    out: dict[str, float] = {}
    prev: float | None = None
    for date, close in sorted(series.items()):
        if prev and prev > 0:
            out[date] = close / prev - 1.0
        prev = close
    return out


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stock_a", type=Path)
    parser.add_argument("stock_b", type=Path)
    parser.add_argument("--min-observations", type=int, default=30)
    args = parser.parse_args()

    ret_a = returns(close_series(args.stock_a))
    ret_b = returns(close_series(args.stock_b))
    common_dates = sorted(set(ret_a) & set(ret_b))
    xs = [ret_a[d] for d in common_dates]
    ys = [ret_b[d] for d in common_dates]
    value = pearson(xs, ys)
    enough = len(common_dates) >= args.min_observations and value is not None

    result = {
        "observations": len(common_dates),
        "correlation": round(value, 4) if enough and value is not None else None,
        "label": label(value, len(common_dates), args.min_observations),
        "method": "Pearson correlation of aligned daily returns",
        "common_start": common_dates[0] if common_dates else None,
        "common_end": common_dates[-1] if common_dates else None,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
