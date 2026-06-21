---
name: external-tooling
description: External non-trading tooling for security review, UI testing, code review, Brave research, DuckDB querying, and research-only onchain analysis. Avoids duplicating bundled finance skills.
category: tool
---

# External Tooling

Use this skill when the task needs non-trading support from the
awesome-agent-skills catalog. Vibe Trading already includes bundled finance
skills, so this skill is intentionally focused on support tooling.

## Approved Skill Families

- Security: `trailofbits/static-analysis`, `trailofbits/insecure-defaults`,
  `trailofbits/property-based-testing`, `openai/security-best-practices`,
  `openai/security-threat-model`
- UI and code review: `openai/playwright`, `browserbase/ui-test`,
  `coderabbitai/code-review`
- Search: `brave/web-search`, `brave/news-search`
- Data querying: `duckdb/query`, `duckdb/read-file`
- Research-only onchain data: `coinbase/query-onchain-data`

## When To Use

- FastAPI auth, uploads, MCP configuration, broker connector boundaries, order
  guards, mandates, halts, and live-runner safety.
- React/Vite dashboard checks, portfolio page checks, agent chat checks, and
  live-safety UI validation.
- Code review of broker, runtime, auth, upload, or execution-adjacent changes.
- Research-only market, regulatory, macro, company, or crypto/onchain context.
- Portfolio workbook, CSV, Parquet, backtest, and trade-journal analysis.

## Do Not Use

- Do not duplicate existing `agent/src/skills` finance methods.
- Do not bypass order guards, mandates, halt flags, or audit logging.
- Do not enable live Indian broker orders unless the product direction changes.
- Do not use `coinbase/trade` unless a gated connector with paper/live controls
  is explicitly added.

