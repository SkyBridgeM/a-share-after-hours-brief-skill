---
name: a-share-after-hours-brief
description: Generate one-stock or multi-stock A-share after-hours review briefs as polished mobile-friendly HTML attachments with optional Gmail summary drafts and portable JSON history. Use for requests like “复盘今天的宁德时代”, “今天A股股票A和股票B盘后总结”, “股票池盘后HTML简报”, “校验上次判断”, “Gmail草稿”, “近60日相关性”, or event-triggered A-share updates.
---

# A 股个股盘后复盘

Create a practical Chinese after-hours review for one or more specified A-share stocks: what changed today, whether the thesis changed, how the previous judgment held up, and what observable conditions matter next session. This is not a full-market debrief. Default output is a polished mobile-friendly `.html` attachment; Gmail delivery uses a short plain summary body plus the HTML attachment.

## Defaults

- Report date: use the user-specified date; otherwise use today's date. Convert relative dates such as `昨天` or `上周五` into concrete dates and show the date in the report.
- Output path: if the user does not specify one, save under `reports/` in the current workspace with a date-and-stock filename.
- Length: standard multi-stock brief is 2-4 HTML pages; use 1-2 pages only when the user asks for a short version.
- Correlation: compare the user-specified pair; if omitted, compare the first two stocks and label the assumption.
- History: `history=on`, `compare_previous=true`. Save JSON under `<HTML output directory>/history/` unless `history_dir` is supplied.
- Position review: enable only when the user provides holdings/trades or explicitly asks for discipline review.
- Gmail: create drafts by default; never send until the user explicitly authorizes sending and gives recipients. Do not put rich HTML in the Gmail body.
- Notion: do not sync.

## Dependencies

- Use `wind-find-finance-skill` if required financial capabilities or routing are uncertain.
- Use `wind-mcp-skill` for A-share prices, K-line data, announcements, news, company events, and financial facts. Do not replace Wind facts with web search or model memory.
- Use Gmail tools only for summary drafts/sending; attach the polished HTML file.

## Workflow

1. **Scope**
   - Identify stocks, report date, output HTML path, optional Gmail recipients, optional correlation pair, history options, and whether position review is triggered.

2. **Wind data**
   - Use request tiers to protect quota. Start with Tier 1 and escalate only when triggered.
   - Read `references/wind-data.md` before selecting Wind fields or calling Wind CLI.
   - Fetch a compact broad-market benchmark and a relevant sector/style benchmark. Market data is context for the specified stocks, not a full-market review.
   - Use K-line data for the correlation pair and calculate return correlation locally.

3. **Previous review**
   - Read `references/history-and-review.md`.
   - Use `scripts/review_journal.py lookup` before writing the report when history and comparison are enabled.
   - For each overlapping stock, evaluate the previous record's confirmation and invalidation conditions from current Wind facts. Mark each condition `met`, `not_met`, or `unknown`; never infer missing facts.
   - Use `scripts/review_journal.py build` to calculate the final review status and atomically save the current JSON record.

4. **Industry news**
   - Use web/current news only as supplemental context when industry news may affect the brief.
   - Cite links for material external news.
   - Read `references/industry-news.md` when using external industry news.

5. **Major events**
   - Check announcements, news, earnings, meeting notes, abnormal moves, and policy/industry shocks.
   - Call event skills only when trigger conditions are met; do not expand routine disclosures.
   - Read `references/event-triggers.md` before invoking event skills.

6. **Correlation**
   - Wind provides K-line series; calculate correlation locally from aligned daily returns.
   - Use `scripts/correlation.py` when K-line data is saved as JSON/CSV.
   - If common return observations are fewer than 30, report sample insufficiency and avoid a directional conclusion.

7. **Next-session watch**
   - For each stock, write observable watch items, confirmation conditions, and invalidation conditions.
   - Do not predict direction or exact prices. Conditions may reference price/volume behavior, relative strength, disclosures, or sector confirmation when supported by available facts.

8. **Optional position review**
   - When triggered, compare the user's original thesis and exit conditions with current facts.
   - State whether an exit condition was triggered and whether the user reports executing it.
   - Do not invent position size, cost, exit conditions, or transactions.

9. **Write and deliver**
   - Use `references/html-email.md` for sections, length, HTML attachment, mobile layout, Gmail summary body, and attachment rules.
   - Use `assets/brief-template.html` for the polished HTML attachment.
   - Use `assets/plain-email-summary-template.md` for Gmail body.

## Verification

Before delivery, check:

- Stock codes, report date, price data, announcement/news dates, and source labeling.
- Wind request tier discipline, especially that Tier 3 was only used when triggered.
- If Tier 3 returned data, it appears in the stock analysis, next-session conditions, or risk caveat.
- Major-event skill use, if any, matches `references/event-triggers.md`.
- Correlation uses returns, not raw prices, and reports sample size.
- Previous-review conditions use current facts and valid IDs from the prior record.
- History JSON contains no absolute paths or directional outlook fields.
- Position review appears only when holdings/trades or an explicit request triggered it.
- HTML opens correctly, is readable on mobile, includes disclaimer, and uses the polished attachment template.
- Gmail draft, if created, has a readable plain summary body and the HTML attachment; do not imply it was sent.
