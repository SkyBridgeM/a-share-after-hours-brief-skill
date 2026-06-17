#!/usr/bin/env python3
"""Calculate deterministic K-line structure features from daily OHLCV data."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
ANNUALIZATION_FACTOR = 252
WARNING_EXAMPLE_LIMIT = 10
PRE_CLOSE_CONFLICT_THRESHOLD = 0.001
QUALITY_GOOD = "good"
QUALITY_USABLE = "usable_with_limitations"
QUALITY_INSUFFICIENT = "insufficient"
ALLOWED_ADJUSTMENTS = {"forward", "backward", "none", "unknown"}
DATE_KEYS = ("date", "trade_date", "datetime", "日期", "交易日期", "时间")
OPEN_KEYS = ("open", "open_price", "开盘价", "开盘")
HIGH_KEYS = ("high", "high_price", "最高价", "最高")
LOW_KEYS = ("low", "low_price", "最低价", "最低")
CLOSE_KEYS = ("close", "close_price", "收盘价", "收盘", "前复权收盘价", "复权收盘价")
VOLUME_KEYS = ("volume", "成交量")
AMOUNT_KEYS = ("amount", "turnover_amount", "成交额")
PRE_CLOSE_KEYS = ("pre_close", "prev_close", "前收盘价", "昨收")


@dataclass(frozen=True)
class Bar:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    amount: float | None = None
    pre_close: float | None = None


@dataclass
class WarningCollector:
    counts: dict[str, int]
    examples: list[dict[str, str]]
    total: int = 0

    def add(self, reason: str, row_date: str | None = None) -> None:
        self.total += 1
        self.counts[reason] = self.counts.get(reason, 0) + 1
        if len(self.examples) < WARNING_EXAMPLE_LIMIT:
            item = {"reason": reason}
            if row_date:
                item["date"] = row_date
            self.examples.append(item)

    def summary(self) -> dict[str, Any]:
        return {
            "warning_counts": dict(sorted(self.counts.items())),
            "warning_examples": self.examples,
            "warnings_truncated": self.total > len(self.examples),
            "warnings": self.examples,
        }


def rounded(value: float | None, digits: int = 6) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


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
    raise ValueError(f"Cannot find row list in {path.name}")


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


def parse_number(value: Any, positive: bool = False) -> float | None:
    if value is None:
        return None
    try:
        parsed = float(str(value).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None
    if not math.isfinite(parsed):
        return None
    if positive and parsed <= 0:
        return None
    return parsed


def load_bars(path: Path, adjustment: str = "unknown") -> tuple[list[Bar], dict[str, Any]]:
    rows = load_rows(path)
    by_date: dict[str, Bar] = {}
    duplicate_dates: list[str] = []
    warnings = WarningCollector({}, [])
    missing_ohlc = {"open": 0, "high": 0, "low": 0, "close": 0}
    raw_rows_missing_volume = 0
    invalid_price_rows = 0
    rows_skipped = 0
    previous_seen_date: str | None = None
    chronological_corrections = 0

    for row in rows:
        if not isinstance(row, dict):
            rows_skipped += 1
            warnings.add("row_not_object")
            continue
        row_date = normalize_date(pick(row, DATE_KEYS))
        if row_date is None:
            rows_skipped += 1
            warnings.add("missing_or_malformed_date")
            continue
        if previous_seen_date is not None and row_date < previous_seen_date:
            chronological_corrections += 1
        previous_seen_date = row_date

        open_ = parse_number(pick(row, OPEN_KEYS), positive=True)
        high = parse_number(pick(row, HIGH_KEYS), positive=True)
        low = parse_number(pick(row, LOW_KEYS), positive=True)
        close = parse_number(pick(row, CLOSE_KEYS), positive=True)
        values = {"open": open_, "high": high, "low": low, "close": close}
        for key, value in values.items():
            if value is None:
                missing_ohlc[key] += 1
        if any(value is None for value in values.values()):
            rows_skipped += 1
            invalid_price_rows += 1
            warnings.add("missing_or_malformed_ohlc", row_date)
            continue
        assert open_ is not None and high is not None and low is not None and close is not None
        if high < max(open_, low, close) or low > min(open_, high, close):
            rows_skipped += 1
            invalid_price_rows += 1
            warnings.add("inconsistent_ohlc_range", row_date)
            continue

        volume = parse_number(pick(row, VOLUME_KEYS), positive=False)
        if volume is None:
            raw_rows_missing_volume += 1
        elif volume < 0:
            volume = None
            raw_rows_missing_volume += 1
        amount = parse_number(pick(row, AMOUNT_KEYS), positive=False)
        pre_close = parse_number(pick(row, PRE_CLOSE_KEYS), positive=True)
        bar = Bar(row_date, open_, high, low, close, volume, amount, pre_close)
        if row_date in by_date:
            duplicate_dates.append(row_date)
            warnings.add("duplicate_date_last_row_kept", row_date)
        by_date[row_date] = bar

    bars = [by_date[key] for key in sorted(by_date)]
    quality = data_quality(
        rows_read=len(rows),
        bars=bars,
        rows_skipped=rows_skipped,
        duplicate_dates=sorted(set(duplicate_dates)),
        missing_ohlc=missing_ohlc,
        raw_rows_missing_volume=raw_rows_missing_volume,
        invalid_price_rows=invalid_price_rows,
        chronological_corrections=chronological_corrections,
        adjustment=adjustment,
        warnings=warnings,
    )
    return bars, quality


def data_quality(
    rows_read: int,
    bars: list[Bar],
    rows_skipped: int,
    duplicate_dates: list[str],
    missing_ohlc: dict[str, int],
    raw_rows_missing_volume: int,
    invalid_price_rows: int,
    chronological_corrections: int,
    adjustment: str,
    warnings: WarningCollector,
) -> dict[str, Any]:
    valid_rows = len(bars)
    final_rows_with_volume = sum(1 for bar in bars if bar.volume is not None)
    final_rows_missing_volume = valid_rows - final_rows_with_volume
    volume_coverage_ratio = final_rows_with_volume / valid_rows if valid_rows else 0.0
    volume_coverage_ratio = min(1.0, max(0.0, volume_coverage_ratio))
    if valid_rows < 5:
        price_data_status = QUALITY_INSUFFICIENT
    elif rows_skipped or valid_rows < 20:
        price_data_status = QUALITY_USABLE
    else:
        price_data_status = QUALITY_GOOD
    if volume_coverage_ratio >= 0.95:
        volume_data_status = QUALITY_GOOD
    elif volume_coverage_ratio >= 0.50:
        volume_data_status = QUALITY_USABLE
    else:
        volume_data_status = QUALITY_INSUFFICIENT
    if valid_rows < 5:
        status = QUALITY_INSUFFICIENT
    elif price_data_status != QUALITY_GOOD or volume_data_status != QUALITY_GOOD:
        status = QUALITY_USABLE
    else:
        status = QUALITY_GOOD
    result = {
        "status": status,
        "price_data_status": price_data_status,
        "volume_data_status": volume_data_status,
        "volume_coverage_ratio": rounded(volume_coverage_ratio),
        "rows_read": rows_read,
        "valid_rows": valid_rows,
        "rows_skipped": rows_skipped,
        "duplicate_dates": duplicate_dates,
        "missing_ohlc_counts": missing_ohlc,
        "missing_volume_count": final_rows_missing_volume,
        "raw_rows_missing_volume": raw_rows_missing_volume,
        "final_rows_missing_volume": final_rows_missing_volume,
        "raw_input": {
            "rows_read": rows_read,
            "rows_skipped": rows_skipped,
            "raw_rows_missing_volume": raw_rows_missing_volume,
            "duplicate_date_count": len(duplicate_dates),
            "duplicate_dates": duplicate_dates,
            "missing_ohlc_counts": missing_ohlc,
            "non_positive_or_invalid_price_rows": invalid_price_rows,
            "chronological_corrections": chronological_corrections,
        },
        "final_series": {
            "valid_rows": valid_rows,
            "final_rows_with_volume": final_rows_with_volume,
            "final_rows_missing_volume": final_rows_missing_volume,
            "volume_coverage_ratio": rounded(volume_coverage_ratio),
            "first_date": bars[0].date if bars else None,
            "last_date": bars[-1].date if bars else None,
        },
        "non_positive_or_invalid_price_rows": invalid_price_rows,
        "chronological_corrections": chronological_corrections,
        "adjustment_basis": adjustment,
        "first_date": bars[0].date if bars else None,
        "last_date": bars[-1].date if bars else None,
        "sufficient_for": {
            "return_5d": valid_rows >= 6,
            "return_10d": valid_rows >= 11,
            "return_20d": valid_rows >= 21,
            "return_60d": valid_rows >= 61,
        },
    }
    result.update(warnings.summary())
    return result


def merge_warning_summary(quality: dict[str, Any], warnings: WarningCollector) -> None:
    summary = warnings.summary()
    counts = dict(quality.get("warning_counts", {}))
    for reason, count in summary["warning_counts"].items():
        counts[reason] = counts.get(reason, 0) + count
    examples = list(quality.get("warning_examples", []))
    examples.extend(summary["warning_examples"])
    quality["warning_counts"] = dict(sorted(counts.items()))
    quality["warning_examples"] = examples[:WARNING_EXAMPLE_LIMIT]
    quality["warnings"] = quality["warning_examples"]
    quality["warnings_truncated"] = (
        bool(quality.get("warnings_truncated"))
        or bool(summary["warnings_truncated"])
        or len(examples) > WARNING_EXAMPLE_LIMIT
    )


def period_return(bars: list[Bar], days: int) -> float | None:
    if len(bars) <= days:
        return None
    return bars[-1].close / bars[-1 - days].close - 1.0


def daily_returns(bars: list[Bar]) -> list[tuple[str, float]]:
    values: list[tuple[str, float]] = []
    for previous, current in zip(bars, bars[1:]):
        values.append((current.date, current.close / previous.close - 1.0))
    return values


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def moving_average_series(bars: list[Bar], period: int) -> list[tuple[str, float]]:
    out: list[tuple[str, float]] = []
    closes = [bar.close for bar in bars]
    for index in range(period - 1, len(closes)):
        out.append((bars[index].date, sum(closes[index + 1 - period:index + 1]) / period))
    return out


def moving_average(bars: list[Bar], period: int) -> float | None:
    if len(bars) < period:
        return None
    return sum(bar.close for bar in bars[-period:]) / period


def ma_slope(bars: list[Bar], period: int, observations: int = 5) -> float | None:
    series = moving_average_series(bars, period)
    if len(series) <= observations:
        return None
    previous = series[-1 - observations][1]
    current = series[-1][1]
    return current / previous - 1.0 if previous else None


def returns_section(bars: list[Bar]) -> dict[str, Any]:
    notes = []
    result = {}
    for days in (1, 5, 10, 20, 60):
        value = period_return(bars, days)
        key = f"return_{days}d"
        result[key] = rounded(value)
        if value is None:
            notes.append(f"{key} requires at least {days + 1} valid observations")
    result["insufficiency_notes"] = notes
    return result


def moving_averages_section(bars: list[Bar]) -> dict[str, Any]:
    latest_close = bars[-1].close if bars else None
    values: dict[str, Any] = {
        "slope_method": "percentage change in the moving average over the last five available MA observations"
    }
    for period in (5, 10, 20, 60):
        ma = moving_average(bars, period)
        values[f"ma{period}"] = rounded(ma)
        values[f"close_vs_ma{period}"] = rounded(latest_close / ma - 1.0 if latest_close and ma else None)
    values["ma5_vs_ma10"] = rounded(
        values["ma5"] / values["ma10"] - 1.0 if values["ma5"] and values["ma10"] else None
    )
    values["ma10_vs_ma20"] = rounded(
        values["ma10"] / values["ma20"] - 1.0 if values["ma10"] and values["ma20"] else None
    )
    values["ma20_slope_5obs"] = rounded(ma_slope(bars, 20))
    values["ma60_slope_5obs"] = rounded(ma_slope(bars, 60))
    return values


def trend_section(bars: list[Bar], ma: dict[str, Any], quality_status: str) -> dict[str, Any]:
    if quality_status == "insufficient" or len(bars) < 20 or ma["ma20"] is None:
        return {"state": "insufficient_data", "evidence": []}
    close = bars[-1].close
    evidence: list[str] = []
    above = [period for period in (5, 10, 20) if ma.get(f"ma{period}") and close > ma[f"ma{period}"]]
    below = [period for period in (5, 10, 20) if ma.get(f"ma{period}") and close < ma[f"ma{period}"]]
    if len(above) == 3:
        evidence.append("trend:close_above_ma5_ma10_ma20")
    if len(below) == 3:
        evidence.append("trend:close_below_ma5_ma10_ma20")
    if ma["ma5"] and ma["ma10"] and ma["ma20"] and ma["ma5"] > ma["ma10"] > ma["ma20"]:
        evidence.append("trend:ma5_above_ma10_above_ma20")
    if ma["ma5"] and ma["ma10"] and ma["ma20"] and ma["ma5"] < ma["ma10"] < ma["ma20"]:
        evidence.append("trend:ma5_below_ma10_below_ma20")
    slope20 = ma.get("ma20_slope_5obs")
    if slope20 is not None and slope20 > 0:
        evidence.append("trend:ma20_slope_positive")
    if slope20 is not None and slope20 < 0:
        evidence.append("trend:ma20_slope_negative")

    close_vs_ma20 = ma.get("close_vs_ma20")
    if all(item in evidence for item in ("trend:close_above_ma5_ma10_ma20", "trend:ma5_above_ma10_above_ma20")) and slope20 and slope20 > 0.005 and close_vs_ma20 and close_vs_ma20 > 0.03:
        state = "strong_uptrend"
    elif len(above) >= 2 and slope20 is not None and slope20 >= 0:
        state = "uptrend"
    elif all(item in evidence for item in ("trend:close_below_ma5_ma10_ma20", "trend:ma5_below_ma10_below_ma20")) and slope20 and slope20 < -0.005 and close_vs_ma20 and close_vs_ma20 < -0.03:
        state = "strong_downtrend"
    elif len(below) >= 2 and slope20 is not None and slope20 <= 0:
        state = "downtrend"
    else:
        state = "mixed"
    return {"state": state, "evidence": evidence}


def previous_close_reference(
    bars: list[Bar],
    index: int,
    warnings: WarningCollector | None = None,
    use_verified_pre_close: bool = False,
) -> tuple[float | None, str]:
    bar = bars[index]
    previous_close = bars[index - 1].close if index > 0 else None
    if bar.pre_close is not None and previous_close is not None:
        diff = abs(bar.pre_close / previous_close - 1.0)
        if diff > PRE_CLOSE_CONFLICT_THRESHOLD and warnings is not None:
            warnings.add("conflicting_pre_close_vs_previous_bar_close", bar.date)
    if bar.pre_close is not None and (previous_close is None or use_verified_pre_close):
        return bar.pre_close, "verified_pre_close" if use_verified_pre_close else "pre_close_no_previous_bar"
    if previous_close is not None:
        return previous_close, "previous_bar_close"
    return None, "unavailable"


def latest_candle_section(
    bars: list[Bar],
    warnings: WarningCollector | None = None,
    use_verified_pre_close: bool = False,
) -> dict[str, Any]:
    if not bars:
        return {}
    latest = bars[-1]
    previous = bars[-2] if len(bars) >= 2 else None
    daily_range = latest.high - latest.low
    if daily_range > 0:
        close_location = (latest.close - latest.low) / daily_range
        open_location = (latest.open - latest.low) / daily_range
        body_ratio = abs(latest.close - latest.open) / daily_range
        upper_shadow_ratio = (latest.high - max(latest.open, latest.close)) / daily_range
        lower_shadow_ratio = (min(latest.open, latest.close) - latest.low) / daily_range
    else:
        close_location = open_location = body_ratio = upper_shadow_ratio = lower_shadow_ratio = None
    if close_location is None:
        close_zone = "zero_range"
    elif close_location >= 0.75:
        close_zone = "near_high"
    elif close_location <= 0.25:
        close_zone = "near_low"
    else:
        close_zone = "middle"
    if open_location is not None and close_location is not None and open_location >= 0.75 and close_location <= 0.25:
        session_shape = "high_open_low_close"
    elif open_location is not None and close_location is not None and open_location <= 0.25 and close_location >= 0.75:
        session_shape = "low_open_high_close"
    else:
        session_shape = "neutral"
    reference_close, reference_source = previous_close_reference(
        bars, len(bars) - 1, warnings, use_verified_pre_close
    )
    return {
        "close_location": rounded(close_location),
        "body_size": rounded(abs(latest.close - latest.open)),
        "body_ratio": rounded(body_ratio),
        "upper_shadow_size": rounded(latest.high - max(latest.open, latest.close)),
        "upper_shadow_ratio": rounded(upper_shadow_ratio),
        "lower_shadow_size": rounded(min(latest.open, latest.close) - latest.low),
        "lower_shadow_ratio": rounded(lower_shadow_ratio),
        "gap_from_previous_close": rounded(latest.open / reference_close - 1.0 if reference_close else None),
        "previous_close_source": reference_source,
        "session_shape": session_shape,
        "close_zone": close_zone,
        "thresholds": {
            "near_high": "close_location >= 0.75",
            "near_low": "close_location <= 0.25",
        },
    }


def percentile(values: list[float], latest: float, min_count: int) -> float | None:
    if len(values) < min_count:
        return None
    sorted_values = sorted(values)
    rank = sum(value <= latest for value in sorted_values)
    return rank / len(sorted_values)


def volume_section(bars: list[Bar], returns_: list[tuple[str, float]], volume_data_status: str) -> dict[str, Any]:
    insufficient = {
        "ratio_vs_prior_5d": None,
        "ratio_vs_prior_20d": None,
        "percentile_vs_prior_60d": None,
        "percentile_60d": None,
        "deprecated_fields": {"percentile_60d": "Use percentile_vs_prior_60d. Planned removal in 0.2.0."},
        "avg_volume_positive_return_days": None,
        "avg_volume_negative_return_days": None,
        "state": "insufficient_data",
    }
    if volume_data_status == QUALITY_INSUFFICIENT or not bars or bars[-1].volume is None:
        return {
            **insufficient,
            "limitation": "volume coverage is below 50% or latest volume is missing",
        }
    latest = bars[-1].volume
    assert latest is not None
    prior_volumes = [bar.volume for bar in bars[:-1] if bar.volume is not None]
    prior_5 = prior_volumes[-5:]
    prior_20 = prior_volumes[-20:]
    ratio5 = latest / average(prior_5) if len(prior_5) == 5 and average(prior_5) else None
    ratio20 = latest / average(prior_20) if len(prior_20) == 20 and average(prior_20) else None
    prior_60 = prior_volumes[-60:]
    volume_percentile = percentile(prior_60, latest, 60)

    by_date = {bar.date: bar.volume for bar in bars}
    positive = [by_date[d] for d, value in returns_ if value > 0 and by_date.get(d) is not None]
    negative = [by_date[d] for d, value in returns_ if value < 0 and by_date.get(d) is not None]
    avg_positive = average(positive) if len(positive) >= 2 else None
    avg_negative = average(negative) if len(negative) >= 2 else None

    if ratio20 is None and ratio5 is None and volume_percentile is None:
        state = "insufficient_data"
    elif (ratio20 is not None and ratio20 >= 2.0) or (volume_percentile is not None and volume_percentile >= 0.9):
        state = "high"
    elif (ratio20 is not None and ratio20 >= 1.2) or (ratio5 is not None and ratio5 >= 1.2):
        state = "above_average"
    elif (ratio20 is not None and ratio20 <= 0.8) or (ratio5 is not None and ratio5 <= 0.8):
        state = "below_average"
    else:
        state = "normal"
    return {
        "ratio_vs_prior_5d": rounded(ratio5),
        "ratio_vs_prior_20d": rounded(ratio20),
        "percentile_vs_prior_60d": rounded(volume_percentile),
        "percentile_60d": rounded(volume_percentile),
        "deprecated_fields": {"percentile_60d": "Use percentile_vs_prior_60d. Planned removal in 0.2.0."},
        "avg_volume_positive_return_days": rounded(avg_positive),
        "avg_volume_negative_return_days": rounded(avg_negative),
        "state": state,
        "thresholds": {
            "high": "ratio_vs_prior_20d >= 2.0 or percentile_vs_prior_60d >= 0.90",
            "above_average": "ratio_vs_prior_20d >= 1.2 or ratio_vs_prior_5d >= 1.2",
            "below_average": "ratio_vs_prior_20d <= 0.8 or ratio_vs_prior_5d <= 0.8",
        },
    }


def prior_range(bars: list[Bar], days: int) -> dict[str, float | None]:
    if len(bars) <= days:
        return {
            f"prior_{days}d_highest_close": None,
            f"prior_{days}d_lowest_close": None,
            f"prior_{days}d_highest_high": None,
            f"prior_{days}d_lowest_low": None,
        }
    window = bars[-1 - days:-1]
    return {
        f"prior_{days}d_highest_close": max(bar.close for bar in window),
        f"prior_{days}d_lowest_close": min(bar.close for bar in window),
        f"prior_{days}d_highest_high": max(bar.high for bar in window),
        f"prior_{days}d_lowest_low": min(bar.low for bar in window),
    }


def range_structure_section(bars: list[Bar]) -> dict[str, Any]:
    latest = bars[-1] if bars else None
    result: dict[str, Any] = {}
    for days in (20, 60):
        result.update(prior_range(bars, days))
    if latest is None or result["prior_20d_highest_close"] is None:
        result.update({"state": "insufficient_data"})
        return result
    high_close = result["prior_20d_highest_close"]
    low_close = result["prior_20d_lowest_close"]
    high_high = result["prior_20d_highest_high"]
    low_low = result["prior_20d_lowest_low"]
    assert high_close is not None and low_close is not None and high_high is not None and low_low is not None
    result["distance_to_prior_20d_high_close"] = rounded(latest.close / high_close - 1.0)
    result["distance_to_prior_20d_low_close"] = rounded(latest.close / low_close - 1.0)
    if result["prior_60d_highest_close"]:
        result["distance_to_prior_60d_high_close"] = rounded(latest.close / result["prior_60d_highest_close"] - 1.0)
        result["distance_to_prior_60d_low_close"] = rounded(latest.close / result["prior_60d_lowest_close"] - 1.0)
    else:
        result["distance_to_prior_60d_high_close"] = None
        result["distance_to_prior_60d_low_close"] = None

    close_breakout = latest.close > high_close
    close_breakdown = latest.close < low_close
    failed_breakout = latest.high > high_high and latest.close <= high_close
    intraday_recovery = latest.low < low_low and latest.close >= low_close
    if close_breakout:
        state = "close_breakout"
    elif close_breakdown:
        state = "close_breakdown"
    elif failed_breakout:
        state = "intraday_failed_breakout"
    elif intraday_recovery:
        state = "intraday_recovery"
    else:
        state = "inside_range"
    result.update({
        "broke_above_prior_20d_highest_close": close_breakout,
        "broke_below_prior_20d_lowest_close": close_breakdown,
        "intraday_high_broke_prior_high_but_close_fell_back": failed_breakout,
        "intraday_low_broke_prior_low_but_close_recovered": intraday_recovery,
        "state": state,
    })
    return {key: rounded(value) if isinstance(value, float) else value for key, value in result.items()}


def consecutive_count(values: list[bool]) -> int:
    count = 0
    for value in reversed(values):
        if not value:
            break
        count += 1
    return count


def ma_by_date(bars: list[Bar], period: int) -> dict[str, float]:
    return dict(moving_average_series(bars, period))


def sequence_section(bars: list[Bar]) -> dict[str, Any]:
    close_changes = [current.close - previous.close for previous, current in zip(bars, bars[1:])]
    up_flags = [value > 0 for value in close_changes]
    down_flags = [value < 0 for value in close_changes]
    ma20 = ma_by_date(bars, 20)
    above_ma20 = [bar.close > ma20[bar.date] for bar in bars if bar.date in ma20]
    below_ma20 = [bar.close < ma20[bar.date] for bar in bars if bar.date in ma20]
    latest_above = bool(above_ma20[-1]) if above_ma20 else False
    latest_below = bool(below_ma20[-1]) if below_ma20 else False
    previous_three = above_ma20[-4:-1] if len(above_ma20) >= 4 else []
    previous_three_below = below_ma20[-4:-1] if len(below_ma20) >= 4 else []

    highs_up = [current.high > previous.high for previous, current in zip(bars, bars[1:])]
    lows_up = [current.low > previous.low for previous, current in zip(bars, bars[1:])]
    highs_down = [current.high < previous.high for previous, current in zip(bars, bars[1:])]
    lows_down = [current.low < previous.low for previous, current in zip(bars, bars[1:])]
    return {
        "consecutive_up_days": consecutive_count(up_flags),
        "consecutive_down_days": consecutive_count(down_flags),
        "days_above_ma20": consecutive_count(above_ma20),
        "days_below_ma20": consecutive_count(below_ma20),
        "first_close_above_ma20_after_3_below": latest_above and len(previous_three_below) == 3 and all(previous_three_below),
        "first_close_below_ma20_after_3_above": latest_below and len(previous_three) == 3 and all(previous_three),
        "higher_high_sequence_count": consecutive_count(highs_up),
        "higher_low_sequence_count": consecutive_count(lows_up),
        "lower_high_sequence_count": consecutive_count(highs_down),
        "lower_low_sequence_count": consecutive_count(lows_down),
    }


def stddev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def true_ranges(
    bars: list[Bar],
    warnings: WarningCollector | None = None,
    use_verified_pre_close: bool = False,
) -> list[tuple[str, float]]:
    ranges: list[tuple[str, float]] = []
    for index, bar in enumerate(bars):
        previous_close, _ = previous_close_reference(bars, index, warnings, use_verified_pre_close)
        if previous_close:
            value = max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close))
        else:
            value = bar.high - bar.low
        ranges.append((bar.date, value))
    return ranges


def daily_range_ratios(bars: list[Bar]) -> list[tuple[str, float]]:
    ranges: list[tuple[str, float]] = []
    for previous, current in zip(bars, bars[1:]):
        ranges.append((current.date, (current.high - current.low) / previous.close))
    return ranges


def volatility_section(
    bars: list[Bar],
    returns_: list[tuple[str, float]],
    warnings: WarningCollector | None = None,
    use_verified_pre_close: bool = False,
) -> dict[str, Any]:
    latest_return = returns_[-1][1] if returns_ else None
    recent_returns = [value for _, value in returns_[-20:]]
    vol20 = stddev(recent_returns) if len(recent_returns) == 20 else None
    annualized = vol20 * math.sqrt(ANNUALIZATION_FACTOR) if vol20 is not None else None
    tr = true_ranges(bars, warnings, use_verified_pre_close)
    latest_tr = tr[-1][1] if tr else None
    atr14 = average([value for _, value in tr[-14:]]) if len(tr) >= 14 else None
    tr_vs_atr = latest_tr / atr14 if latest_tr is not None and atr14 else None
    abs_returns = [abs(value) for _, value in returns_[-60:]]
    abs_return_percentile = percentile(abs_returns, abs(latest_return), 20) if latest_return is not None else None
    range_pairs = daily_range_ratios(bars)[-60:]
    ranges = [value for _, value in range_pairs]
    latest_range_ratio = ranges[-1] if ranges else None
    range_percentile = percentile(ranges, latest_range_ratio, 20) if latest_range_ratio is not None else None
    abs_high = abs_return_percentile is not None and abs_return_percentile >= 0.9
    tr_high = (tr_vs_atr is not None and tr_vs_atr >= 1.8) or (range_percentile is not None and range_percentile >= 0.9)
    if abs_high and tr_high:
        abnormal = "both"
    elif abs_high:
        abnormal = "absolute_return_unusually_high"
    elif tr_high:
        abnormal = "true_range_unusually_high"
    elif latest_return is None or (abs_return_percentile is None and tr_vs_atr is None and range_percentile is None):
        abnormal = "insufficient_data"
    else:
        abnormal = "none"
    return {
        "return_volatility_20d": rounded(vol20),
        "annualized_volatility_20d": rounded(annualized),
        "annualization_factor": ANNUALIZATION_FACTOR,
        "true_range": rounded(latest_tr),
        "atr14": rounded(atr14),
        "true_range_vs_atr14": rounded(tr_vs_atr),
        "latest_absolute_return_percentile_60d": rounded(abs_return_percentile),
        "latest_daily_range_percentile_60d": rounded(range_percentile),
        "daily_range_percentile_observations": len(ranges),
        "abnormal_move": abnormal,
        "thresholds": {
            "absolute_return_unusually_high": "latest absolute return percentile >= 0.90 over available recent returns",
            "true_range_unusually_high": "true_range_vs_atr14 >= 1.80 or daily range percentile >= 0.90",
        },
    }


def gap_section(
    bars: list[Bar],
    candle: dict[str, Any],
    warnings: WarningCollector | None = None,
    use_verified_pre_close: bool = False,
) -> dict[str, Any]:
    if len(bars) < 2:
        return {"type": "insufficient_data", "opening_gap_return": None, "fill_status": None}
    latest = bars[-1]
    previous = bars[-2]
    reference_close, reference_source = previous_close_reference(
        bars, len(bars) - 1, warnings, use_verified_pre_close
    )
    if reference_close is None:
        return {
            "type": "insufficient_data",
            "opening_gap_return": None,
            "fill_status": None,
            "previous_close_source": reference_source,
        }
    opening_gap_return = latest.open / reference_close - 1.0
    if latest.low > previous.high:
        gap_type = "full_upward_gap"
    elif latest.high < previous.low:
        gap_type = "full_downward_gap"
    elif opening_gap_return > 0:
        gap_type = "opening_gap_up"
    elif opening_gap_return < 0:
        gap_type = "opening_gap_down"
    else:
        gap_type = "none"
    fill_status = None
    if opening_gap_return > 0:
        fill_status = "substantially_filled" if latest.low <= reference_close + (latest.open - reference_close) * 0.25 else "not_filled"
    elif opening_gap_return < 0:
        fill_status = "substantially_filled" if latest.high >= reference_close + (latest.open - reference_close) * 0.25 else "not_filled"
    return {
        "type": gap_type,
        "opening_gap_return": rounded(opening_gap_return),
        "previous_close_source": reference_source,
        "fill_status": fill_status,
        "gap_up_closed_weakly": opening_gap_return > 0 and candle.get("close_zone") == "near_low",
        "gap_down_recovered_strongly": opening_gap_return < 0 and candle.get("close_zone") == "near_high",
    }


def aligned_period_return(bars: list[Bar], common_dates: list[str], days: int) -> float | None:
    by_date = {bar.date: bar.close for bar in bars}
    if len(common_dates) <= days:
        return None
    end = common_dates[-1]
    start = common_dates[-1 - days]
    return by_date[end] / by_date[start] - 1.0


def quality_limitations(quality: dict[str, Any]) -> list[str]:
    limitations: list[str] = []
    if quality.get("status") == QUALITY_USABLE:
        limitations.append("comparison data is usable with limitations")
    if quality.get("price_data_status") == QUALITY_USABLE:
        limitations.append("comparison price data is usable with limitations")
    if quality.get("volume_data_status") == QUALITY_USABLE:
        limitations.append("comparison volume data is usable with limitations")
    return limitations


def score_relative_strength(value: float | None) -> int | None:
    if value is None:
        return None
    if value >= 0.05:
        return 2
    if value >= 0.02:
        return 1
    if value <= -0.05:
        return -2
    if value <= -0.02:
        return -1
    return 0


def relative_strength_one(stock: list[Bar], other: list[Bar], quality: dict[str, Any]) -> dict[str, Any]:
    common = sorted(set(bar.date for bar in stock) & set(bar.date for bar in other))
    result: dict[str, Any] = {
        "common_observations": len(common),
        "data_quality_status": quality.get("status"),
        "price_data_status": quality.get("price_data_status"),
        "volume_data_status": quality.get("volume_data_status"),
        "limitations": quality_limitations(quality),
        "warning_counts": quality.get("warning_counts", {}),
        "warning_examples": quality.get("warning_examples", []),
    }
    if quality.get("price_data_status") == QUALITY_INSUFFICIENT:
        result["limitations"].append("comparison price data is insufficient; relative returns are not calculated")
        for days in (1, 5, 20):
            result[f"return_{days}d_difference"] = None
        return result
    for days in (1, 5, 20):
        stock_ret = aligned_period_return(stock, common, days)
        other_ret = aligned_period_return(other, common, days)
        result[f"return_{days}d_difference"] = rounded(stock_ret - other_ret if stock_ret is not None and other_ret is not None else None)
    return result


def unavailable_relative_strength(reason: str) -> dict[str, Any]:
    return {
        "common_observations": 0,
        "data_quality_status": QUALITY_INSUFFICIENT,
        "price_data_status": QUALITY_INSUFFICIENT,
        "volume_data_status": None,
        "limitations": [reason],
        "return_1d_difference": None,
        "return_5d_difference": None,
        "return_20d_difference": None,
        "warning_counts": {"comparison_data_unusable": 1},
        "warning_examples": [{"reason": "comparison_data_unusable", "detail": reason}],
    }


def relative_strength_section(
    stock: list[Bar],
    benchmark: Path | None,
    sector: Path | None,
    adjustment: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "benchmark": None,
        "sector": None,
        "benchmark_relative_strength_score": None,
        "sector_relative_strength_score": None,
        "relative_strength_conflict": False,
    }
    if benchmark is not None:
        try:
            bars, quality = load_bars(benchmark, adjustment)
            result["benchmark"] = relative_strength_one(stock, bars, quality)
            result["benchmark_relative_strength_score"] = score_relative_strength(
                result["benchmark"].get("return_20d_difference")
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            result["benchmark"] = unavailable_relative_strength(f"{benchmark.name}: {type(exc).__name__}")
    if sector is not None:
        try:
            bars, quality = load_bars(sector, adjustment)
            result["sector"] = relative_strength_one(stock, bars, quality)
            result["sector_relative_strength_score"] = score_relative_strength(
                result["sector"].get("return_20d_difference")
            )
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            result["sector"] = unavailable_relative_strength(f"{sector.name}: {type(exc).__name__}")
    benchmark_score = result.get("benchmark_relative_strength_score")
    sector_score = result.get("sector_relative_strength_score")
    result["relative_strength_conflict"] = (
        benchmark_score is not None
        and sector_score is not None
        and benchmark_score * sector_score < 0
    )
    return result


def score_from_trend(state: str) -> int | None:
    return {
        "strong_uptrend": 2,
        "uptrend": 1,
        "mixed": 0,
        "downtrend": -1,
        "strong_downtrend": -2,
        "insufficient_data": None,
    }.get(state)


def price_volume_score(
    range_structure: dict[str, Any],
    candle: dict[str, Any],
    volume: dict[str, Any],
    latest_return: float | None,
) -> tuple[int | None, list[str]]:
    volume_state = volume.get("state")
    range_state = range_structure.get("state")
    close_zone = candle.get("close_zone")
    if volume_state == "insufficient_data" or latest_return is None:
        return None, ["price_volume:insufficient_volume_or_return_data"]
    high_volume = volume_state == "high"
    above_volume = volume_state in {"high", "above_average"}
    low_volume = volume_state == "below_average"
    if range_state == "close_breakdown" and above_volume:
        return -2 if high_volume else -1, ["price_volume:breakdown_with_above_average_volume"]
    if latest_return < 0 and close_zone == "near_low" and high_volume:
        return -2, ["price_volume:high_volume_down_day"]
    if range_state == "intraday_failed_breakout" and above_volume:
        score = -2 if close_zone == "near_low" or high_volume else -1
        return score, ["price_volume:failed_breakout_with_above_average_volume"]
    if range_state == "close_breakout" and above_volume:
        return 2 if high_volume else 1, ["price_volume:breakout_with_above_average_volume"]
    if latest_return > 0 and close_zone == "near_high" and above_volume:
        return 2 if high_volume else 1, ["price_volume:up_day_closing_near_high_with_volume"]
    if latest_return < 0 and low_volume:
        return 0, ["price_volume:low_volume_pullback"]
    if latest_return > 0 and low_volume:
        return 0, ["price_volume:low_volume_up_day"]
    return 0, ["price_volume:neutral_price_volume_interaction"]


def classify_technical(scores: list[int]) -> tuple[str, float | None]:
    if len(scores) < 2:
        return "insufficient_data", None
    avg_score = sum(scores) / len(scores)
    if avg_score >= 1.2:
        return "constructive", avg_score
    if avg_score >= 0.4:
        return "slightly_constructive", avg_score
    if avg_score <= -1.2:
        return "weak", avg_score
    if avg_score <= -0.4:
        return "slightly_weak", avg_score
    return "mixed", avg_score


def classify_relative(scores: list[int | None], conflict: bool) -> tuple[str, float | None]:
    available = [score for score in scores if score is not None]
    if not available:
        return "insufficient_data", None
    if conflict:
        return "mixed", sum(available) / len(available)
    avg_score = sum(available) / len(available)
    if avg_score >= 1.5:
        return "outperforming", avg_score
    if avg_score > 0:
        return "slightly_outperforming", avg_score
    if avg_score <= -1.5:
        return "underperforming", avg_score
    if avg_score < 0:
        return "slightly_underperforming", avg_score
    return "mixed", avg_score


def overall_interpretation(technical: str, relative: str, conflict: bool) -> str:
    if technical == "insufficient_data" and relative == "insufficient_data":
        return "insufficient_technical_and_relative_data"
    if technical == "insufficient_data":
        return f"technical_structure_insufficient_relative_context_{relative}"
    if relative == "insufficient_data":
        return f"technical_structure_{technical}_relative_context_insufficient"
    if conflict:
        return f"technical_structure_{technical}_relative_signals_mixed"
    return f"technical_structure_{technical}_relative_context_{relative}"


def add_evidence(target: dict[str, list[str]], category: str, values: list[str] | tuple[str, ...]) -> None:
    clean = [value for value in values if value and value != "None"]
    if clean:
        target.setdefault(category, []).extend(clean)


def structural_summary(
    trend: dict[str, Any],
    range_structure: dict[str, Any],
    candle: dict[str, Any],
    volume: dict[str, Any],
    relative_strength: dict[str, Any],
    latest_return: float | None,
) -> dict[str, Any]:
    trend_score = score_from_trend(str(trend.get("state")))
    range_state = range_structure.get("state")
    if range_state == "close_breakout":
        price_score = 2
    elif range_state == "intraday_recovery":
        price_score = 1
    elif range_state == "close_breakdown":
        price_score = -2
    elif range_state == "intraday_failed_breakout":
        price_score = -1
    elif range_state == "inside_range":
        price_score = 0
    else:
        price_score = None
    if price_score is not None and candle.get("close_zone") == "near_high":
        price_score = min(2, price_score + 1)
    if price_score is not None and candle.get("close_zone") == "near_low":
        price_score = max(-2, price_score - 1)

    pv_score, pv_evidence = price_volume_score(range_structure, candle, volume, latest_return)
    benchmark_rs_score = relative_strength.get("benchmark_relative_strength_score")
    sector_rs_score = relative_strength.get("sector_relative_strength_score")
    technical_scores = [score for score in (trend_score, price_score, pv_score) if score is not None]
    technical_classification, technical_average = classify_technical(technical_scores)
    relative_conflict = bool(relative_strength.get("relative_strength_conflict"))
    relative_classification, relative_average = classify_relative(
        [benchmark_rs_score, sector_rs_score], relative_conflict
    )
    evidence: dict[str, list[str]] = {}
    add_evidence(evidence, "trend", trend.get("evidence", []))
    if range_state:
        add_evidence(evidence, "price_action", [f"range:{range_state}"])
    add_evidence(evidence, "price_volume", pv_evidence)
    relative_evidence: list[str] = []
    if benchmark_rs_score is not None:
        relative_evidence.append(
            "relative_strength:benchmark_outperformance"
            if benchmark_rs_score > 0
            else "relative_strength:benchmark_underperformance"
            if benchmark_rs_score < 0
            else "relative_strength:benchmark_neutral"
        )
    if sector_rs_score is not None:
        relative_evidence.append(
            "relative_strength:sector_outperformance"
            if sector_rs_score > 0
            else "relative_strength:sector_underperformance"
            if sector_rs_score < 0
            else "relative_strength:sector_neutral"
        )
    if relative_conflict:
        relative_evidence.append("relative_strength:mixed_benchmark_sector")
    add_evidence(evidence, "relative_context", relative_evidence)
    evidence_flat = [item for values in evidence.values() for item in values]
    relative_sources = [
        name
        for name, score in (("benchmark", benchmark_rs_score), ("sector", sector_rs_score))
        if score is not None
    ]
    technical_structure = {
        "trend_score": trend_score,
        "price_action_score": price_score,
        "price_volume_score": pv_score,
        "classification": technical_classification,
        "average_score": rounded(technical_average),
        "available_dimensions": len(technical_scores),
        "classification_rule": "average of available trend, price_action, and price_volume scores; require at least two dimensions",
    }
    relative_context = {
        "benchmark_relative_strength_score": benchmark_rs_score,
        "sector_relative_strength_score": sector_rs_score,
        "classification": relative_classification,
        "average_score": rounded(relative_average),
        "conflict": relative_conflict,
        "sources": relative_sources,
        "based_on_single_comparison": len(relative_sources) == 1,
        "classification_rule": "relative scores use +/-2% and +/-5% 20d thresholds; one source may classify with a single-source flag; conflicts classify as mixed",
    }
    return {
        "technical_structure": technical_structure,
        "relative_context": relative_context,
        "overall_interpretation": overall_interpretation(
            technical_classification, relative_classification, relative_conflict
        ),
        "trend_score": trend_score,
        "price_action_score": price_score,
        "price_volume_score": pv_score,
        "benchmark_relative_strength_score": benchmark_rs_score,
        "sector_relative_strength_score": sector_rs_score,
        "relative_strength_conflict": relative_conflict,
        "classification": technical_classification,
        "scoring_rules": {
            "trend_score": "strong_uptrend=2, uptrend=1, mixed=0, downtrend=-1, strong_downtrend=-2",
            "price_action_score": "range breakout/recovery/breakdown state adjusted one step by latest close zone",
            "price_volume_score": "price-volume interaction only; high-volume down days and failed breakouts are negative, low-volume pullbacks are neutral",
            "benchmark_relative_strength_score": "20d stock return minus benchmark return: +/-2% and +/-5% thresholds",
            "sector_relative_strength_score": "20d stock return minus sector return: +/-2% and +/-5% thresholds",
            "technical_classification": "constructive >= 1.2, slightly_constructive >= 0.4, mixed between -0.4 and 0.4, slightly_weak <= -0.4, weak <= -1.2; at least two technical dimensions required",
            "relative_classification": "outperforming >= 1.5, slightly_outperforming > 0, mixed = 0 or conflicting sources, slightly_underperforming < 0, underperforming <= -1.5",
        },
        "evidence": evidence,
        "evidence_flat": evidence_flat,
        "deprecated_fields": {
            "classification": "Use technical_structure.classification.",
            "trend_score": "Use technical_structure.trend_score.",
            "price_action_score": "Use technical_structure.price_action_score.",
            "price_volume_score": "Use technical_structure.price_volume_score.",
            "benchmark_relative_strength_score": "Use relative_context.benchmark_relative_strength_score.",
            "sector_relative_strength_score": "Use relative_context.sector_relative_strength_score.",
        },
    }


def assert_no_absolute_paths(value: Any) -> None:
    if isinstance(value, dict):
        for child in value.values():
            assert_no_absolute_paths(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_absolute_paths(child)
    elif isinstance(value, str):
        if os.path.isabs(value) or re.match(r"^[A-Za-z]:[\\/]", value):
            raise ValueError("Output contains an absolute path")


def calculate_features(
    stock_path: Path,
    adjustment: str = "unknown",
    benchmark: Path | None = None,
    sector: Path | None = None,
    pre_close_adjustment_verified: bool = False,
) -> dict[str, Any]:
    if adjustment not in ALLOWED_ADJUSTMENTS:
        raise ValueError(f"Unsupported adjustment: {adjustment}")
    bars, quality = load_bars(stock_path, adjustment)
    pre_close_policy = {
        "verified_for_full_series": pre_close_adjustment_verified,
        "default_source": "verified_pre_close" if pre_close_adjustment_verified else "previous_bar_close",
        "description": (
            "pre_close may be used across the full series only because the caller asserted a consistent adjustment basis"
            if pre_close_adjustment_verified
            else "previous-bar close is preferred; pre_close is used only when no previous bar exists"
        ),
    }
    if not bars:
        result = {
            "schema_version": SCHEMA_VERSION,
            "as_of_date": None,
            "adjustment": adjustment,
            "data_quality": quality,
            "returns": {},
            "moving_averages": {},
            "trend": {"state": "insufficient_data", "evidence": []},
            "latest_candle": {},
            "volume": {"state": "insufficient_data"},
            "range_structure": {"state": "insufficient_data"},
            "sequence": {},
            "volatility": {"abnormal_move": "insufficient_data"},
            "gap": {"type": "insufficient_data"},
            "relative_strength": {"benchmark": None, "sector": None},
            "structural_summary": {
                "technical_structure": {"classification": "insufficient_data"},
                "relative_context": {"classification": "insufficient_data"},
                "overall_interpretation": "insufficient_technical_and_relative_data",
                "classification": "insufficient_data",
            },
            "pre_close_policy": pre_close_policy,
        }
        assert_no_absolute_paths(result)
        return result

    returns_ = daily_returns(bars)
    runtime_warnings = WarningCollector({}, [])
    ma = moving_averages_section(bars)
    trend = trend_section(bars, ma, quality["status"])
    candle = latest_candle_section(bars, runtime_warnings, pre_close_adjustment_verified)
    volume = volume_section(bars, returns_, quality["volume_data_status"])
    ranges = range_structure_section(bars)
    sequence = sequence_section(bars)
    volatility = volatility_section(bars, returns_, runtime_warnings, pre_close_adjustment_verified)
    gap = gap_section(bars, candle, runtime_warnings, pre_close_adjustment_verified)
    relative_strength = relative_strength_section(bars, benchmark, sector, adjustment)
    latest_return = returns_[-1][1] if returns_ else None
    summary = structural_summary(trend, ranges, candle, volume, relative_strength, latest_return)
    merge_warning_summary(quality, runtime_warnings)
    result = {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": bars[-1].date,
        "adjustment": adjustment,
        "data_quality": quality,
        "pre_close_policy": pre_close_policy,
        "returns": returns_section(bars),
        "moving_averages": ma,
        "trend": trend,
        "latest_candle": candle,
        "volume": volume,
        "range_structure": ranges,
        "sequence": sequence,
        "volatility": volatility,
        "gap": gap,
        "relative_strength": relative_strength,
        "structural_summary": summary,
        "interpretation_limits": [
            "K-line features are deterministic structural evidence, not a price forecast.",
            "The script does not output trading recommendations, target prices, or next-session direction.",
        ],
    }
    assert_no_absolute_paths(result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("stock", type=Path)
    parser.add_argument("--benchmark", type=Path)
    parser.add_argument("--sector", type=Path)
    parser.add_argument("--adjustment", choices=sorted(ALLOWED_ADJUSTMENTS), default="unknown")
    parser.add_argument(
        "--pre-close-adjustment-verified",
        action="store_true",
        help="Allow pre_close to be used when metadata confirms it shares the same adjustment basis.",
    )
    args = parser.parse_args()
    result = calculate_features(
        args.stock,
        adjustment=args.adjustment,
        benchmark=args.benchmark,
        sector=args.sector,
        pre_close_adjustment_verified=args.pre_close_adjustment_verified,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
