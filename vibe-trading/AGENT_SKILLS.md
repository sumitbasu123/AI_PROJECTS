# Agent Skills For Vibe Trading

Source catalog: https://github.com/VoltAgent/awesome-agent-skills/tree/main

This project already includes a large finance skill system under
`agent/src/skills` plus an `agent/SKILL.md` entry point. Do not duplicate
trading-theory skills from the external catalog. Add external skills only for
security, testing, code review, UI validation, research discovery, and data
querying.

## Approved Skills

### Security And Static Analysis

- `trailofbits/static-analysis`
- `trailofbits/insecure-defaults`
- `trailofbits/property-based-testing`
- `openai/security-best-practices`
- `openai/security-threat-model`

Use these for FastAPI upload handling, auth, broker connector boundaries,
MCP server configuration, order-guard logic, mandate enforcement, live-runner
safety, SSRF/path traversal checks, and paper-vs-live separation.

### UI And Code Review

- `openai/playwright`
- `browserbase/ui-test`
- `coderabbitai/code-review`

Use UI testing skills for the React/Vite dashboard, portfolio page, agent chat,
live safety status, file upload flow, and API documentation surfaces. Use code
review skills for larger changes touching broker connectors, runtime loops,
auth, or order safety.

### Search And Market Research

- `brave/web-search`
- `brave/news-search`

Use these for research-only market, company, regulatory, and macro context.
Prefer the project's built-in market-data loaders for prices and backtests.

### Data Querying

- `duckdb/query`
- `duckdb/read-file`

Use these for portfolio workbook analysis, backtest result inspection, CSV/
Parquet research artifacts, trade-journal analysis, and local analytics. Avoid
adding a new database service unless there is a clear operational need.

### Crypto / Onchain Research

- `coinbase/query-onchain-data`

Use only for research-only onchain or Base ecosystem analysis.

Do not use `coinbase/trade` unless the project explicitly adds a gated crypto
paper/live connector with the same mandate, order-guard, halt, and audit
controls used elsewhere.

## Project Guardrails

- Avoid duplicating existing finance skills in `agent/src/skills`.
- Keep Indian broker live orders disabled unless the user explicitly changes
  the product direction.
- Treat all execution-related changes as high-risk.
- Preserve paper-trading defaults.
- Never bypass mandate checks, order guards, kill switches, or audit logging.
- Keep broker credentials, OAuth caches, API keys, and portfolio files private.

