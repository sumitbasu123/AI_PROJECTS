from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

from src.api import portfolio_routes


def _workbook(path: Path) -> None:
    wb = Workbook()
    ws = wb.active
    ws.append(["INSTRUMENT", "NET POS", "AVG COST", "LTP", "CHG %", "TOTAL P&L", "MKT VAL", "INV AMT", "P&L DAY"])
    ws.append(["TEST", 10, 100, 120, 0.01, 200, 1200, 1000, 12])
    wb.save(path)


def test_portfolio_summary_calculates_metrics(tmp_path, monkeypatch):
    source = tmp_path / "holdings.xlsx"
    _workbook(source)
    monkeypatch.setenv("VIBE_TRADING_PORTFOLIO_FILE", str(source))

    summary = portfolio_routes._portfolio_summary()

    assert summary["metrics"]["positions"] == 1
    assert summary["metrics"]["market_value"] == 1200
    assert summary["metrics"]["total_pnl_pct"] == 0.2
    assert summary["holdings"][0]["weight"] == 1.0


def test_local_order_ledger_round_trip(tmp_path, monkeypatch):
    ledger = tmp_path / "orders.json"
    monkeypatch.setattr(portfolio_routes, "ORDER_LEDGER", ledger)

    portfolio_routes._write_orders([{"id": "one"}])

    assert portfolio_routes._read_orders() == [{"id": "one"}]


def test_portfolio_routes_return_summary_and_record_simulation(tmp_path, monkeypatch):
    source = tmp_path / "holdings.xlsx"
    ledger = tmp_path / "orders.json"
    _workbook(source)
    monkeypatch.setenv("VIBE_TRADING_PORTFOLIO_FILE", str(source))
    monkeypatch.setattr(portfolio_routes, "ORDER_LEDGER", ledger)

    async def allow_test_request():
        return None

    app = FastAPI()
    portfolio_routes.register_portfolio_routes(app, allow_test_request)
    client = TestClient(app)

    summary = client.get("/portfolio/summary")
    order = client.post(
        "/portfolio/orders",
        json={
            "symbol": "test",
            "side": "buy",
            "quantity": 2,
            "order_type": "market",
            "product": "delivery",
            "execution_mode": "simulated",
        },
    )

    assert summary.status_code == 200
    assert summary.json()["holdings"][0]["symbol"] == "TEST"
    assert order.status_code == 200
    assert order.json()["result"]["paper_guard"] == "local_ledger"
