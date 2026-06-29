from __future__ import annotations

import pytest
from datetime import UTC, datetime
from pathlib import Path

from omnifin.ingest.normalize import (
    parse_number,
    parse_date,
    find_value,
    infer_event_type,
    infer_asset_symbol,
    normalize_csv_file,
    NormalizationResult,
)

def test_parse_number():
    # Standard floats
    assert parse_number("123.45") == 123.45
    assert parse_number("-123.45") == -123.45
    
    # Thousands separators
    assert parse_number("1,234.56") == 1234.56
    
    # Currency symbols
    assert parse_number("$100.00") == 100.0
    assert parse_number("€50.00") == 50.0
    
    # Accounting format (parentheses)
    assert parse_number("(100.00)") == -100.0
    
    # Edge cases
    assert parse_number(None) is None
    assert parse_number("invalid") is None
    assert parse_number("") is None

def test_parse_date():
    # ISO format
    assert parse_date("2026-01-01") == datetime(2026, 1, 1, tzinfo=UTC)
    
    # US formats
    assert parse_date("01/01/2026") == datetime(2026, 1, 1, tzinfo=UTC)
    assert parse_date("01/01/26") == datetime(2026, 1, 1, tzinfo=UTC)
    
    # European format
    assert parse_date("01.01.2026") == datetime(2026, 1, 1, tzinfo=UTC)
    
    # ISO with time/offset (via fromisoformat)
    assert parse_date("2026-01-01T10:00:00+00:00") == datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
    
    # Edge cases
    assert parse_date(None) is None
    assert parse_date("invalid date") is None

def test_find_value():
    row = {
        " Trade Date ": "2026-01-01",
        "SYMBOL": "AAPL",
        "Amount": "100.00",
        "Empty": ""
    }
    
    # Should find value regardless of case or surrounding whitespace
    assert find_value(row, ("trade date", "date")) == "2026-01-01"
    assert find_value(row, ("symbol", "ticker")) == "AAPL"
    assert find_value(row, ("amount", "value")) == "100.00"
    
    # Should return None for missing or empty
    assert find_value(row, ("nonexistent", "unknown")) is None
    assert find_value(row, ("empty",)) is None

def test_infer_event_type():
    # Keywords in values
    assert infer_event_type({"desc": "Dividend payment"}) == "dividend"
    assert infer_event_type({"desc": "Interest from savings"}) == "interest"
    assert infer_event_type({"desc": "Management fee"}) == "fee"
    assert infer_event_type({"desc": "Bought shares"}) == "trade_buy"
    assert infer_event_type({"desc": "Sold shares"}) == "trade_sell"
    assert infer_event_type({"desc": "Wire transfer"}) == "transfer"
    
    # Explicit type column
    assert infer_event_type({"type": "Purchase"}) == "purchase"
    
    # Unknown
    assert infer_event_type({"something": "random"}) == "unknown"

def test_infer_asset_symbol():
    # Explicit symbol column
    assert infer_asset_symbol({"symbol": "AAPL"}) == "AAPL"
    assert infer_asset_symbol({"ticker": "MSFT"}) == "MSFT"
    
    # Fiat currencies in haystack
    assert infer_asset_symbol({"desc": "Deposit in USD"}) == "USD"
    assert infer_asset_symbol({"desc": "Payment in EUR"}) == "EUR"
    
    # Default
    assert infer_asset_symbol({"desc": "nothing here"}) == "USD"

def test_normalize_csv_file(tmp_path):
    # Create a dummy CSV file
    csv_content = (
        "Trade Date,Symbol,Amount,Description\n"
        "2026-01-01,AAPL,100.00,Bought shares\n"
        "2026-01-02,USD,-50.00,Management fee\n"
        "2026-01-03,MSFT,200.00,Dividend\n"
    )
    p = tmp_path / "test_trades.csv"
    p.write_text(csv_content, encoding="utf-8")
    
    result = normalize_csv_file(p, account_name="Test Account")
    
    assert isinstance(result, NormalizationResult)
    assert result.report.name == "test_trades.csv"
    
    # Check rows
    assert len(result.rows) == 3
    assert result.rows[0].asset_symbol == "AAPL"
    assert result.rows[0].amount == 100.0
    assert result.rows[1].asset_symbol == "USD"
    assert result.rows[1].amount == 50.0  # abs() is used in normalize_csv_file
    
    # Check objects
    # 2 Accounts (Internal + External), 3 Assets (AAPL, USD, MSFT), 3 Transfers
    # Total objects: 2 + 3 + 3 = 8
    assert len(result.objects) == 8