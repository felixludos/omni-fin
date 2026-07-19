from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from omnifin.api import invest_parse
from omnifin.api.server import DB_ENV, app
from omnifin.core.db import DatabaseSession
from omnifin.models import Asset, Investment, Transfer, clear_global_identity_map


@pytest.fixture(autouse=True)
def clear_identity_maps():
    clear_global_identity_map()
    yield
    clear_global_identity_map()


@pytest.fixture
def test_db_path(tmp_path):
    return str(tmp_path / "test_invest_parse.db")


@pytest.fixture(autouse=True)
def setup_env(test_db_path, monkeypatch):
    monkeypatch.setenv(DB_ENV, test_db_path)
    from omnifin.api import server
    server._current_db_path = test_db_path
    invest_parse.manager._jobs.clear()
    invest_parse.manager._tasks.clear()


@pytest.fixture
def client(monkeypatch):
    async def fake_parse_row(job, row):
        symbol = row.edited_row.get("symbol", "AAPL") or "AAPL"
        return (
            invest_parse.RowInterpretation(
                summary=f"fake parse row {row.index}",
                confidence=0.8,
                result=invest_parse.InvestmentParseResult(
                    status="known",
                    symbol=symbol,
                    investment=None
                ),
            ),
            None,
        )

    monkeypatch.setattr(invest_parse, "_interpret_row_with_llm", fake_parse_row)
    return TestClient(app)


def _wait_for_done(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/api/invest-parse/jobs/{job_id}").json()
        statuses = [row["status"] for row in payload["rows"]]
        if all(status in {"processed", "error"} for status in statuses):
            return payload
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for invest parse job completion")


def test_invest_parse_job_lifecycle_and_commit(client, test_db_path):
    csv_text = "date,symbol,amount,action\n2026-01-01,AAPL,10,buy\n2026-01-02,VWCE,-5,sell\n"

    create_response = client.post(
        "/api/invest-parse/jobs",
        json={"filename": "investments.csv", "csv_text": csv_text},
    )
    assert create_response.status_code == 200
    job = create_response.json()
    assert job["filename"] == "investments.csv"
    assert len(job["rows"]) == 2

    final_job = _wait_for_done(client, job["id"])
    assert all(row["interpretation"] is not None for row in final_job["rows"])

    pause_response = client.post(f"/api/invest-parse/jobs/{job['id']}/pause")
    assert pause_response.status_code == 200
    assert pause_response.json()["paused"] is True

    resume_response = client.post(f"/api/invest-parse/jobs/{job['id']}/resume")
    assert resume_response.status_code == 200
    assert resume_response.json()["paused"] is False

    first_row = final_job["rows"][0]
    patch_response = client.patch(
        f"/api/invest-parse/jobs/{job['id']}/rows/{first_row['index']}",
        json={"selected": False},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["selected"] is False

    rerun_response = client.post(
        f"/api/invest-parse/jobs/{job['id']}/rerun-rows",
        json={"row_indices": [2]},
    )
    assert rerun_response.status_code == 200
    _wait_for_done(client, job["id"])

    dry_run = client.post(
        f"/api/invest-parse/jobs/{job['id']}/commit",
        json={"dry_run": True},
    )
    assert dry_run.status_code == 200
    dry_payload = dry_run.json()
    assert dry_payload["selected_rows"] == 1
    assert dry_payload["plan_valid"] is True

    commit = client.post(
        f"/api/invest-parse/jobs/{job['id']}/commit",
        json={"dry_run": False, "author": "test"},
    )
    assert commit.status_code == 200
    commit_payload = commit.json()
    assert commit_payload["plan_valid"] is True


def test_invest_parse_surfaces_llm_error_to_row(client, monkeypatch):
    async def llm_failure_with_fallback(job, row):
        return invest_parse._fallback_interpretation(job.filename, row), "RuntimeError: mocked llm failure"

    monkeypatch.setattr(invest_parse, "_interpret_row_with_llm", llm_failure_with_fallback)

    csv_text = "date,symbol,amount\n2026-01-01,AAPL,10\n"
    create_response = client.post(
        "/api/invest-parse/jobs",
        json={"filename": "errors.csv", "csv_text": csv_text},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]

    final_job = _wait_for_done(client, job_id)
    row = final_job["rows"][0]
    assert row["status"] == "processed"
    assert row["llm_error"] == "RuntimeError: mocked llm failure"
    assert row["interpretation"] is not None


def test_list_existing_symbols(client, test_db_path):
    from omnifin.models import Report
    with DatabaseSession(test_db_path) as session:
        report = Report(name="Test Report", _session=session)
        usd = Asset("USD", _session=session)
        eur = Asset("EUR", _session=session)
        aapl = Investment("AAPL", name="Apple Inc.", _session=session)
        report.save(usd, eur, aapl)

    response = client.get("/api/invest-parse/symbols")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert "AAPL" in data
    assert "USD" in data
    assert "EUR" in data


def test_new_investment_parsing(client, test_db_path, monkeypatch):
    async def parse_new_investment(job, row):
        return (
            invest_parse.RowInterpretation(
                summary="New ETF discovered",
                confidence=0.9,
                result=invest_parse.InvestmentParseResult(
                    status="new",
                    symbol=None,
                    investment={
                        "symbol": "EMXC",
                        "name": "iShares Core MSCI Emerging Markets Investments",
                        "category": "etf",
                        "nyse_ticker": None,
                        "ibkr_ticker": "EMXC",
                        "identifier": "IE00B4L5Y983",
                        "identifier_type": "isin",
                        "country": "IE",
                        "fund_type": "etf",
                        "fund_focus": "equity_heavy",
                    }
                ),
            ),
            None,
        )

    monkeypatch.setattr(invest_parse, "_interpret_row_with_llm", parse_new_investment)

    csv_text = "date,description,amount,currency\n2026-01-01,EMXC ETF Purchase,1000,USD\n"

    create_response = client.post(
        "/api/invest-parse/jobs",
        json={"filename": "new_investments.csv", "csv_text": csv_text},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]

    final_job = _wait_for_done(client, job_id)
    row = final_job["rows"][0]
    assert row["interpretation"] is not None
    result = row["interpretation"]["result"]
    assert result["status"] == "new"
    assert result["investment"]["symbol"] == "EMXC"

    commit_response = client.post(
        f"/api/invest-parse/jobs/{job_id}/commit",
        json={"dry_run": False, "author": "test"},
    )
    assert commit_response.status_code == 200
    commit_data = commit_response.json()
    assert "Investment" in commit_data["inserts"]


def test_group_rows_with_column_selection(client, monkeypatch):
    async def fake_group_rows_impl(self, job_id, group_column):
        from omnifin.api.invest_parse import InvestmentGroup, stable_hash_bytes
        
        job = self._require_job_locked(job_id)
        groups = [
            InvestmentGroup(
                group_id=f"group_{stable_hash_bytes(b'[1, 2]').hex()[:8]}",
                row_indices=[1, 2],
                investment=None,
                summary="COST",
                confidence=0.9,
            ),
            InvestmentGroup(
                group_id=f"group_{stable_hash_bytes(b'[3]').hex()[:8]}",
                row_indices=[3],
                investment=None,
                summary="AAPL",
                confidence=0.9,
            ),
        ]
        job.investment_groups = groups
        job.group_column = group_column
        return job

    monkeypatch.setattr(invest_parse.InvestParseJobManager, "group_rows", fake_group_rows_impl)

    csv_text = "Symbol(CUSIP),Security description,Date,Quantity,Price\nCOST(22160K105),COSTCO WHOLESALE CORP,2024-01-01,10,50\nCOST(22160K105),COSTCO WHOLESALE CORP,2024-02-01,5,55\nAAPL,AAPL INC,2024-01-15,100,150\n"

    create_response = client.post(
        "/api/invest-parse/jobs",
        json={"filename": "test.csv", "csv_text": csv_text},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]

    group_response = client.post(
        f"/api/invest-parse/jobs/{job_id}/group-rows",
        json={"group_column": "Symbol(CUSIP)"},
    )
    assert group_response.status_code == 200
    job = group_response.json()
    assert "investment_groups" in job
    assert len(job["investment_groups"]) == 2
    assert job["group_column"] == "Symbol(CUSIP)"