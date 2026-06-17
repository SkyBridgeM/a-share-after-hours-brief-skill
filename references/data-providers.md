# Data Provider Requirements

Financial facts must come from explicit data capabilities, not model memory. Prefer `wind-mcp-skill` for A-share data when available, and use `wind-find-finance-skill` for capability discovery when routing is unclear.

## Required capabilities

For a standard brief, the agent needs these capabilities:

- A-share daily quote and compact price indicators.
- Adjusted daily K-line data.
- Company announcements and exchange disclosures.
- Company financial facts when earnings, valuation, or thesis impact requires them.
- Financial, company, and industry news.
- Broad benchmark and relevant sector/style context.

If a required capability is unavailable, state the limitation and avoid unsupported conclusions. Do not replace missing financial facts with model memory.

## Provider use

- Use one primary financial data provider per factual data group. Do not silently mix providers for the same fact group.
- Label the provider used for material fact groups, such as price/K-line, announcements, financial facts, benchmark context, and news.
- Web/current news and Agent Reach can supplement external industry, supply-chain, association, customer, peer, and policy context. They do not replace exchange disclosures, quotes, K-line data, or financial facts.
- If providers conflict, prioritize official exchange/company disclosures and state the conflict briefly.

## Wind mapping

When using Wind MCP tools, use these mappings where available:

- A-share quote: `stock_data.get_stock_price_indicators`.
- Adjusted daily K-line: `stock_data.get_stock_kline`.
- Company announcements: `financial_docs.get_company_announcements`.
- Financial/company/industry news: `financial_docs.get_financial_news`.
- Benchmark or sector context: `index_data.get_index_price_indicators` or `index_data.get_index_kline`.

Provider-specific field names belong in this reference or `references/wind-data.md`. Do not expose raw provider field names in user-facing HTML or Gmail summaries.
