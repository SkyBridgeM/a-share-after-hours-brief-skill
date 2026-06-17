---
name: a-share-after-hours-brief
description: Generate one-stock or multi-stock A-share after-hours review briefs as polished mobile-friendly HTML attachments with optional Gmail summary drafts and portable JSON history. Use for requests like “复盘今天的宁德时代”, “今天A股股票A和股票B盘后总结”, “股票池盘后HTML简报”, “校验上次判断”, “Gmail草稿”, “近60日相关性”, or event-triggered A-share updates.
---

# A 股个股盘后复盘

Create a practical Chinese after-hours review for one or more specified A-share stocks: what changed today, whether the thesis changed, how the previous judgment held up, and whether next-session direction is assessable. This is not a full-market debrief. Default output is a polished mobile-friendly `.html` attachment; Gmail delivery uses a short plain summary body and attaches the HTML only when the Gmail tool confirms attachment support.

## Defaults

- Timezone: use Asia/Shanghai for A-share report dates and generated timestamps unless the user explicitly specifies another timezone. Store `generated_at` as ISO 8601 with offset, for example `2026-06-17T16:30:00+08:00`.
- Report date: use the user-specified date; otherwise use today's date in the report timezone. Convert relative dates such as `昨天` or `上周五` into concrete dates and show the date in the report.
- Output path: if the user does not specify one, save under `reports/` in the current workspace with a date-and-stock filename.
- Length: standard multi-stock brief is 2-4 HTML pages; use 1-2 pages only when the user asks for a short version.
- Correlation: compare the user-specified pair; if omitted, compare the first two stocks and label the assumption.
- History: `history=on`, `compare_previous=true`. Save JSON under `<HTML output directory>/history/` unless `history_dir` is supplied.
- Position review: enable only when the user provides holdings/trades or explicitly asks for discipline review.
- Gmail: create drafts by default when requested; never send until the user explicitly authorizes sending and gives recipients. Do not put rich HTML in the Gmail body. Confirm attachment capability before claiming the HTML file was attached.
- Notion: do not sync.

## Dependencies

- Read `references/data-providers.md` for required financial data capabilities and provider labeling.
- Prefer `wind-mcp-skill` for A-share prices, K-line data, announcements, news, company events, and financial facts. Use `wind-find-finance-skill` if required capabilities or routing are uncertain.
- Do not replace unavailable financial facts with web search or model memory. Web/current news and Agent Reach are supplemental for external industry and supply-chain context only.
- Use Gmail tools only for summary drafts/sending. Treat draft creation and attachment upload as separately verified actions.

## Workflow

1. **Scope**
   - Identify stocks, report date, output HTML path, optional Gmail recipients, optional correlation pair, history options, and whether position review is triggered.

2. **Financial data**
   - Use request tiers to protect quota. Start with Tier 1 and escalate only when triggered.
   - Read `references/data-providers.md` before selecting a provider. Label the provider used for price/K-line, announcements, financial facts, benchmark context, and news.
   - Read `references/wind-data.md` before selecting Wind fields or calling Wind CLI.
   - Fetch a compact broad-market benchmark and a relevant sector/style benchmark. Market data is context for the specified stocks, not a full-market review.
   - Fetch enough daily K-line context to support the next-session assessment for each stock. Prefer recent daily K-line data when price structure cannot be judged from compact snapshot fields alone.
   - When sufficient K-line rows are available, read `references/kline-analysis.md` and run `scripts/kline_features.py` instead of manually estimating moving averages, candle structure, volume ratios, breakouts, volatility, or relative strength.
   - Use K-line data for the correlation pair and calculate return correlation locally.
   - Treat K-line data quality by dimension. If `price_data_status` is usable but `volume_data_status` is insufficient, price structure may still be discussed, but volume and price-volume conclusions must be marked insufficient.

3. **Previous review**
   - Read `references/history-and-review.md`.
   - Use `scripts/review_journal.py lookup` before writing the report when history and comparison are enabled.
   - Surface malformed-history warnings from lookup/build output. Do not hide skipped invalid files.
   - For each overlapping stock, evaluate the previous record's confirmation and invalidation conditions from current provider-backed facts. Mark each condition `met`, `not_met`, or `unknown`; never infer missing facts.
   - Use `scripts/review_journal.py build` to calculate the final review status and atomically save the current JSON record.

4. **Industry news**
   - Use web/current news only as supplemental context when industry or supply-chain news may affect the brief.
   - For each stock, identify the company's value-chain position before selecting news: upstream inputs/supply, the company's own segment, downstream demand/customers/channels, and close peers/substitutes.
   - Prioritize news that changes costs, supply, prices, orders, demand, policy constraints, or customer/peer expectations. Avoid broad industry news that cannot be tied to the specified stock's value chain.
   - Cite links for material external news.
   - Read `references/industry-news.md` when using external industry news.

5. **Major events**
   - Check announcements, news, earnings, meeting notes, abnormal moves, and policy/industry shocks.
   - Call event skills only when trigger conditions are met; do not expand routine disclosures.
   - Read `references/event-triggers.md` before invoking event skills.

6. **Correlation**
   - Use provider-backed K-line series; calculate correlation locally from aligned daily returns.
   - Use `scripts/correlation.py` when K-line data is saved as JSON/CSV.
   - If common return observations are fewer than 30, report sample insufficiency and avoid a directional conclusion.

7. **Next-session assessment**
   - For each stock, separate assessability from direction using `next_session_assessment`.
   - If evidence is sufficient, set `assessment_status: "assessable"` and choose exactly one tendency: `向上`, `维持震荡`, or `向下`.
   - If evidence is insufficient, set `assessment_status: "insufficient_evidence"`, set `tendency: null`, and use `confidence: "偏低"`. Do not use `维持震荡` merely because data is missing.
   - Make the assessment visually and textually obvious in the report, ideally as a pill/tag near the stock name and again in the next-session section.
   - Base the tendency on two evidence groups:
     - K-line/price-volume evidence: use `scripts/kline_features.py` output where available; summarize trend state, close zone, volume state, range state, abnormal-move warning, price-volume interaction, and benchmark/sector relative strength.
     - Information/news evidence: announcements, earnings, guidance, policy/industry/supply-chain news, upstream cost/supply changes, downstream demand/order changes, company news, abnormal event, capital-market event, or absence of meaningful new information.
   - Treat K-line features as structured technical evidence, not a deterministic forecast. Do not infer missing K-line features.
   - If `data_quality.status` from `scripts/kline_features.py` is `insufficient`, the assessment should normally use `assessment_status: "insufficient_evidence"` and `tendency: null`.
   - If volume quality is insufficient, do not describe volume expansion, volume contraction, or price-volume confirmation as directional evidence. Say the volume side is not assessable.
   - When benchmark and sector relative strength conflict, describe it as mixed evidence. Prefer sector relative strength for stock-specific competitiveness and benchmark relative strength for market beta context.
   - A constructive technical structure without information-side support should not automatically become a high-confidence `向上` judgment. A weak technical structure without an identified catalyst or event should not become a deterministic `向下` judgment.
   - Use `维持震荡` when evidence is assessable but mixed, weak, or lacks a clear catalyst. Do not force `向上` or `向下` from a single noisy indicator.
   - Include a short confidence label: `偏高`, `中等`, or `偏低`.
   - Give 2-4 observable conditions for the next session: what would confirm the tendency, what would invalidate it, and what price/volume/news signal matters most.
   - Do not give exact target prices or treat the tendency as certainty. Phrase it as a conditional judgment based on current K-line and news evidence.

8. **Optional position review**
   - When triggered, compare the user's original thesis and exit conditions with current facts.
   - State whether an exit condition was triggered and whether the user reports executing it.
   - Do not invent position size, cost, exit conditions, or transactions.

9. **Write and deliver**
   - Use `references/html-email.md` for sections, length, HTML attachment, mobile layout, Gmail summary body, and attachment rules.
   - Use `assets/brief-template.html` for the polished HTML attachment.
   - Use `assets/plain-email-summary-template.md` for Gmail body.
   - If Gmail attachment upload is unsupported or unconfirmed, create only the plain-text draft when appropriate and state the local HTML output path.

## Verification

Before delivery, check:

- Stock codes, report date, price data, announcement/news dates, and source labeling.
- Data provider capabilities were available for all material conclusions; limitations are stated where capabilities were missing.
- Wind request tier discipline, when Wind is used, especially that Tier 3 was only used when triggered.
- If Tier 3 returned data, it appears in the stock analysis, next-session conditions, or risk caveat.
- Major-event skill use, if any, matches `references/event-triggers.md`.
- Correlation uses returns, not raw prices, and reports sample size.
- K-line feature output, when used, comes from `scripts/kline_features.py`; user-facing text summarizes only a concise subset and does not expose raw JSON keys.
- Previous-review conditions use current facts and valid IDs from the prior record.
- Industry/news analysis distinguishes upstream, own segment, downstream, and peer/substitute signals when those signals are material and available.
- History JSON conforms to schema version 1, stores `generated_at` with timezone offset, and contains no absolute paths, exact target prices, or deterministic prediction language.
- Each stock has a visible next-session assessment. Assessable stocks show one tendency from `向上` / `维持震荡` / `向下`; insufficient-evidence stocks show no tendency and explain missing evidence.
- User-facing HTML/Gmail does not expose internal condition IDs, raw provider field names, raw JSON keys, template variables, script names, or local absolute paths.
- Position review appears only when holdings/trades or an explicit request triggered it.
- HTML opens correctly, is readable on mobile, includes disclaimer, and uses the polished attachment template.
- Gmail draft, if created, has a readable plain summary body. Claim an HTML attachment only when attachment upload was confirmed; do not imply the email was sent.
