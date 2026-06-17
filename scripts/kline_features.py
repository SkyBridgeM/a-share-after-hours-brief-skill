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
    warnings: list[dict[str, str]] = []
    missing_ohlc = {"open": 0, "high": 0, "low": 0, "close": 0}
    missing_volume = 0
    invalid_price_rows = 0
    rows_skipped = 0
    previous_seen_date: str | None = None
    chronological_corrections = 0

    for row in rows:
        if not isinstance(row, dict):
            rows_skipped += 1
            warnings.append({"reason": "row is not an object"})
            continue
        row_date = normalize_date(pick(row, DATE_KEYS))
        if row_date is None:
            rows_skipped += 1
            warnings.append({"reason": "missing or malformed date"})
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
            warnings.append({"date": row_date, "reason": "missing or malformed OHLC"})
            continue
        assert open_ is not None and high is not None and low is not None and close is not None
        if high < max(open_, low, close) or low > min(open_, high, close):
            rows_skipped += 1
            invalid_price_rows += 1
            warnings.append({"date": row_date, "reason": "inconsistent OHLC range"})
            continue

        volume = parse_number(pick(row, VOLUME_KEYS), positive=False)
        if volume is None:
            missing_volume += 1
        elif volume < 0:
            volume = None
            missing_volume += 1
        amount = parse_number(pick(row, AMOUNT_KEYS), positive=False)
        pre_close = parse_number(pick(row, PRE_CLOSE_KEYS), positive=True)
        bar = Bar(row_date, open_, high, low, close, volume, amount, pre_close)
        if row_date in by_date:
            duplicate_dates.append(row_date)
            warnings.append({"date": row_date, "reason": "duplicate date; last row kept"})
        by_date[row_date] = bar

    bars = [by_date[key] for key in sorted(by_date)]
    quality = data_quality(
        rows_read=len(rows),
        bars=bars,
        rows_skipped=rows_skipped,
        duplicate_dates=sorted(set(duplicate_dates)),
        missing_ohlc=missing_ohlc,
        missing_volume=missing_volume,
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
    missing_volume: int,
    invalid_price_rows: int,
    chronological_corrections: int,
    adjustment: str,
    warnings: list[dict[str, str]],
) -> dict[str, Any]:
    valid_rows = len(bars)
    if valid_rows < 5:
        status = "insufficient"
    elif rows_skipped or valid_rows < 20 or missing_volume == rows_read:
        status = "usable_with_limitations"
    else:
        status = "good"
    return {
        "status": status,
        "rows_read": rows_read,
        "valid_rows": valid_rows,
        "rows_skipped": rows_skipped,
        "duplicate_dates": duplicate_dates,
        "missing_ohlc_counts": missing_ohlc,
        "missing_volume_count": missing_volume,
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
        "warnings": warnings,
    }


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
        evidence.append("close_above_ma5_ma10_ma20")
    if len(below) == 3:
        evidence.append("close_below_ma5_ma10_ma20")
    if ma["ma5"] and ma["ma10"] and ma["ma20"] and ma["ma5"] > ma["ma10"] > ma["ma20"]:
        evidence.append("ma5_above_ma10_above_ma20")
    if ma["ma5"] and ma["ma10"] and ma["ma20"] and ma["ma5"] < ma["ma10"] < ma["ma20"]:
        evidence.append("ma5_below_ma10_below_ma20")
    slope20 = ma.get("ma20_slope_5obs")
    if slope20 is not None and slope20 > 0:
        evidence.append("ma20_slope_positive")
    if slope20 is not None and slope20 < 0:
        evidence.append("ma20_slope_negative")

    close_vs_ma20 = ma.get("close_vs_ma20")
    if all(item in evidence for item in ("close_above_ma5_ma10_ma20", "ma5_above_ma10_above_ma20")) and slope20 and slope20 > 0.005 and close_vs_ma20 and close_vs_ma20 > 0.03:
        state = "strong_uptrend"
    elif len(above) >= 2 and slope20 is not None and slope20 >= 0:
        state = "uptrend"
    elif all(item in evidence for item in ("close_below_ma5_ma10_ma20", "ma5_below_ma10_below_ma20")) and slope20 and slope20 < -0.005 and close_vs_ma20 and close_vs_ma20 < -0.03:
        state = "strong_downtrend"
    elif len(below) >= 2 and slope20 is not None and slope20 <= 0:
        state = "downtrend"
    else:
        state = "mixed"
    return {"state": state, "evidence": evidence}


def latest_candle_section(bars: list[Bar]) -> dict[str, Any]:
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
    reference_close = latest.pre_close or (previous.close if previous else None)
    return {
        "close_location": rounded(close_location),
        "body_size": rounded(abs(latest.close - latest.open)),
        "body_ratio": rounded(body_ratio),
        "upper_shadow_size": rounded(latest.high - max(latest.open, latest.close)),
        "upper_shadow_ratio": rounded(upper_shadow_ratio),
        "lower_shadow_size": rounded(min(latest.open, latest.close) - latest.low),
        "lower_shadow_ratio": rounded(lower_shadow_ratio),
        "gap_from_previous_close": rounded(latest.open / reference_close - 1.0 if reference_close else None),
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


def volume_section(bars: list[Bar], returns_: list[tuple[str, float]]) -> dict[str, Any]:
    if not bars or bars[-1].volume is None:
        return {
            "ratio_vs_prior_5d": None,
            "ratio_vs_prior_20d": None,
            "percentile_60d": None,
            "avg_volume_positive_return_days": None,
            "avg_volume_negative_return_days": None,
            "state": "insufficient_data",
        }
    latest = bars[-1].volume
    assert latest is not None
    prior_volumes = [bar.volume for bar in bars[:-1] if bar.volume is not None]
    prior_5 = prior_volumes[-5:]
    prior_20 = prior_volumes[-20:]
    ratio5 = latest / average(prior_5) if len(prior_5) == 5 and average(prior_5) else None
    ratio20 = latest / average(prior_20) if len(prior_20) == 20 and average(prior_20) else None
    latest_60 = [bar.volume for bar in bars[-60:] if bar.volume is not None]
    volume_percentile = percentile(latest_60, latest, 60)

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
        "percentile_60d": rounded(volume_percentile),
        "avg_volume_positive_return_days": rounded(avg_positive),
        "avg_volume_negative_return_days": rounded(avg_negative),
        "state": state,
        "thresholds": {
            "high": "ratio_vs_prior_20d >= 2.0 or percentile_60d >= 0.90",
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


def true_ranges(bars: list[Bar]) -> list[tuple[str, float]]:
    ranges: list[tuple[str, float]] = []
    for index, bar in enumerate(bars):
        previous_close = bar.pre_close or (bars[index - 1].close if index > 0 else None)
        if previous_close:
            value = max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close))
        else:
            value = bar.high - bar.low
        ranges.append((bar.date, value))
    return ranges


def volatility_section(bars: list[Bar], returns_: list[tuple[str, float]]) -> dict[str, Any]:
    latest_return = returns_[-1][1] if returns_ else None
    recent_returns = [value for _, value in returns_[-20:]]
    vol20 = stddev(recent_returns) if len(recent_returns) == 20 else None
    annualized = vol20 * math.sqrt(ANNUALIZATION_FACTOR) if vol20 is not None else None
    tr = true_ranges(bars)
    latest_tr = tr[-1][1] if tr else None
    atr14 = average([value for _, value in tr[-14:]]) if len(tr) >= 14 else None
    tr_vs_atr = latest_tr / atr14 if latest_tr is not None and atr14 else None
    abs_returns = [abs(value) for _, value in returns_[-60:]]
    abs_return_percentile = percentile(abs_returns, abs(latest_return), 20) if latest_return is not None else None
    ranges = []
    for index, bar in enumerate(bars[-60:]):
        previous_close = bars[max(0, len(bars) - len(bars[-60:]) + index - 1)].close if len(bars) > 1 else None
        ranges.append((bar.high - bar.low) / previous_close if previous_close else 0)
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
        "abnormal_move": abnormal,
        "thresholds": {
            "absolute_return_unusually_high": "latest absolute return percentile >= 0.90 over available recent returns",
            "true_range_unusually_high": "true_range_vs_atr14 >= 1.80 or daily range percentile >= 0.90",
        },
    }


def gap_section(bars: list[Bar], candle: dict[str, Any]) -> dict[str, Any]:
    if len(bars) < 2:
        return {"type": "insufficient_data", "opening_gap_return": None, "fill_status": None}
    latest = bars[-1]
    previous = bars[-2]
    reference_close = latest.pre_close or previous.close
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


def relative_strength_one(stock: list[Bar], other: list[Bar]) -> dict[str, Any]:
    common = sorted(set(bar.date for bar in stock) & set(bar.date for bar in other))
    result: dict[str, Any] = {"common_observations": len(common)}
    for days in (1, 5, 20):
        stock_ret = aligned_period_return(stock, common, days)
        other_ret = aligned_period_return(other, common, days)
        result[f"return_{days}d_difference"] = rounded(stock_ret - other_ret if stock_ret is not None and other_ret is not None else None)
    return result


def relative_strength_section(
    stock: list[Bar],
    benchmark: Path | None,
    sector: Path | None,
    adjustment: str,
) -> dict[str, Any]:
    result = {"benchmark": None, "sector": None}
    if benchmark is not None:
        bars, _ = load_bars(benchmark, adjustment)
        result["benchmark"] = relative_strength_one(stock, bars)
    if sector is not None:
        bars, _ = load_bars(sector, adjustment)
        result["sector"] = relative_strength_one(stock, bars)
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


def structural_summary(
    trend: dict[str, Any],
    range_structure: dict[str, Any],
    candle: dict[str, Any],
    volume: dict[str, Any],
    relative_strength: dict[str, Any],
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

    volume_score = {
        "high": 2,
        "above_average": 1,
        "normal": 0,
        "below_average": -1,
        "insufficient_data": None,
    }.get(volume.get("state"))

    rs20 = None
    if relative_strength.get("benchmark") and relative_strength["benchmark"].get("return_20d_difference") is not None:
        rs20 = relative_strength["benchmark"]["return_20d_difference"]
    elif relative_strength.get("sector") and relative_strength["sector"].get("return_20d_difference") is not None:
        rs20 = relative_strength["sector"]["return_20d_difference"]
    if rs20 is None:
        rs_score = None
    elif rs20 >= 0.05:
        rs_score = 2
    elif rs20 >= 0.02:
        rs_score = 1
    elif rs20 <= -0.05:
        rs_score = -2
    elif rs20 <= -0.02:
        rs_score = -1
    else:
        rs_score = 0
    available = [score for score in (trend_score, price_score, volume_score, rs_score) if score is not None]
    if len(available) < 2:
        classification = "insufficient_data"
    else:
        avg_score = sum(available) / len(available)
        if avg_score >= 1.2:
            classification = "constructive"
        elif avg_score >= 0.4:
            classification = "slightly_constructive"
        elif avg_score <= -1.2:
            classification = "weak"
        elif avg_score <= -0.4:
            classification = "slightly_weak"
        else:
            classification = "mixed"
    return {
        "trend_score": trend_score,
        "price_action_score": price_score,
        "volume_score": volume_score,
        "relative_strength_score": rs_score,
        "classification": classification,
        "scoring_rules": {
            "trend_score": "strong_uptrend=2, uptrend=1, mixed=0, downtrend=-1, strong_downtrend=-2",
            "price_action_score": "range breakout/recovery/breakdown state adjusted one step by latest close zone",
            "volume_score": "high=2, above_average=1, normal=0, below_average=-1",
            "relative_strength_score": "20d relative return difference thresholds: +/-2% and +/-5%",
        },
        "evidence": [*trend.get("evidence", []), str(range_state), str(volume.get("state"))],
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
) -> dict[str, Any]:
    if adjustment not in ALLOWED_ADJUSTMENTS:
        raise ValueError(f"Unsupported adjustment: {adjustment}")
    bars, quality = load_bars(stock_path, adjustment)
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
            "structural_summary": {"classification": "insufficient_data"},
        }
        assert_no_absolute_paths(result)
        return result

    returns_ = daily_returns(bars)
    ma = moving_averages_section(bars)
    trend = trend_section(bars, ma, quality["status"])
    candle = latest_candle_section(bars)
    volume = volume_section(bars, returns_)
    ranges = range_structure_section(bars)
    sequence = sequence_section(bars)
    volatility = volatility_section(bars, returns_)
    gap = gap_section(bars, candle)
    relative_strength = relative_strength_section(bars, benchmark, sector, adjustment)
    summary = structural_summary(trend, ranges, candle, volume, relative_strength)
    result = {
        "schema_version": SCHEMA_VERSION,
        "as_of_date": bars[-1].date,
        "adjustment": adjustment,
        "data_quality": quality,
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
    args = parser.parse_args()
    result = calculate_features(
        args.stock,
        adjustment=args.adjustment,
        benchmark=args.benchmark,
        sector=args.sector,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
