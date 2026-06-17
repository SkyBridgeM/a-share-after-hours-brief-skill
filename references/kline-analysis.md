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

## Feature formulas

- Period returns use trading observations: `latest_close / close_n_observations_ago - 1`.
- Moving averages are simple close averages over 5, 10, 20, and 60 observations.
- MA slope is the percentage change in the moving average over the last five available MA observations.
- Close location is `(close - low) / (high - low)`. Zero-range candles return null ratios and `close_zone: "zero_range"`.
- Volume ratios compare latest volume with prior 5-day and prior 20-day average volume, excluding the latest day.
- Historical percentiles use the rank of the latest value within the available recent window. Volume percentile requires 60 volume observations; volatility/range percentiles require at least 20 observations.
- Prior range levels exclude the latest day.
- True range is `max(high-low, abs(high-prev_close), abs(low-prev_close))`.
- ATR14 is the average of the latest 14 true ranges.
- 20-day volatility is the sample standard deviation of the latest 20 daily returns. Annualized volatility uses `sqrt(252)`.
- Relative strength uses aligned trading dates only. It reports stock return minus benchmark or sector return for 1, 5, and 20 trading observations when available.

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

The script reports component scores from -2 to +2:

- `trend_score`: strong uptrend 2, uptrend 1, mixed 0, downtrend -1, strong downtrend -2.
- `price_action_score`: range breakout/recovery/breakdown state adjusted one step by the latest close zone.
- `volume_score`: high 2, above-average 1, normal 0, below-average -1.
- `relative_strength_score`: 20-day relative return difference uses +/-2% and +/-5% thresholds.

Missing dimensions remain null rather than becoming neutral. Aggregate classifications are descriptive: `constructive`, `slightly_constructive`, `mixed`, `slightly_weak`, `weak`, or `insufficient_data`.

## Report usage

Use the script output as one evidence source in the final review. A constructive technical structure without information-side support should not automatically become a high-confidence upward assessment. A weak technical structure without an identified catalyst or event should not become a deterministic downward assessment.

In polished HTML or Gmail summaries, show only a concise subset: trend state, close zone, volume state, range state, abnormal-move warning, relative strength, and 2-4 plain-language evidence points. Do not expose raw JSON keys or every calculated metric.
