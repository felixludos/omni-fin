from __future__ import annotations

import pytest
from datetime import UTC, datetime
from fastapi.testclient import TestClient

from omnifin.api.server import app, DB_ENV
from omnifin.core.db import DatabaseSession
from omnifin.models import Account, Asset, Report, Statement, Transfer, clear_global_identity_map

@pytest.fixture(autouse=True)
def clear_identity_maps():
    clear_global_identity_map()
    yield
    clear_global_identity_map()


@pytest.fixture
def test_db_path(tmp_path):
    return str(tmp_path / "test_omnifin.db")

@pytest.fixture(autouse=True)
def setup_api_env(test_db_path, monkeypatch):
    monkeypatch.setenv(DB_ENV, test_db_path)

    with DatabaseSession(test_db_path) as session:
        report = Report(name="Test Report", _session=session)
        usd = Asset("USD", category="fiat", _session=session)
        eur = Asset("EUR", category="fiat", _session=session)
        account = Account(name="Test Account", type="internal", _session=session)
        statement = Statement(
            _session=session,
            date=datetime(2026, 1, 1, tzinfo=UTC),
            account=account,
            unit=usd,
            balance=1000.0,
        )
        transfer = Transfer(
            _session=session,
            date=datetime(2026, 1, 1, tzinfo=UTC),
            sender=account,
            receiver=account,
            unit=eur,
            amount=10.0,
        )
        report.save(usd, eur, account, statement, transfer)
    
    yield

@pytest.fixture
def client():
    return TestClient(app)

def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"].endswith("test_omnifin.db")

def test_list_assets(client):
    response = client.get("/api/assets")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert {asset["symbol"] for asset in data} == {"USD", "EUR"}

def test_list_accounts(client):
    response = client.get("/api/accounts")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "Test Account"


def test_list_statements(client):
    response = client.get("/api/statements")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["balance"] == 1000.0


def test_list_transfers(client):
    response = client.get("/api/transfers")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["amount"] == 10.0

def test_list_reports(client):
    response = client.get("/api/reports")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "Test Report"

def test_api_pagination_params(client):
    response = client.get("/api/assets?limit=1&offset=1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["symbol"] in {"USD", "EUR"}

def test_api_invalid_params(client):
    assert client.get("/api/assets?limit=-1").status_code == 422
    assert client.get("/api/assets?offset=-1").status_code == 422
    assert client.get("/api/assets?limit=1001").status_code == 422