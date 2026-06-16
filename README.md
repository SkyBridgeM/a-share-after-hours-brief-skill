# A Share After-Hours Brief Skill

[中文说明](README_zh.md)

A Codex / Agent Skills package for **after-hours A-share stock review**.

This is not a stock-picking tool, a trading bot, or a full-market recap generator. It focuses on one or more user-specified A-share stocks, produces a mobile-friendly HTML review, and keeps portable local JSON history so the next run can verify the previous review.

## When To Use It

- Review one A-share stock after market close: what happened today and whether the logic changed.
- Review a small stock pool: compare daily performance, events, and follow-up observation conditions.
- Check the previous review: verify whether the last observation points were confirmed.
- Generate an HTML brief that can be archived, shared, or attached to email.
- Review position discipline when the user provides holdings or transaction records.

## Core Features

- **Single-stock or stock-pool review**: supports one or multiple A-share stocks.
- **Previous-review verification**: uses `verified / partially_verified / not_verified / invalidated / unable_to_judge`.
- **Portable JSON history**: defaults to a `history/` folder next to the HTML output.
- **Market and industry baselines**: used only as context to separate market, sector, and stock-specific factors.
- **Major events and industry news**: handles announcements, earnings, meetings, policy changes, and industry updates.
- **Correlation calculation**: computes Pearson correlation from two stocks' K-line returns.
- **Mobile-friendly HTML template**: designed for phone reading and email attachments.
- **Gmail draft template**: can create a concise email body with the HTML report attached.
- **Position discipline review**: enabled only when the user provides holdings, trade records, or explicitly asks for it.

## What It Does Not Do

- Does not provide default buy or sell recommendations.
- Does not execute trades.
- Does not predict 1-3 day price movements.
- Does not generate a complete market-wide recap by default.
- Does not create weekly reviews or long-term memory by default.
- Does not upload or centrally store user history.
- Does not include Wind, Gmail, or other API credentials.

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

Copy the folder into your Codex skills directory:

```bash
cp -R a-share-after-hours-brief ~/.codex/skills/
```

## Usage Examples

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

Chinese prompts are fully supported, for example:

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
7. Industry news
8. Correlation analysis
9. Next-trading-day observation points
10. Optional position discipline review

The "next-trading-day observation" section only lists verifiable variables and conditions. It does not provide a directional price forecast.

## JSON History

History defaults to a folder next to the HTML output:

```text
reports/
├── 2026-06-16_A-share-after-hours-brief.html
└── history/
    └── 2026-06-16__300750-SZ_600519-SH.json
```

Design principles:

- JSON is the only structured history source.
- No Markdown history log is generated.
- No absolute paths are stored.
- The whole report directory can be moved or backed up.
- Re-running the same stock pool on the same day updates the matching JSON record.

## Project Structure

```text
a-share-after-hours-brief/
├── SKILL.md
├── agents/
│   └── openai.yaml
├── assets/
│   ├── brief-template.html
│   └── plain-email-summary-template.md
├── references/
│   ├── event-triggers.md
│   ├── history-and-review.md
│   ├── html-email.md
│   ├── industry-news.md
│   └── wind-data.md
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

Build and save the current history record:

```bash
python3 scripts/review_journal.py build \
  --input current-draft.json \
  --output-html ./reports/2026-06-16_A-share-after-hours-brief.html
```

## Requirements

- Python 3.10+
- Node.js 18+, only for the npm installer
- A Codex / Agent Skills compatible client
- Wind data capability for A-share quotes, K-lines, announcements, and news
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

If you have the Skill Creator validator:

```bash
python3 /path/to/skill-creator/scripts/quick_validate.py ./a-share-after-hours-brief
```

## Data And Privacy

Do not commit generated HTML reports, `history/*.json`, holding records, or trade records. This repository only publishes reusable skill logic, templates, and documentation.

`.gitignore` excludes common output folders and history data by default.

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

This Skill is for research notes and workflow automation only. It is not investment advice, a trading instruction, or a promise of returns. Users are responsible for their own investment decisions.

## License

MIT License. See [LICENSE](LICENSE).
