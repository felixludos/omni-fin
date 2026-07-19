from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from omnifin.api import ingest
from omnifin.api.server import DB_ENV, app
from omnifin.core.db import DatabaseSession
from omnifin.models import Transfer, clear_global_identity_map


@pytest.fixture(autouse=True)
def clear_identity_maps():
    clear_global_identity_map()
    yield
    clear_global_identity_map()


@pytest.fixture
def test_db_path(tmp_path):
    return str(tmp_path / "test_ingest_api.db")


@pytest.fixture(autouse=True)
def setup_env(test_db_path, monkeypatch):
    monkeypatch.setenv(DB_ENV, test_db_path)
    ingest.manager._jobs.clear()
    ingest.manager._tasks.clear()


@pytest.fixture
def client(monkeypatch):
    async def fake_interpretation(job, row):
        symbol = row.edited_row.get("symbol", "USD") or "USD"
        amount_text = row.edited_row.get("amount", "1")
        try:
            amount = float(amount_text)
        except ValueError:
            amount = 1.0

        return (
            ingest.RowInterpretation(
                summary=f"fake row {row.index}",
                confidence=0.8,
                objects=[
                    ingest.ProposedObject(object_type="asset", data={"symbol": symbol}),
                    ingest.ProposedObject(
                        object_type="transfer",
                        data={
                            "date": row.edited_row.get("date", "2026-01-01"),
                            "amount": abs(amount) if amount != 0 else 1.0,
                            "unit_symbol": symbol,
                            "sender_account_name": "External",
                            "receiver_account_name": "Internal",
                            "event_type": "transfer",
                            "event_name": f"row-{row.index}",
                        },
                    ),
                ],
            ),
            None,
        )

    monkeypatch.setattr(ingest, "_interpret_row_with_llm", fake_interpretation)
    return TestClient(app)


def _wait_for_done(client: TestClient, job_id: str) -> dict:
    for _ in range(80):
        payload = client.get(f"/api/ingest/jobs/{job_id}").json()
        statuses = [row["status"] for row in payload["rows"]]
        if all(status in {"processed", "error"} for status in statuses):
            return payload
        time.sleep(0.05)
    raise AssertionError("Timed out waiting for ingest job completion")


def test_ingest_job_lifecycle_and_commit(client, test_db_path):
    csv_text = "date,symbol,amount,action\n2026-01-01,USD,10,deposit\n2026-01-02,EUR,-5,withdraw\n"

    create_response = client.post(
        "/api/ingest/jobs",
        json={"filename": "sample.csv", "csv_text": csv_text},
    )
    assert create_response.status_code == 200
    job = create_response.json()
    assert job["filename"] == "sample.csv"
    assert len(job["rows"]) == 2

    final_job = _wait_for_done(client, job["id"])
    assert all(row["interpretation"] is not None for row in final_job["rows"])

    pause_response = client.post(f"/api/ingest/jobs/{job['id']}/pause")
    assert pause_response.status_code == 200
    assert pause_response.json()["paused"] is True

    resume_response = client.post(f"/api/ingest/jobs/{job['id']}/resume")
    assert resume_response.status_code == 200
    assert resume_response.json()["paused"] is False

    first_row = final_job["rows"][0]
    patch_response = client.patch(
        f"/api/ingest/jobs/{job['id']}/rows/{first_row['index']}",
        json={"selected": False},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["selected"] is False

    rerun_response = client.post(
        f"/api/ingest/jobs/{job['id']}/rerun-rows",
        json={"row_indices": [2]},
    )
    assert rerun_response.status_code == 200
    _wait_for_done(client, job["id"])

    dry_run = client.post(
        f"/api/ingest/jobs/{job['id']}/commit",
        json={"dry_run": True},
    )
    assert dry_run.status_code == 200
    dry_payload = dry_run.json()
    assert dry_payload["selected_rows"] == 1
    assert dry_payload["plan_valid"] is True

    commit = client.post(
        f"/api/ingest/jobs/{job['id']}/commit",
        json={"dry_run": False},
    )
    assert commit.status_code == 200
    commit_payload = commit.json()
    assert commit_payload["plan_valid"] is True

    with DatabaseSession(test_db_path) as session:
        transfers = session.all(Transfer, limit=20)
        assert len(transfers) == 1


def test_ingest_surfaces_llm_error_to_row(client, monkeypatch):
    async def llm_failure_with_fallback(job, row):
        return ingest._fallback_interpretation(job.filename, row), "RuntimeError: mocked llm failure"

    monkeypatch.setattr(ingest, "_interpret_row_with_llm", llm_failure_with_fallback)

    csv_text = "date,symbol,amount\n2026-01-01,USD,10\n"
    create_response = client.post(
        "/api/ingest/jobs",
        json={"filename": "errors.csv", "csv_text": csv_text},
    )
    assert create_response.status_code == 200
    job_id = create_response.json()["id"]

    final_job = _wait_for_done(client, job_id)
    row = final_job["rows"][0]
    assert row["status"] == "processed"
    assert row["llm_error"] == "RuntimeError: mocked llm failure"
    assert row["interpretation"] is not None
