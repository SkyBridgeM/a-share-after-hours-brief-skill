# History and Previous-Review Rules

Use `scripts/review_journal.py` for portable JSON history.

## Storage

- Default directory: `<HTML output directory>/history/`.
- Override with `history_dir`.
- JSON is the only history source. Do not generate Markdown logs.
- Records must not contain absolute paths.
- File name: `<report-date>__<sorted-stock-codes>.json`.
- Same date and same stock pool are atomically replaced; other pools are untouched.

## Commands

Look up the latest prior record for each current stock:

```bash
python3 scripts/review_journal.py lookup \
  --history-dir /path/to/report/history \
  --before-date 2026-06-16 \
  --stocks 300750.SZ,600519.SH
```

Build and save a current record:

```bash
python3 scripts/review_journal.py build \
  --input /path/to/current-draft.json \
  --output-html /path/to/report/2026-06-16-review.html
```

Use `--history-dir` to override the default. Use `--history off` to validate and emit the record without saving. Use `--compare-previous false` to skip lookup.

## Condition contract

Each current stock must define next-session conditions with stable IDs:

```json
{
  "next_session_watch": {
    "watch_items": ["成交量能否恢复"],
    "confirmation_conditions": [
      {"id": "volume-recovery", "condition": "成交量较本日明显恢复"}
    ],
    "invalidation_conditions": [
      {"id": "thesis-break", "condition": "公司披露否定核心业务假设"}
    ]
  }
}
```

When a prior record exists, add `condition_results` to the current stock:

```json
[
  {
    "id": "volume-recovery",
    "outcome": "met",
    "evidence": "成交量较上一交易日增加 28%"
  },
  {
    "id": "thesis-break",
    "outcome": "not_met",
    "evidence": "未发现否定核心假设的公告"
  }
]
```

Allowed outcomes: `met`, `not_met`, `unknown`.

## Status mapping

- Any invalidation condition `met` -> `已失效`.
- All confirmation conditions `met`, with no invalidation met -> `已验证`.
- Some confirmation conditions `met` -> `部分验证`.
- All required conditions are known but no confirmation is met -> `未验证`.
- Missing facts, missing condition results, or only unknown outcomes -> `无法判断`.
- No prior record -> `无历史基线`.

The script calculates the status. The agent supplies evidence-backed condition outcomes and a concise adjustment note. Never mark unavailable data as `not_met`; use `unknown`.

## Draft record minimum

```json
{
  "schema_version": 1,
  "report_date": "2026-06-16",
  "generated_at": "2026-06-16T16:30:00+08:00",
  "market_context": {},
  "stocks": [
    {
      "code": "300750.SZ",
      "name": "宁德时代",
      "facts": {},
      "attribution": "mixed",
      "thesis_change": "未改变",
      "condition_results": [],
      "review_adjustment": "继续观察量能与行业相对强弱",
      "next_session_watch": {
        "watch_items": [],
        "confirmation_conditions": [],
        "invalidation_conditions": []
      }
    }
  ],
  "position_review": null
}
```

Allowed attribution values: `market_beta`, `sector`, `stock_specific`, `mixed`, `unknown`.
