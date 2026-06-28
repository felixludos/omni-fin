"""Generic CSV normalization utilities for the first Omnifin milestone."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Literal

from pydantic import BaseModel, Field

from omnifin.core.ids import stable_hash_bytes, utcnow
from omnifin.models import Account, Asset, Event, Report, Transfer

DATE_COLUMNS = ("date", "run date", "trade date", "settle date", "settlement date", "activity date")
SYMBOL_COLUMNS = ("symbol", "ticker", "security", "security id", "asset", "currency")
AMOUNT_COLUMNS = ("amount", "net amount", "net cash", "value", "proceeds", "debit", "credit")
QUANTITY_COLUMNS = ("quantity", "qty", "shares")
TYPE_COLUMNS = ("type", "action", "transaction type", "activity type", "description")


class NormalizedCsvEvent(BaseModel):
    row_number: int
    event_type: str
    date: datetime
    asset_symbol: str
    amount: float
    sender_account: str
    receiver_account: str
    raw_hash_hex: str
    notes: list[str] = Field(default_factory=list)


@dataclass
class NormalizationResult:
    report: Report
    objects: list[Any]
    rows: list[NormalizedCsvEvent]


def normalize_csv_file(
    input_csv: str | Path,
    *,
    source_name: str | None = None,
    account_name: str = "Imported Account",
    account_type: str = "internal",
    include_non_taxable: bool = True,
) -> NormalizationResult:
    """Parse an arbitrary broker-like CSV into Omnifin objects.

    This is deliberately conservative. Broker-specific scripts can layer better
    mappings on top of the same primitives, while this generic path gives you a
    useful first pass for unknown CSV files.
    """

    path = Path(input_csv)
    source_name = source_name or path.name
    report_hash = stable_hash_bytes(path.read_bytes())
    report = Report(date=utcnow(), name=source_name, raw_hash=report_hash)

    internal = Account(name=account_name, type=account_type)
    external = Account(name=f"External counterparty for {source_name}", type="external")

    objects: list[Any] = [internal, external]
    normalized_rows: list[NormalizedCsvEvent] = []

    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for idx, row in enumerate(reader, start=1):
            event_type = infer_event_type(row)
            if not include_non_taxable and event_type in {"metadata", "ignored"}:
                continue
            date = parse_date(find_value(row, DATE_COLUMNS)) or utcnow()
            asset_symbol = infer_asset_symbol(row)
            amount = infer_amount(row)
            if amount == 0:
                amount = infer_quantity(row)
            if amount == 0:
                # Keep a parseable row, but avoid violating transfers.amount > 0.
                amount = 1.0

            asset = Asset(asset_symbol, category=infer_asset_category(asset_symbol))
            raw_json = json.dumps(row, sort_keys=True, ensure_ascii=False)
            raw_hash = stable_hash_bytes(raw_json)

            if amount >= 0:
                sender, receiver = external, internal
            else:
                sender, receiver = internal, external

            transfer = Transfer(
                date=date,
                sender=sender,
                receiver=receiver,
                unit=asset,
                amount=abs(float(amount)),
                raw_hash=raw_hash,
            )
            transfer.add_involved(Event(name=event_type, type=event_type))
            transfer.add_tags(f"source:{source_name}")

            objects.extend([asset, transfer])
            normalized_rows.append(
                NormalizedCsvEvent(
                    row_number=idx,
                    event_type=event_type,
                    date=date,
                    asset_symbol=asset_symbol,
                    amount=abs(float(amount)),
                    sender_account=sender.name or "",
                    receiver_account=receiver.name or "",
                    raw_hash_hex=raw_hash.hex(),
                )
            )
    return NormalizationResult(report=report, objects=objects, rows=normalized_rows)


def write_normalized_csv(rows: Iterable[NormalizedCsvEvent], output_csv: str | Path) -> None:
    rows = list(rows)
    path = Path(output_csv)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(NormalizedCsvEvent.model_fields.keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            data = row.model_dump()
            data["date"] = row.date.isoformat()
            data["notes"] = "; ".join(row.notes)
            writer.writerow(data)


def find_value(row: dict[str, Any], candidates: Iterable[str]) -> str | None:
    lower = {key.strip().lower(): value for key, value in row.items()}
    for candidate in candidates:
        value = lower.get(candidate)
        if value not in (None, ""):
            return str(value).strip()
    return None


def infer_event_type(row: dict[str, Any]) -> str:
    haystack = " ".join(str(v).lower() for v in row.values() if v is not None)
    if "dividend" in haystack:
        return "dividend"
    if "interest" in haystack:
        return "interest"
    if "fee" in haystack or "commission" in haystack:
        return "fee"
    if "buy" in haystack or "bought" in haystack:
        return "trade_buy"
    if "sell" in haystack or "sold" in haystack:
        return "trade_sell"
    if "transfer" in haystack or "wire" in haystack or "deposit" in haystack or "withdrawal" in haystack:
        return "transfer"
    value = find_value(row, TYPE_COLUMNS)
    return value.lower().replace(" ", "_") if value else "unknown"


def infer_asset_symbol(row: dict[str, Any]) -> str:
    symbol = find_value(row, SYMBOL_COLUMNS)
    if symbol:
        symbol = symbol.strip().upper()
        # Fidelity cash-like rows often omit a symbol. Keep obvious fiat tickers.
        if len(symbol) <= 16 and not any(ch.isspace() for ch in symbol):
            return symbol
    haystack = " ".join(str(v).upper() for v in row.values() if v is not None)
    for fiat in ("USD", "EUR", "GBP", "CHF", "JPY"):
        if fiat in haystack:
            return fiat
    return "USD"


def infer_asset_category(symbol: str) -> str | None:
    return "fiat" if symbol in {"USD", "EUR", "GBP", "CHF", "JPY"} else "unknown"


def infer_amount(row: dict[str, Any]) -> float:
    for candidate in AMOUNT_COLUMNS:
        value = find_value(row, (candidate,))
        parsed = parse_number(value)
        if parsed is not None:
            return parsed
    return 0.0


def infer_quantity(row: dict[str, Any]) -> float:
    for candidate in QUANTITY_COLUMNS:
        value = find_value(row, (candidate,))
        parsed = parse_number(value)
        if parsed is not None:
            return parsed
    return 0.0


def parse_number(value: str | None) -> float | None:
    if value is None:
        return None
    cleaned = value.strip().replace(",", "").replace("$", "").replace("€", "")
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=UTC)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None
