from __future__ import annotations

import os
import pytest
from fastapi.testclient import TestClient

from omnifin.api.server import app, DB_ENV
from omnifin.core.db import DatabaseSession
from omnifin.models import Account, Asset, Report

@pytest.fixture(scope="session")
def test_db_path(tmp_path_factory):
    # Create a temporary database file for the entire test session
    tmp_dir = tmp_path_factory.mktemp("data")
    db_file = tmp_dir / "test_omnifin.db"
    return str(db_file)

@pytest.fixture(autouse=True)
def setup_api_env(test_db_path, monkeypatch):
    # Force the API to use the test database
    monkeypatch.setenv(DB_ENV, test_db_path)
    
    # Initialize the database with some seed data for each test
    with DatabaseSession(test_db_path) as session:
        # Attach the session to all models that need it for .save() or internal lookups
        report = Report(name="Test Report", _session=session)
        asset = Asset("USD", category="fiat", _session=session)
        account = Account(name="Test Account", type="internal", _session=session)
        
        report.save(account)
        report.save(asset)
    
    yield

@pytest.fixture
def client():
    return TestClient(app)

def test_health_endpoint(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "database" in data

def test_list_assets(client):
    response = client.get("/api/assets")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    # Verify the seeded asset is there
    assert any(asset["symbol"] == "USD" for asset in data)

def test_list_accounts(client):
    response = client.get("/api/accounts")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(acc["name"] == "Test Account" for acc in data)

def test_list_reports(client):
    response = client.get("/api/reports")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert any(rep["name"] == "Test Report" for rep in data)

def test_api_pagination_params(client):
    # Test that query parameters are accepted without crashing
    response = client.get("/api/assets?limit=10&offset=0")
    assert response.status_code == 200

def test_api_invalid_params(client):
    # Test that invalid query parameters (e.g., negative limit) return 422
    response = client.get("/api/assets?limit=-1")
    assert response.status_code == 422