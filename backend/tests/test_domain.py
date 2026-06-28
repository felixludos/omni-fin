from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from omnifin.core.db import DatabaseSession
from omnifin.core.errors import LedgerIntegrityError
from omnifin.models import Account, Asset, Report, Statement, clear_global_identity_map


@pytest.fixture(autouse=True)
def clear_identity_maps():
    clear_global_identity_map()
    yield
    clear_global_identity_map()


def test_identity_map_and_scalar_coercion():
    usd = Asset("USD", category="fiat")
    assert Asset("USD") is usd

    account = Account(name="Fidelity Taxable", type="internal")
    statement = Statement(
        date=datetime(2026, 1, 1, tzinfo=UTC),
        account=account,
        unit="USD",
        balance=100.50,
    )

    assert statement.account is account
    assert statement.unit is usd
    assert statement.unit.symbol == "USD"


def test_plan_and_save_persist_nested_graph_and_staged_relations():
    with DatabaseSession(":memory:") as session:
        report = Report(_session=session, name="unit test import")
        statement = Statement(
            date=datetime(2026, 1, 1, tzinfo=UTC),
            account=Account(name="Fidelity Taxable", type="internal"),
            unit="USD",
            balance=100.50,
        )
        statement.add_tags("taxable_2026")
        statement.comment("Imported from test CSV")

        plan = report.plan(statement)
        assert plan.is_valid
        assert plan.inserts["Report"] == 1
        assert plan.inserts["Asset"] == 1
        assert plan.inserts["Account"] == 1
        assert plan.inserts["Statement"] == 1
        assert plan.inserts["Tag"] == 1
        assert plan.inserts["Comment"] == 1
        assert plan.relation_inserts["statement_tags"] == 1
        assert plan.relation_inserts["statement_comments"] == 1

        report.save(statement)

        assert session.execute("SELECT COUNT(*) AS c FROM assets").fetchone()["c"] == 1
        assert session.execute("SELECT COUNT(*) AS c FROM accounts").fetchone()["c"] == 1
        assert session.execute("SELECT COUNT(*) AS c FROM statements").fetchone()["c"] == 1
        assert session.execute("SELECT COUNT(*) AS c FROM statement_tags").fetchone()["c"] == 1
        assert [tag.name for tag in statement.tags()] == ["taxable_2026"]
        assert session.get(Statement, statement.id) is statement


def test_lazy_hydration_from_database_row():
    statement_id = None
    account_id = None
    with DatabaseSession(":memory:") as session:
        report = Report(_session=session, name="first session")
        account = Account(name="IBKR", type="internal")
        statement = Statement(
            date=datetime(2026, 2, 1, tzinfo=UTC),
            account=account,
            unit=Asset("EUR", category="fiat"),
            balance=42.0,
        )
        report.save(statement)
        statement_id = statement.id
        account_id = account.id

        session.identity_map.clear()
        loaded = session.get(Statement, statement_id)
        assert loaded is not None
        assert loaded.account is not None
        assert loaded.account.id == account_id
        # Account was represented by only its id until this field access hydrated it.
        assert loaded.account.name == "IBKR"
        assert loaded.unit is not None
        assert loaded.unit.symbol == "EUR"


def test_plan_flags_missing_required_references():
    with DatabaseSession(":memory:") as session:
        report = Report(_session=session, name="bad import")
        missing_account = Account(id=uuid4())
        statement = Statement(
            date=datetime(2026, 1, 1, tzinfo=UTC),
            account=missing_account,
            unit="USD",
            balance=1.0,
        )
        plan = report.plan(statement)
        assert not plan.is_valid
        assert any("Account" in error and "missing required fields" in error for error in plan.errors)
        with pytest.raises(LedgerIntegrityError):
            report.save(statement)
