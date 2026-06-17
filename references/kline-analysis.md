# K-line Feature Analysis

Use `scripts/kline_features.py` when daily K-line data is available and the report needs price-volume structure, moving averages, range structure, candle features, volatility, or relative strength. The script is a deterministic feature engine. It does not forecast prices, assign next-session direction, produce target prices, or make trading recommendations.

## Commands

Basic usage:

```bash
python3 scripts/kline_features.py stock.json
```

With benchmark and sector relative strength:

```bash
python3 scripts/kline_features.py stock.json \
  --benchmark benchmark.json \
  --sector sector.json \
  --adjustment forward
```

Allowed `--adjustment` values: `forward`, `backward`, `none`, `unknown`. Default is `unknown`. Do not infer the adjustment basis unless the data source makes it explicit.

Use `--pre-close-adjustment-verified` only when metadata confirms that `pre_close` uses the same adjustment basis as the OHLC series. Without that flag, sequential calculations prefer the previous bar's close and only use `pre_close` when no previous bar exists.

## Input handling

The script reads JSON lists, JSON objects containing `data`, `rows`, `items`, or `result`, and CSV files.

Supported aliases include:

- Date: `date`, `trade_date`, `datetime`, `日期`, `交易日期`, `时间`.
- Open: `open`, `open_price`, `开盘价`, `开盘`.
- High: `high`, `high_price`, `最高价`, `最高`.
- Low: `low`, `low_price`, `最低价`, `最低`.
- Close: `close`, `close_price`, `收盘价`, `收盘`, `前复权收盘价`, `复权收盘价`.
- Volume: `volume`, `成交量`.
- Amount: `amount`, `turnover_amount`, `成交额`.
- Previous close: `pre_close`, `prev_close`, `前收盘价`, `昨收`.

Dates are normalized to `YYYY-MM-DD` from `YYYY-MM-DD`, `YYYYMMDD`, `YYYY/MM/DD`, or timestamps beginning with those forms. Rows are sorted chronologically. Duplicate dates are handled deterministically by keeping the last row and emitting a warning. Turnover rate is not treated as volume.

Data quality is reported separately for price and volume:

- `price_data_status`: `good`, `usable_with_limitations`, or `insufficient`.
- `volume_data_status`: `good` when final-series volume coverage is at least 95%, `usable_with_limitations` from 50% to below 95%, and `insufficient` below 50%.
- `volume_coverage_ratio`: final-series valid volume observations divided by final deduplicated price observations. The value is clamped to `[0, 1]`.

The overall `data_quality.status` uses the same enum: `good`, `usable_with_limitations`, or `insufficient`. It cannot be `good` when volume quality is not good. Price-only feature groups may still be usable when volume is incomplete, but volume-derived fields return null or `insufficient_data` when coverage is below 50%.

Diagnostics separate raw input from the final series:

- `raw_input.rows_read`, `raw_input.rows_skipped`, and `raw_input.raw_rows_missing_volume` describe incoming rows before duplicate-date resolution.
- `final_series.valid_rows`, `final_series.final_rows_missing_volume`, and `final_series.volume_coverage_ratio` describe the final deduplicated K-line series used for features.
- Top-level compatibility fields such as `rows_read`, `valid_rows`, `missing_volume_count`, `raw_rows_missing_volume`, and `final_rows_missing_volume` remain available in 0.1.x. `missing_volume_count` means final-series missing volume rows.

Warnings are aggregated as `warning_counts` and capped `warning_examples`; `warnings_truncated` marks omitted examples.

## Feature formulas

- Period returns use trading observations: `latest_close / close_n_observations_ago - 1`.
- Moving averages are simple close averages over 5, 10, 20, and 60 observations.
- MA slope is the percentage change in the moving average over the last five available MA observations.
- Close location is `(close - low) / (high - low)`. Zero-range candles return null ratios and `close_zone: "zero_range"`.
- Volume ratios compare latest volume with prior 5-day and prior 20-day average volume, excluding the latest day.
- `percentile_vs_prior_60d` compares the latest volume against the prior 60 valid volume observations and excludes the latest day. `percentile_60d` is retained as a deprecated compatibility alias for 0.1.x, with the deprecation note under `deprecated_fields`; planned removal is 0.2.0.
- Historical volatility/range percentiles use the rank of the latest value within the available recent window and require at least 20 observations.
- Prior range levels exclude the latest day.
- True range is `max(high-low, abs(high-previous_close), abs(low-previous_close))`. The previous close source is the previous K-line bar by default; `pre_close` is used only when no previous bar exists or when `--pre-close-adjustment-verified` is supplied.
- ATR14 is the average of the latest 14 true ranges.
- 20-day volatility is the sample standard deviation of the latest 20 daily returns. Annualized volatility uses `sqrt(252)`.
- Daily range percentile uses `(current_high - current_low) / previous_bar_close` for real previous-current pairs only. The first bar in a truncated window is not assigned a synthetic range ratio.
- Relative strength uses aligned trading dates only. It reports stock return minus benchmark and stock return minus sector return separately for 1, 5, and 20 trading observations when available. Optional comparison data that cannot be parsed is marked `insufficient` without failing the stock calculation. If comparison `price_data_status` is `insufficient`, relative-return differences and relative scores are null. If comparison data is `usable_with_limitations`, calculations may proceed when aligned observations are sufficient and limitations remain visible.

## Deterministic states

Trend states:

- `strong_uptrend`: close is above MA5/MA10/MA20, MA5 > MA10 > MA20, MA20 slope over five MA observations is above 0.5%, and close is more than 3% above MA20.
- `uptrend`: at least two of MA5/MA10/MA20 are below the close and MA20 slope is non-negative.
- `strong_downtrend`: close is below MA5/MA10/MA20, MA5 < MA10 < MA20, MA20 slope is below -0.5%, and close is more than 3% below MA20.
- `downtrend`: at least two of MA5/MA10/MA20 are above the close and MA20 slope is non-positive.
- `mixed`: evidence is assessable but not aligned.
- `insufficient_data`: data quality or sample length is not enough.

Candle thresholds:

- `near_high`: close location >= 0.75.
- `near_low`: close location <= 0.25.
- `middle`: between those thresholds.

Volume states:

- `high`: latest volume / prior 20-day average >= 2.0, or 60-day percentile >= 0.90.
- `above_average`: latest volume / prior 20-day average >= 1.2, or latest volume / prior 5-day average >= 1.2.
- `below_average`: latest volume / prior 20-day average <= 0.8, or latest volume / prior 5-day average <= 0.8.
- `normal`: available ratios do not meet those thresholds.
- `insufficient_data`: volume data is missing or too short.

Volume state is descriptive. It is not used as a direct positive or negative score. Directional technical scoring uses price-volume interaction instead:

- `price_volume_score` is positive when constructive price action is confirmed by above-average or high volume.
- High-volume down days, close breakdowns with volume, and failed breakouts with volume are negative.
- Low-volume pullbacks are neutral unless other price evidence is weak.
- Missing or insufficient volume leaves `price_volume_score` null.

Range states:

- `close_breakout`: latest close is above the prior 20-day highest close.
- `close_breakdown`: latest close is below the prior 20-day lowest close.
- `intraday_failed_breakout`: latest high is above the prior 20-day highest high but close is not above the prior 20-day highest close.
- `intraday_recovery`: latest low is below the prior 20-day lowest low but close is not below the prior 20-day lowest close.
- `inside_range`: none of the above.
- `insufficient_data`: fewer than 21 valid observations.

Abnormal move states:

- `absolute_return_unusually_high`: latest absolute return percentile >= 0.90.
- `true_range_unusually_high`: latest true range / ATR14 >= 1.80 or latest daily range percentile >= 0.90.
- `both`: both conditions are true.
- `none`: available evidence does not trigger an abnormal-move condition.
- `insufficient_data`: not enough return/range observations.

## Structural summary

The script separates absolute technical structure from relative-performance context. Relative strength does not directly change the absolute technical classification.

Technical structure uses only:

- `trend_score`: strong uptrend 2, uptrend 1, mixed 0, downtrend -1, strong downtrend -2.
- `price_action_score`: range breakout/recovery/breakdown state adjusted one step by the latest close zone.
- `price_volume_score`: price-volume interaction score; raw volume level is not scored by itself.

Technical classification averages the available technical scores and requires at least two available dimensions:

- `constructive`: average >= 1.2.
- `slightly_constructive`: average >= 0.4 and < 1.2.
- `mixed`: average > -0.4 and < 0.4.
- `slightly_weak`: average <= -0.4 and > -1.2.
- `weak`: average <= -1.2.
- `insufficient_data`: fewer than two technical dimensions.

Relative context uses:

- `benchmark_relative_strength_score`: 20-day stock return minus benchmark return, using +/-2% and +/-5% thresholds.
- `sector_relative_strength_score`: 20-day stock return minus sector return, using +/-2% and +/-5% thresholds.

Relative classification:

- `outperforming`: average relative score >= 1.5.
- `slightly_outperforming`: average relative score > 0 and < 1.5.
- `mixed`: score is 0 or benchmark and sector scores conflict.
- `slightly_underperforming`: average relative score < 0 and > -1.5.
- `underperforming`: average relative score <= -1.5.
- `insufficient_data`: no relative comparison score is available.

If only one relative source is available, `based_on_single_comparison` is true. Sector-relative performance is more stock-specific than benchmark-relative performance, but neither source is silently discarded.

Missing dimensions remain null rather than becoming neutral. `overall_interpretation` is a descriptive phrase combining the two layers; it is not a forecast.

When benchmark and sector relative strength conflict, use `relative_strength_conflict: true` as mixed evidence. Sector relative strength is the better signal for stock-specific competitiveness; benchmark relative strength is market beta context. Do not collapse one into the other in the written report.

Evidence is grouped by category under `structural_summary.evidence`: `trend`, `price_action`, `price_volume`, and `relative_context`. Raw evidence keys are for agent use; user-facing reports should translate them into natural Chinese.

## Report usage

Use the script output as one evidence source in the final review. A constructive technical structure without information-side support should not automatically become a high-confidence upward assessment. A weak technical structure without an identified catalyst or event should not become a deterministic downward assessment. Outperforming a falling market does not automatically mean the stock has a constructive absolute structure; underperforming a strong sector does not automatically mean the stock is in an absolute downtrend.

In polished HTML or Gmail summaries, show only a concise subset: technical structure, close zone, volume state or volume-data limitation, range state, abnormal-move warning, benchmark/sector relative context, and 2-4 plain-language evidence points. Do not expose raw JSON keys, deprecated raw field names, or every calculated metric.
