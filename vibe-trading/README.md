# Vibe Trading Portfolio Dashboard

A paper-trading and portfolio-monitoring extension built on the open-source [HKUDS Vibe-Trading](https://github.com/HKUDS/Vibe-Trading) platform.

## Portfolio extension

This version adds an Indian-equities portfolio workflow with:

- Excel-based holdings import with configurable local file paths.
- Invested value, market value, daily P&L, and total P&L summaries.
- Allocation, concentration, and drawdown indicators.
- A FastAPI portfolio API and React dashboard.
- A local simulated-order ledger.
- Guarded Dhan and Shoonya connector profiles restricted to paper environments.

The extension is implemented primarily in `agent/src/api/portfolio_routes.py`, `frontend/src/pages/Portfolio.tsx`, and `scripts/run-portfolio-local.cmd`.

## Upstream platform

The underlying Vibe-Trading project provides natural-language financial research, backtesting engines, factor libraries, broker connectors, agent workflows, and a React interface. Copyright and authorship remain with HKUDS and the upstream contributors. The original MIT license and `NOTICE` are preserved.

## Run locally

Requires Python 3.11 or newer and Node.js for frontend development.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
```

Create a local `portfolio_holdings.xlsx` workbook with these required headings:

| INSTRUMENT | NET POS | AVG COST | LTP |
|---|---:|---:|---:|
| EXAMPLE | 10 | 100.00 | 105.00 |

Optional columns include `INV AMT`, `MKT VAL`, `TOTAL P&L`, `CHG %`, and `P&L DAY`. The workbook is deliberately excluded from Git.

Start the portfolio app on Windows:

```bat
scripts\run-portfolio-local.cmd
```

Then open <http://127.0.0.1:8000/portfolio>. API documentation is at <http://127.0.0.1:8000/docs>.

## Safety and privacy

- Live broker orders are not enabled by the portfolio dashboard.
- Simulated orders are stored locally and excluded from Git.
- Holdings workbooks, broker credentials, runtime state, and environment files are excluded.
- This software is for research and educational use, not financial advice.

## License and attribution

MIT. See `LICENSE` and `NOTICE`, plus the additional notices within the factor libraries.
