# Wind Data Notes

Use `wind-mcp-skill` for A-share行情、K线、公告、新闻、财务、事件、技术和风险数据. Do not replace these facts with web search or model memory.

## Default Fields

For each A-share, prefer one `stock_data.get_stock_price_indicators` call with only needed fields:

`中文简称`, `最新成交价`, `涨跌幅`, `成交量`, `成交额`, `换手率`, `量比`, `振幅`, `5日涨跌幅`, `10日涨跌幅`, `20日涨跌幅`.

Add `60日涨跌幅` only when medium-term context is needed. Verify exact field names against `wind-mcp-skill/references/indicators.md`.

Use:

- `financial_docs.get_company_announcements` for announcements/reports/disclosures.
- `financial_docs.get_financial_news` for news and market reports.
- `stock_data.get_stock_kline` for A-share daily K-line.
- `index_data.get_index_price_indicators` or `index_data.get_index_kline` for broad/sector index context.

## Next-Session Tendency Evidence

Every stock needs one next-session tendency: `向上`, `维持震荡`, or `向下`. Treat it as a conditional trading tendency, not a deterministic forecast.

Use two evidence groups:

- K-line/price-volume evidence: close position, daily return, volume/turnover/volume ratio, 5/10/20-day trend, recent high/low, support/resistance, gap, long upper/lower shadow, consecutive rise/fall, and relative strength versus market/sector when available.
- Information/news evidence: announcements, earnings, company news, policy/industry/supply-chain news, upstream cost/supply changes, downstream demand/order changes, peer/substitute signals, abnormal event, capital-market event, or explicit lack of meaningful new information.

Direction rules:

- `向上`: price-volume structure is constructive and news/catalyst is supportive or at least not contradictory. Examples include closing near the high after increased volume, reclaiming short-term averages, sector/stock relative strength, positive announcement/news, or clear risk release.
- `维持震荡`: K-line and information evidence are mixed, weak, catalyst-light, or mutually offsetting. This is the default when there is no clear edge.
- `向下`: price-volume structure is weak and news/risk is negative or not enough to offset weakness. Examples include failed rebound, closing near the low, breakdown below short-term support, heavy-volume selloff, sector drag, negative announcement/news, or unresolved risk event.

Always include a confidence label: `偏高`, `中等`, or `偏低`. Use `偏低` when K-line data is insufficient, news is stale, or market/sector context conflicts with the stock signal.

## Request Tiers

Protect Wind quota. Start with Tier 1 and escalate only when triggered.

### Tier 1: Default daily brief

Use for ordinary daily reports and multi-stock pools.

- Per stock: one compact price snapshot call.
- Per stock: concise date-scoped announcement/news check.
- Per stock: if compact fields are not enough to support the next-session tendency, add recent daily K-line data rather than guessing.
- For the report: K-line only for the specified correlation pair.
- Broad market index snapshot only when needed for overall context.

### Tier 2: Context and condition checks

Use when previous-review conditions or next-session watch items require time-series confirmation.

- Add `stock_data.get_stock_kline` for stocks needing K-line confirmation or a stronger next-session tendency, usually near 60 trading days ending at report date.
- Add one broad benchmark snapshot and one relevant style/sector benchmark when available.
- Prefer local calculations from K-line: 5/20/60-day trend, recent high/low, support/resistance, consecutive rise/fall, and return correlation.

### Tier 3: Triggered enrichment

Use only for abnormal movement, major event, unresolved condition checks, or explicit user request.

- `stock_data.get_stock_technicals` for MACD/KDJ/RSI/BOLL.
- `stock_data.get_risk_metrics` for beta/volatility/risk.
- Sector/theme index K-line or extra announcements/news beyond date scope.

Triggers include: daily move around 5%+, unusually high turnover/volume ratio, sharp divergence from market/sector, major announcement/earnings/conference call, policy/news shock, or a previous condition that cannot be checked with Tier 1 data.

If Tier 3 is triggered and data is successfully fetched, include those indicators as explicit evidence in the stock analysis, condition check, or risk caveat. Do not leave fetched Tier 3 data unused.

## K-Line and Correlation

K-line params: `windcode` one stock only, `begin_date`/`end_date` as `yyyyMMdd`, `period: "10"` for daily K, `aftime: "0"` for forward-adjusted data when possible.

For two-stock correlation, call K-line separately for each stock, align common trading dates, convert close prices to daily returns, and calculate Pearson correlation locally. If common return observations are fewer than 30, report sample insufficiency.

## Market Context

Fetch compact context only:

- One broad benchmark relevant to the stock pool.
- One sector/style benchmark relevant to each stock where practical.
- Prefer `最新成交价`, `涨跌幅`, `成交额`, `上涨家数`, and `下跌家数` when supported for the selected index.
- Use context to classify the move as mainly market beta, sector influence, stock-specific, or mixed.

If a field is unavailable, continue with available data and state the limitation briefly only when it affects the conclusion.
