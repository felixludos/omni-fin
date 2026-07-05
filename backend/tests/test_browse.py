"""Tests for the browse API — ensure every model returns JSON-serializable data."""

from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from omnifin.api.browse import (
    MODEL_DEFS,
    _build_high_row,
    _build_low_row,
    _db_path,
)
from omnifin.api.server import app, DB_ENV
from omnifin.core.db import DatabaseSession
from omnifin.models import (
    Account,
    Asset,
    Event,
    Investment,
    InvestmentSale,
    Report,
    Statement,
    Transfer,
    clear_global_identity_map,
)
from datetime import UTC, datetime


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def clear_identity_maps():
    clear_global_identity_map()
    yield
    clear_global_identity_map()


@pytest.fixture
def test_db_path(tmp_path):
    return str(tmp_path / "test_browse.db")


@pytest.fixture(autouse=True)
def setup_browse_env(test_db_path, monkeypatch):
    monkeypatch.setenv(DB_ENV, test_db_path)

    with DatabaseSession(test_db_path) as session:
        report = Report(name="Test Report", _session=session)
        usd = Asset("USD", category="fiat", _session=session)
        eur = Asset("EUR", category="fiat", _session=session)
        equity = Asset("VWCE", category="etf", _session=session)
        investment = Investment(
            _session=session,
            symbol="VWCE",
            name="Vanguard FTSE All-World UCITS ETF",
            identifier="IE00BK5BQT80",
            country="IE",
            fund_type="ETF",
            fund_focus="equity_heavy",
        )
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
        event = Event(_session=session, name="Test sale event", type="trade")
        transfer.add_involved(event)
        sale = InvestmentSale(
            _session=session,
            id=event.id,
            acquisition_date=datetime(2025, 1, 1, tzinfo=UTC),
            cost_basis=8.0,
            term="long",
        )
        report.save(
            usd, eur, equity, investment, account, statement, transfer, event, sale
        )

    yield


@pytest.fixture
def client():
    return TestClient(app)


# ── Helper: check for raw bytes in a dict tree ────────────────────────────────


def _has_raw_bytes(obj) -> bool:
    """Return True if *obj* (or any nested dict/list value) contains a bytes value."""
    if isinstance(obj, bytes):
        return True
    if isinstance(obj, dict):
        return any(_has_raw_bytes(v) for v in obj.values())
    if isinstance(obj, (list, tuple)):
        return any(_has_raw_bytes(v) for v in obj)
    return False


# ── Browse list endpoint tests ────────────────────────────────────────────────


class TestBrowseList:
    """Every ``/api/browse/{model}`` endpoint must return valid JSON."""

    MODELS_TO_TEST = [m for m in MODEL_DEFS]

    @pytest.mark.parametrize("model", MODELS_TO_TEST)
    def test_browse_list_returns_200(self, client, model):
        """The browse list endpoint for every model must return HTTP 200."""
        response = client.get(f"/api/browse/{model}?limit=10&offset=0")
        assert response.status_code == 200, (
            f"{model} returned {response.status_code}: {response.text[:200]}"
        )

    @pytest.mark.parametrize("model", MODELS_TO_TEST)
    def test_browse_list_is_valid_json(self, client, model):
        """The response body must be valid JSON — catching PydanticSerializationError."""
        response = client.get(f"/api/browse/{model}?limit=10&offset=0")
        # json() will raise if the body is not valid JSON
        data = response.json()
        # Verify no raw bytes leaked into the structure
        assert not _has_raw_bytes(data), f"{model} response contains raw bytes"
        # Verify expected top-level keys
        assert "total" in data
        assert "rows" in data
        assert "low_columns" in data
        assert "high_columns" in data
        assert "column_hints" in data

    @pytest.mark.parametrize("model", MODELS_TO_TEST)
    def test_browse_list_rows_have_low_and_high(self, client, model):
        """Every row must have 'id', 'low', and 'high' fields."""
        response = client.get(f"/api/browse/{model}?limit=10&offset=0")
        data = response.json()
        for row in data["rows"]:
            assert "id" in row, f"{model} row missing 'id'"
            assert "low" in row, f"{model} row missing 'low'"
            assert "high" in row, f"{model} row missing 'high'"
            assert not _has_raw_bytes(row["low"]), (
                f"{model} row.low contains raw bytes"
            )
            assert not _has_raw_bytes(row["high"]), (
                f"{model} row.high contains raw bytes"
            )

    @pytest.mark.parametrize("model", MODELS_TO_TEST)
    def test_browse_list_json_roundtrip(self, client, model):
        """The response must survive ``json.dumps`` without error."""
        response = client.get(f"/api/browse/{model}?limit=10&offset=0")
        data = response.json()
        # Force re-serialization — this is what killed us before
        try:
            json.dumps(data)
        except (TypeError, ValueError) as exc:
            pytest.fail(f"{model} response cannot be JSON-serialized: {exc}")

    @pytest.mark.parametrize("model", MODELS_TO_TEST)
    def test_browse_list_both_views(self, client, model):
        """Both high and low views must work and return the expected columns."""
        for view in ("high", "low"):
            response = client.get(
                f"/api/browse/{model}?view={view}&limit=10&offset=0"
            )
            assert response.status_code == 200, (
                f"{model} view={view} returned {response.status_code}"
            )
            data = response.json()
            col_key = f"{view}_columns"
            expected_cols = data.get(col_key, [])
            for row in data["rows"]:
                row_data = row[view]
                # Every column name in the list must be a key in the row data
                for col in expected_cols:
                    assert col in row_data, (
                        f"{model} view={view} row missing column {col!r}"
                    )


# ── Browse detail endpoint tests ──────────────────────────────────────────────


class TestBrowseDetail:
    """The ``/api/browse/{model}/{id}`` endpoint must also return clean JSON."""

    MODELS_TO_TEST = [m for m in MODEL_DEFS if m != "assets"]

    @pytest.mark.parametrize("model", MODELS_TO_TEST)
    def test_browse_detail_first_row(self, client, model):
        """Open the first row from the list in detail view."""
        list_resp = client.get(f"/api/browse/{model}?limit=1&offset=0")
        rows = list_resp.json().get("rows", [])
        if not rows:
            pytest.skip(f"{model} has no rows")
        row_id = rows[0]["id"]
        response = client.get(f"/api/browse/{model}/{row_id}")
        assert response.status_code == 200, (
            f"{model}/{row_id} returned {response.status_code}: {response.text[:200]}"
        )
        detail = response.json()
        assert not _has_raw_bytes(detail), f"{model} detail contains raw bytes"
        for key in ("low", "high", "tags", "comments", "related"):
            assert key in detail, f"{model} detail missing {key!r}"

    def test_browse_detail_asset_by_symbol(self, client):
        """Assets use string PKs (symbol) — verify detail lookup works."""
        response = client.get("/api/browse/assets/USD")
        assert response.status_code == 200, response.text[:200]
        detail = response.json()
        assert not _has_raw_bytes(detail)

    def test_browse_detail_404(self, client):
        """Requesting a non-existent id must return 404."""
        response = client.get("/api/browse/accounts/00000000000000000000000000000000")
        assert response.status_code == 404

    def test_browse_detail_bad_id_format(self, client):
        """An invalid hex id should return 400."""
        response = client.get("/api/browse/accounts/not-a-hex-string")
        assert response.status_code == 400


# ── Helper function unit tests ────────────────────────────────────────────────


class TestBuildLowRow:
    """Direct unit tests for :func:`_build_low_row`."""

    def test_no_raw_bytes_in_output(self, test_db_path):
        """_build_low_row must never return raw bytes, even for UUID PKs."""
        # Open a row from every table that has data
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        for model, spec in MODEL_DEFS.items():
            cols = spec["low_columns"]
            sql = f"SELECT {', '.join(cols)} FROM {spec['table']} LIMIT 1"
            row = conn.execute(sql).fetchone()
            if row is None:
                continue
            low = _build_low_row(spec, row)
            assert isinstance(low, dict), f"{model}: expected dict, got {type(low)}"
            assert not _has_raw_bytes(low), (
                f"{model}: low row contains raw bytes: {low!r}"
            )
            # Every low_column should be a key in the result
            for col in cols:
                assert col in low, f"{model}: low missing key {col!r}"
        conn.close()


class TestBuildHighRow:
    """Direct unit tests for :func:`_build_high_row`."""

    def test_no_raw_bytes_in_output(self, test_db_path):
        """_build_high_row must never return raw bytes."""
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        report_conn = sqlite3.connect(test_db_path)
        report_conn.row_factory = sqlite3.Row
        for model, spec in MODEL_DEFS.items():
            cols = spec["low_columns"]
            sql = f"SELECT {', '.join(cols)} FROM {spec['table']} LIMIT 1"
            row = conn.execute(sql).fetchone()
            if row is None:
                continue
            high = _build_high_row(report_conn, model, spec, row)
            assert isinstance(high, dict), f"{model}: expected dict, got {type(high)}"
            assert not _has_raw_bytes(high), (
                f"{model}: high row contains raw bytes: {high!r}"
            )
        conn.close()
        report_conn.close()
