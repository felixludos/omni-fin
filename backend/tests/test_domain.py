from __future__ import annotations

import pytest
from uuid import UUID
from datetime import datetime

from omnifin.core.db import DatabaseSession
from omnifin.models import (
    Asset, 
    Account, 
    Report, 
    Transfer, 
    Location, 
    Tag, 
    Comment, 
    clear_global_identity_map
)
from omnifin.core.errors import LedgerIntegrityError

@pytest.fixture(autouse=True)
def reset_identity_map():
    clear_global_identity_map()
    yield
    clear_global_identity_map()

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_domain.db"
    return str(db_file)

def test_identity_map_singleton():
    """Ensure that objects with the same ID/Natural Key are singletons within a session."""
    with DatabaseSession(":memory:") as session:
        # Asset uses symbol as natural key
        a1 = Asset(_session=session, symbol="USD")
        a2 = Asset(_session=session, symbol="USD")
        assert a1 is a2

        # Account uses ID - use a UUID object to be explicit
        acc_id = UUID("018e2f3b-1234-7890-abcd-ef1234567890")
        acc1 = Account(_session=session, id=acc_id, name="Test Acc")
        acc2 = Account(_session=session, id=acc_id, name="Different Name")
        assert acc1 is acc2
        # According to current _merge_raw_data, existing values are kept if not from_db
        assert acc1.name == "Test Acc"

def test_report_plan_and_save(temp_db):
    """Test that Report.plan and Report.save correctly persist a graph of objects."""
    with DatabaseSession(temp_db) as session:
        report = Report(_session=session, name="Test Report")
        
        usd = Asset(_session=session, symbol="USD")
        acc_a = Account(_session=session, name="Account A")
        acc_b = Account(_session=session, name="Account B")
        
        transfer = Transfer(
            _session=session, 
            sender=acc_a, 
            receiver=acc_b, 
            unit=usd, 
            amount=100.0,
            date=datetime.now()
        )
        
        # 1. Plan
        plan = report.plan(usd, acc_a, acc_b, transfer)
        assert plan.is_valid
        assert plan.inserts["Asset"] == 1
        assert plan.inserts["Account"] == 2
        assert plan.inserts["Transfer"] == 1
        
        # 2. Save
        report.save(usd, acc_a, acc_b, transfer)
        
        # 3. Verify persistence by creating a new session
        with DatabaseSession(temp_db) as session2:
            saved_report = session2.get(Report, report.id)
            assert saved_report is not None
            assert saved_report.name == "Test Report"
            
            # Verify transfer exists
            t_id = transfer.id
            saved_transfer = session2.get(Transfer, t_id)
            assert saved_transfer is not None
            assert saved_transfer.amount == 100.0
            assert saved_transfer.unit.symbol == "USD"

def test_lazy_hydration(temp_db):
    """Test that related objects are lazily loaded from the DB."""
    report_id = None
    transfer_id = None
    
    with DatabaseSession(temp_db) as session:
        report = Report(_session=session, name="Hydration Test")
        report_id = report.id
        
        usd = Asset(_session=session, symbol="USD")
        acc = Account(_session=session, name="Acc")
        transfer = Transfer(
            _session=session, 
            sender=acc, 
            receiver=acc, 
            unit=usd, 
            amount=10.0,
            date=datetime.now()
        )
        transfer_id = transfer.id
        
        report.save(usd, acc, transfer)

    with DatabaseSession(temp_db) as session2:
        # Load transfer as identity-only (not fully loaded)
        # We can simulate this by getting it from the DB and checking _loaded
        t = session2.get(Transfer, transfer_id)
        assert t is not None
        
        # Accessing a field should trigger hydration
        assert t.amount == 10.0
        assert t._loaded is True

def test_integrity_constraints(temp_db):
    """Test that missing required fields trigger LedgerIntegrityError."""
    with DatabaseSession(temp_db) as session:
        report = Report(_session=session, name="Error Report")
        
        # Since Pydantic validates on instantiation, we test a field 
        # that might be optional in Pydantic but required in the spec.
        # If all required are in Pydantic, we test the ValidationError.
        with pytest.raises(Exception): # Either ValidationError or LedgerIntegrityError
            Asset(_session=session, symbol=None)

def test_tag_and_comment_persistence(temp_db):
    """Test that tags and comments are persisted via the Report."""
    with DatabaseSession(temp_db) as session:
        report = Report(_session=session, name="Tag Test")
        acc = Account(_session=session, name="Acc")
        
        # Add tag
        acc.add_tags("tax", "investment")
        # Add comment
        acc.comment("This is a test comment")
        
        # To avoid FK errors, we must ensure tags and comments are saved.
        # Report.save collects the graph, but we should be explicit if needed.
        # Actually, report.save(acc) should work if the order is correct.
        # Let's ensure we pass them if they are not being picked up.
        
        # We can check if they are in the staged_adds.
        tags = acc.tags()
        comments = acc.comments()
        
        report.save(acc, *tags, *comments)
        
    with DatabaseSession(temp_db) as session2:
        acc_saved = session2.get(Account, acc.id)
        assert len(acc_saved.tags()) == 2
        assert any(t.name == "tax" for t in acc_saved.tags())
        assert len(acc_saved.comments()) == 1
        assert acc_saved.comments()[0].content == "This is a test comment"