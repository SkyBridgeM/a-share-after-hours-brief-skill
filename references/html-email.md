# HTML and Gmail Delivery

Use concise Chinese. Standard multi-stock reports can be 2-4 HTML pages; use 1-2 pages only when the user asks for a short version.

## Sections

Include these sections in order:

1. Header: title, date, stock list, overall judgment, one-sentence conclusion.
2. Compact market context: broad benchmark, relevant style/sector benchmark, breadth/turnover when available, and attribution use.
3. Previous judgment review: one row/card per overlapping stock; show prior date, prior judgment, status, evidence, and adjustment. Show `无历史基线` for new stocks.
4. Portfolio overview: stock, code, close/change, turnover/turnover rate, key update, thesis impact.
5. Stock cards: today's performance, information update, attribution, thesis impact.
6. Major events: whether triggered, event type, event skill used, thesis impact.
7. Industry and supply-chain news: material upstream, own-segment, downstream, peer/substitute, and policy signals; relevance to each stock; source links.
8. Correlation: pair, window, observation count, Pearson correlation, label, caveat.
9. Next-session assessment: for each stock, show assessment status, confidence, K-line evidence, information/news evidence, confirmation conditions, and invalidation conditions. If assessable, show exactly one visible tag from `向上` / `维持震荡` / `向下`. If evidence is insufficient, show `证据不足` and do not display a directional tag. Do not give exact target prices or present the tendency as certainty.
10. Optional position review: original thesis, exit conditions, trigger status, reported execution, and discipline gap.
11. Source and disclaimer.

## Deliverables

- Polished report: static mobile-friendly `.html` using `assets/brief-template.html`.
- Gmail draft: plain summary using `assets/plain-email-summary-template.md`; attach the polished `.html` only when the Gmail tool confirms local attachment support and upload success.
- Do not send polished HTML as Gmail body through the connector.

## HTML Attachment Rules

- Mobile-first: single-column on phones; avoid wide tables when cards/key-value blocks work better.
- Use embedded CSS, no remote images/fonts, and print-friendly contrast.
- Use a concise modern financial-app style: light gray page background, white surfaces, subtle borders, restrained blue accent, clear judgment tile, and compact signal blocks.
- Avoid heavy gradients, warm-paper palettes, glass effects, thick shadows, decorative backgrounds, and unnecessary nested cards.
- Use visual hierarchy through spacing, borders, type weight, metric cards, status pills, and accent rules.
- Keep all user-facing headings, badges, status labels, and table headers in Chinese. English is acceptable only for stock codes, official company/product names, URLs, or unavoidable source names.
- Use simple Chinese labels such as `盘后判断`, `技术结构`, `相对表现`, `量能质量`, `信息面`, `确认条件`, and `失效条件`. Do not display raw enum names, template variable names, CSS class names, or script field names.
- Follow A-share color convention for directional tags: `向上` / positive signals use red; `向下` / cautious signals use green; `维持震荡` and `证据不足` use neutral gray.
- Let important event and condition-check sections breathe; do not compress away useful judgment.
- Make the next-session assessment impossible to miss: use a clear status pill and a one-sentence explanation before detailed conditions.
- For next-session cards, prefer the template classes `assessment-card`, `assessment-up`, `assessment-sideways`, `assessment-down`, and `assessment-insufficient`. Pair them with `tag-up`, `tag-sideways`, `tag-down`, or `tag-insufficient`.
- For a mobile-first financial-app layout, place the primary judgment in `decision-tile` inside `hero-summary-strong`, then use `assessment-scoreboard` to separate absolute technical structure from relative context.
- Use `structure-panel-primary` for absolute technical structure and `structure-panel-secondary` for relative context. Relative context should read as supporting context, not the main tendency.
- Use `quality-ribbon` when volume data, benchmark data, sector data, or other feature groups are `usable_with_limitations` or `insufficient`.
- Use `app-strip` for compact high-signal facts such as confidence, data quality, technical classification, relative context, and material news stance.
- Use `evidence-grid` for K-line versus information/news evidence. Use `signal-list` for compact K-line, news, upstream/downstream, relative-strength, and risk signals.
- Use `condition-grid` for confirmation and invalidation conditions. Keep each condition in natural language and omit internal condition IDs.
- Hide implementation details from user-facing output: condition IDs, raw JSON keys, Wind raw fields like `_DATE`, template variables, script names, and local absolute paths.
- Translate internal enums before display (`mixed` -> `混合因素`, `stock_specific` -> `个股自身因素`, `sector` -> `行业/板块因素`, `market_beta` -> `市场因素`, `unknown` -> `暂无法归因`); show condition checks as natural-language conditions/evidence only.
- For K-line feature output, show only a concise user-facing subset: absolute technical structure, close zone, volume state or limitation, price-volume interaction, range/breakout state, abnormal-move warning, benchmark/sector relative context, and 2-4 plain-language evidence points. Do not dump every metric or expose raw JSON keys.
- If volume quality is insufficient, show volume as not assessable rather than using volume expansion or contraction as a directional signal.
- Do not show deprecated raw field names such as `percentile_60d` in polished HTML.

## Gmail Summary Rules

- Keep body short: conclusion, stock list, previous-review summary, key changes, next-session assessment, and note to open the attached or local HTML report.
- Do not include CSS, HTML tables, or rich layout in Gmail body.
- Do not include internal IDs, raw field names, script names, or local paths.
- Inspect available Gmail tool capabilities before claiming attachment support.
- Treat plain draft creation and attachment upload as separate actions. Never claim an attachment was added unless the tool result confirms it.
- If attachments are unsupported, create only the plain-text draft when that is consistent with the user's request, then state that the HTML report remains at the local output path.
- Never send an email unless the user explicitly authorizes sending and provides recipients.
