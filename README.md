# A-share after-hours brief skill

[中文说明](README_zh.md)

This Codex / Agent Skills package reviews one or more A-share stocks after the market closes.

It does not pick stocks, trade, or write a full-market recap. It takes the stock or stock pool named by the user, creates a phone-friendly HTML brief, and saves local JSON history so the next run can check whether the previous observation points held up.

## When to use it

- Review one A-share stock after the close and see whether today's move changed the thesis.
- Review a small stock pool by comparing price action, events, and follow-up conditions.
- Check the last review and mark each observation point as verified, partly verified, not verified, invalidated, or unable to judge.
- Create an HTML brief for archiving, sharing, or email attachment.
- Review position discipline when the user provides holdings or transaction records.

## Core features

- Reviews one stock or a small stock pool.
- Verifies the previous review with `verified / partially_verified / not_verified / invalidated / unable_to_judge`.
- Saves structured history as JSON in a `history/` folder next to the HTML output.
- Uses market, sector, and supply-chain context to separate market, industry, upstream/downstream, and stock-specific factors.
- Handles announcements, earnings, meetings, policy changes, industry news, and upstream/downstream signals.
- Separates assessability from direction. When evidence is sufficient, it assigns `向上 / 维持震荡 / 向下`; when evidence is insufficient, it records that explicitly instead of defaulting to sideways.
- Computes Pearson correlation from two stocks' K-line returns.
- Uses a modern flat HTML template made for phone reading and email attachments. Direction tags follow the A-share color convention: red for up, green for down.
- Can create a short Gmail draft body when the user asks for one. HTML attachment support is checked separately before claiming an attachment was added.
- Checks position discipline only when the user provides holdings, trade records, or asks for it directly.

## Scope limits

- It does not provide default buy or sell recommendations.
- It does not execute trades.
- It does not provide deterministic price forecasts or target prices.
- It does not generate a full market-wide recap by default.
- It does not create weekly reviews or long-term memory by default.

## Installation

### npm / npx

```bash
npx a-share-after-hours-brief-skill install
```

Default install location:

```text
~/.codex/skills/a-share-after-hours-brief/
```

Overwrite an existing installation:

```bash
npx a-share-after-hours-brief-skill install --force
```

`--force` first moves the existing installation to a timestamped backup directory. Use `--force --no-backup` only when you explicitly want to overwrite without a backup.

Install to a custom skills directory:

```bash
npx a-share-after-hours-brief-skill install --target /path/to/skills
```

### GitHub

If npm is not available, install directly from GitHub:

```bash
npx github:SkyBridgeM/a-share-after-hours-brief-skill install
```

### Manual

From the repository root, copy the skill files into the expected skill directory:

```bash
mkdir -p ~/.codex/skills/a-share-after-hours-brief
cp -R SKILL.md agents assets references scripts schemas examples \
  ~/.codex/skills/a-share-after-hours-brief/
```

## Usage examples

```text
Review today's CATL after market close
```

```text
Generate an after-hours HTML brief for these two A-share stocks
```

```text
Verify the previous review and list next-trading-day observation conditions
```

```text
Review this A-share watchlist and create a Gmail draft
```

Chinese prompts work as well:

```text
复盘今天的宁德时代
```

```text
校验上次判断，列出下一交易日验证条件
```

## Output

The generated HTML review usually includes:

1. Today's conclusion
2. Concise market background
3. Previous-review verification
4. Stock-pool overview
5. Individual stock review cards
6. Major events
7. Industry and supply-chain news
8. Correlation analysis
9. Next-session assessment and validation conditions
10. Optional position discipline review

The next-session section first decides whether the available evidence is assessable. If it is, the report chooses one of `向上 / 维持震荡 / 向下` and shows the confidence level. If evidence is insufficient, the report says so and does not force a sideways judgment. It is not a trading instruction and does not include a target price.

## JSON History

By default, history is saved next to the HTML output:

```text
reports/
├── 2026-06-16_A-share-after-hours-brief.html
└── history/
    └── 2026-06-16__300750-SZ_600519-SH.json
```

History rules:

- JSON is the only structured history source.
- The skill does not generate a Markdown history log.
- The JSON record does not store absolute paths.
- `generated_at` uses ISO 8601 with a timezone offset. A-share reports default to Asia/Shanghai.
- The report directory can be moved or backed up as a folder.
- Running the same stock pool again on the same day updates the matching JSON record.
- Malformed history files are skipped with structured warnings instead of being silently ignored.
- The formal schema lives at `schemas/history-v1.schema.json`; a sample record is available at `examples/history-record.example.json`.

## Repository structure

```text
.
├── SKILL.md
├── agents/
│   └── openai.yaml
├── assets/
│   ├── brief-template.html
│   └── plain-email-summary-template.md
├── examples/
│   └── history-record.example.json
├── references/
│   ├── data-providers.md
│   ├── event-triggers.md
│   ├── history-and-review.md
│   ├── html-email.md
│   ├── industry-news.md
│   └── wind-data.md
├── schemas/
│   └── history-v1.schema.json
└── scripts/
    ├── correlation.py
    └── review_journal.py
```

## Scripts

Calculate return correlation for two stocks:

```bash
python3 scripts/correlation.py stock_a.json stock_b.json
```

Look up the previous history record:

```bash
python3 scripts/review_journal.py lookup \
  --history-dir ./reports/history \
  --before-date 2026-06-16 \
  --stocks 300750.SZ,600519.SH
```

Build the current history record and save it:

```bash
python3 scripts/review_journal.py build \
  --input current-draft.json \
  --output-html ./reports/2026-06-16_A-share-after-hours-brief.html
```

## Requirements

- Python 3.10+
- Node.js 18+, only for the npm installer
- A Codex / Agent Skills compatible client
- Financial data capabilities for A-share quotes, adjusted K-lines, announcements, financial facts, benchmark context, and news. Wind MCP is preferred when available.
- [Agent Reach](https://github.com/Panniantong/Agent-Reach) is optional. It can supplement external web, industry association, upstream/downstream, and peer news searches.
- Gmail connector, only when Gmail draft creation is requested

The bundled Python scripts use only the standard library.

## Local Checks

```bash
npm run check
```

You can also check the Python scripts directly:

```bash
PYTHONPYCACHEPREFIX=/tmp/a-share-after-hours-brief-skill-pycache \
python3 -m py_compile scripts/review_journal.py scripts/correlation.py
```

The full check also runs Python unit tests and Node.js installer tests using only standard-library and built-in runtime features.

If you have the Skill Creator validator:

```bash
python3 /path/to/skill-creator/scripts/quick_validate.py ./a-share-after-hours-brief
```

## Data and privacy

Generated HTML reports, `history/*.json`, holding records, and trade records stay in the user's local output folder. The skill does not upload them or store them in a central service.

This repository only includes reusable skill logic, templates, and documentation. It does not include Wind, Gmail, or other API credentials.

## Publishing

Package name:

```text
a-share-after-hours-brief-skill
```

Install command:

```bash
npx a-share-after-hours-brief-skill install
```

GitHub repository:

```text
https://github.com/SkyBridgeM/a-share-after-hours-brief-skill
```

## Disclaimer

This skill is for research notes and workflow automation only. It is not investment advice, a trading instruction, or a promise of returns. Users are responsible for their own investment decisions.

## License

MIT License. See [LICENSE](LICENSE).
