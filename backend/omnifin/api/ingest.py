"""Asynchronous CSV ingestion API with LLM-assisted row interpretation."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import os
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from omnifin.ai.structured import structured_completion
from omnifin.core.db import DatabaseSession
from omnifin.core.ids import stable_hash_bytes, utcnow
from omnifin.ingest.normalize import infer_amount, infer_asset_symbol, infer_event_type, parse_date
from omnifin.models import Account, Asset, Event, InvestmentSale, Report, Statement, Transfer

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_TEMPLATE_PATH = REPO_ROOT / "assets" / "ingest_ai_template.md"
DB_ENV = "OMNIFIN_DB"


def _db_path() -> str:
    configured = os.environ.get(DB_ENV)
    if configured:
        return configured
    return str(REPO_ROOT / "cloud_data" / "omnifin.db")


class ProposedObject(BaseModel):
    object_type: Literal[
        "asset",
        "account",
        "transfer",
        "event",
        "investment_sale",
        "statement",
    ]
    data: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class RowInterpretation(BaseModel):
    summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    objects: list[ProposedObject] = Field(default_factory=list)


class RowState(BaseModel):
    index: int
    source_row: dict[str, str]
    edited_row: dict[str, str]
    row_hash: str
    selected: bool = True
    status: Literal["pending", "processing", "processed", "error"] = "pending"
    checks: list[str] = Field(default_factory=list)
    error: str | None = None
    llm_error: str | None = None
    interpretation: RowInterpretation | None = None
    updated_at: datetime = Field(default_factory=utcnow)


class IngestJob(BaseModel):
    id: str
    filename: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    document_hash: str
    headers: list[str]
    paused: bool = False
    status: Literal["running", "paused", "completed", "error"] = "running"
    rows: list[RowState]
    account_id: Optional[str] = None


class CreateJobRequest(BaseModel):
    filename: str
    csv_text: str
    account_id: Optional[str] = None


class UpdateRowRequest(BaseModel):
    edited_row: dict[str, str] | None = None
    interpretation: RowInterpretation | None = None
    selected: bool | None = None


class RerunRowsRequest(BaseModel):
    row_indices: list[int] = Field(default_factory=list)


class CommitJobRequest(BaseModel):
    row_indices: list[int] | None = None
    dry_run: bool = False
    author: str | None = None


class CommitResponse(BaseModel):
    report_id: str
    selected_rows: int
    plan_valid: bool
    inserts: dict[str, int]
    updates: dict[str, int]
    unchanged: dict[str, int]
    errors: list[str]


class LlmRowResponse(BaseModel):
    summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    objects: list[ProposedObject] = Field(default_factory=list)


class AccountInfo(BaseModel):
    id: str
    name: Optional[str] = None
    type: Optional[str] = None
    institution: Optional[str] = None


def _get_source_account_info(account_id: str) -> dict[str, Any] | None:
    """Load a single account by id to include as source context in AI prompts."""
    with DatabaseSession(_db_path()) as session:
        row = session.execute(
            "SELECT * FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
    if not row:
        return None
    return {
        "id": str(row["id"]) if row["id"] else "",
        "name": row["name"] or "",
        "type": row["type"] or "",
        "institution": row["institution"] or "",
    }


class IngestionJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, IngestJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def list_accounts(self) -> list[AccountInfo]:
        with DatabaseSession(_db_path()) as session:
            accounts: list[dict[str, str]] = []
            for account in session.all(Account, limit=400):
                if account.name:
                    accounts.append(
                        {
                            "id": str(account.id),
                            "name": account.name or "",
                            "type": account.type or "",
                            "institution": account.institution or "",
                        }
                    )

            ordered = sorted(accounts, key=lambda item: (item["name"] or "").lower())
            return [AccountInfo(**acc) for acc in ordered]

    async def create_job(self, payload: CreateJobRequest) -> IngestJob:
        reader = csv.DictReader(io.StringIO(payload.csv_text))
        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV has no header row")

        rows: list[RowState] = []
        for idx, raw_row in enumerate(reader, start=1):
            source_row = {str(k): ("" if v is None else str(v)) for k, v in raw_row.items()}
            row_hash = stable_hash_bytes(
                json.dumps(source_row, sort_keys=True, ensure_ascii=False)
            ).hex()
            rows.append(
                RowState(
                    index=idx,
                    source_row=source_row,
                    edited_row=dict(source_row),
                    row_hash=row_hash,
                    checks=_build_row_checks(source_row),
                )
            )

        job = IngestJob(
            id=uuid4().hex,
            filename=payload.filename,
            document_hash=stable_hash_bytes(payload.csv_text).hex(),
            headers=list(reader.fieldnames),
            rows=rows,
            account_id=payload.account_id or None,
        )

        async with self._lock:
            self._jobs[job.id] = job
            self._ensure_task_locked(job.id)
        return job

    async def get_job(self, job_id: str) -> IngestJob:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Job not found")
            return job

    async def pause(self, job_id: str) -> IngestJob:
        async with self._lock:
            job = self._require_job_locked(job_id)
            job.paused = True
            job.status = "paused"
            job.updated_at = utcnow()
            return job

    async def resume(self, job_id: str) -> IngestJob:
        async with self._lock:
            job = self._require_job_locked(job_id)
            job.paused = False
            if job.status != "error":
                job.status = "running"
            job.updated_at = utcnow()
            self._ensure_task_locked(job_id)
            return job

    async def rerun_rows(self, job_id: str, indices: list[int]) -> IngestJob:
        async with self._lock:
            job = self._require_job_locked(job_id)
            target = set(indices)
            for row in job.rows:
                if row.index in target:
                    row.status = "pending"
                    row.error = None
                    row.llm_error = None
                    row.updated_at = utcnow()
            job.paused = False
            job.status = "running"
            job.updated_at = utcnow()
            self._ensure_task_locked(job_id)
            return job

    async def rerun_all(self, job_id: str) -> IngestJob:
        async with self._lock:
            job = self._require_job_locked(job_id)
            for row in job.rows:
                row.status = "pending"
                row.error = None
                row.llm_error = None
                row.updated_at = utcnow()
            job.paused = False
            job.status = "running"
            job.updated_at = utcnow()
            self._ensure_task_locked(job_id)
            return job

    async def update_row(self, job_id: str, row_index: int, payload: UpdateRowRequest) -> RowState:
        async with self._lock:
            job = self._require_job_locked(job_id)
            row = self._require_row_locked(job, row_index)
            if payload.edited_row is not None:
                row.edited_row = {str(k): ("" if v is None else str(v)) for k, v in payload.edited_row.items()}
                row.row_hash = stable_hash_bytes(
                    json.dumps(row.edited_row, sort_keys=True, ensure_ascii=False)
                ).hex()
                row.checks = _build_row_checks(row.edited_row)
                if row.status == "processed":
                    row.status = "pending"
            if payload.interpretation is not None:
                row.interpretation = payload.interpretation
            if payload.selected is not None:
                row.selected = payload.selected
            row.updated_at = utcnow()
            job.updated_at = utcnow()
            return row

    async def commit(self, job_id: str, payload: CommitJobRequest) -> CommitResponse:
        job = await self.get_job(job_id)
        index_filter = set(payload.row_indices or [])

        selected_rows = [
            row
            for row in job.rows
            if row.selected and row.interpretation is not None and (not index_filter or row.index in index_filter)
        ]
        if not selected_rows:
            raise HTTPException(status_code=400, detail="No selected rows with interpretations")

        with DatabaseSession(_db_path()) as session:
            report = Report(
                _session=session,
                name=f"Ingest {job.filename}",
                author=payload.author,
                raw_hash=bytes.fromhex(job.document_hash),
            )
            assets_by_symbol: dict[str, Asset] = {}
            accounts_by_name: dict[str, Account] = {}
            for asset in session.all(Asset, limit=1000):
                assets_by_symbol[asset.symbol.upper()] = asset
            for account in session.all(Account, limit=1000):
                name = (account.name or "").strip().lower()
                if name:
                    accounts_by_name[name] = account

            objects: list[Any] = []
            for row in selected_rows:
                row_objects = _build_objects_from_interpretation(
                    session=session,
                    row=row,
                    filename=job.filename,
                    document_hash=job.document_hash,
                    assets_by_symbol=assets_by_symbol,
                    accounts_by_name=accounts_by_name,
                )
                objects.extend(row_objects)

            plan = report.plan(*objects)
            if not payload.dry_run and plan.is_valid:
                report.save(*objects)

            return CommitResponse(
                report_id=str(report.id),
                selected_rows=len(selected_rows),
                plan_valid=plan.is_valid,
                inserts=plan.inserts,
                updates=plan.updates,
                unchanged=plan.unchanged,
                errors=plan.errors,
            )

    async def _run_job(self, job_id: str) -> None:
        while True:
            await asyncio.sleep(0)
            async with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    self._tasks.pop(job_id, None)
                    return
                if job.paused:
                    job.status = "paused"
                    next_row = None
                else:
                    pending = [row for row in job.rows if row.status == "pending"]
                    if not pending:
                        if any(row.status == "error" for row in job.rows):
                            job.status = "error"
                        else:
                            job.status = "completed"
                        job.updated_at = utcnow()
                        self._tasks.pop(job_id, None)
                        return
                    next_row = pending[0]
                    next_row.status = "processing"
                    next_row.updated_at = utcnow()
                    job.status = "running"
                    job.updated_at = utcnow()

            if next_row is None:
                await asyncio.sleep(0.2)
                continue

            try:
                interpretation, llm_error = await _interpret_row_with_llm(job, next_row)
                async with self._lock:
                    current_job = self._jobs.get(job_id)
                    if current_job is None:
                        self._tasks.pop(job_id, None)
                        return
                    current_row = self._require_row_locked(current_job, next_row.index)
                    current_row.interpretation = interpretation
                    current_row.status = "processed"
                    current_row.error = None
                    current_row.llm_error = llm_error
                    current_row.updated_at = utcnow()
                    current_job.updated_at = utcnow()
            except Exception as exc:  # pragma: no cover - defensive runtime guard
                async with self._lock:
                    current_job = self._jobs.get(job_id)
                    if current_job is None:
                        self._tasks.pop(job_id, None)
                        return
                    current_row = self._require_row_locked(current_job, next_row.index)
                    current_row.status = "error"
                    current_row.error = str(exc)
                    current_row.llm_error = None
                    current_row.updated_at = utcnow()
                    current_job.updated_at = utcnow()

    def _require_job_locked(self, job_id: str) -> IngestJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @staticmethod
    def _require_row_locked(job: IngestJob, row_index: int) -> RowState:
        for row in job.rows:
            if row.index == row_index:
                return row
        raise HTTPException(status_code=404, detail=f"Row {row_index} not found")

    def _ensure_task_locked(self, job_id: str) -> None:
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            return
        self._tasks[job_id] = asyncio.create_task(self._run_job(job_id))


async def _interpret_row_with_llm(job: IngestJob, row: RowState) -> tuple[RowInterpretation, str | None]:
    accounts, assets = _load_existing_context()

    source_account_info = None
    if job.account_id:
        source_account_info = _get_source_account_info(job.account_id)

    prompt = _build_prompt(
        filename=job.filename,
        row_index=row.index,
        headers=job.headers,
        document_hash=job.document_hash,
        row_hash=row.row_hash,
        row=row.edited_row,
        checks=row.checks,
        existing_accounts=accounts,
        existing_assets=assets,
        source_account=source_account_info,
    )

    model = os.environ.get("OMNIFIN_OLLAMA_MODEL", "gemma4:31b")
    model = os.environ.get("OMNIFIN_OLLAMA_MODEL", "ornith:35b")
    base_url = os.environ.get("OMNIFIN_OLLAMA_BASE_URL", "http://localhost:11434/v1")

    try:
        interpreted = await asyncio.to_thread(
            structured_completion,
            prompt,
            LlmRowResponse,
            model=model,
            base_url=base_url,
            api_key="ollama",
            temperature=0.0,
            max_tokens=5000,
            timeout=90.0,
        )
        return (
            RowInterpretation(
                summary=interpreted.summary,
                confidence=interpreted.confidence,
                objects=interpreted.objects,
            ),
            None,
        )
    except Exception as exc:
        return _fallback_interpretation(job.filename, row), f"{type(exc).__name__}: {exc}"


def _build_prompt(
    *,
    filename: str,
    row_index: int,
    headers: list[str],
    document_hash: str,
    row_hash: str,
    row: dict[str, str],
    checks: list[str],
    existing_accounts: list[dict[str, str]],
    existing_assets: list[dict[str, str]],
    source_account: dict[str, Any] | None = None,
) -> str:
    if PROMPT_TEMPLATE_PATH.exists():
        template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    else:
        template = _default_prompt_template()

    replacements: dict[str, str] = {
        "filename": filename,
        "row_index": str(row_index),
        "headers_json": json.dumps(headers, ensure_ascii=False),
        "document_hash": document_hash,
        "row_hash": row_hash,
        "row_json": json.dumps(row, ensure_ascii=False, indent=2),
        "checks_json": json.dumps(checks, ensure_ascii=False, indent=2),
        "existing_accounts_json": json.dumps(existing_accounts, ensure_ascii=False, indent=2),
        "existing_assets_json": json.dumps(existing_assets, ensure_ascii=False, indent=2),
    }

    if source_account:
        replacements["source_account_json"] = json.dumps(source_account, ensure_ascii=False, indent=2)

    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _default_prompt_template() -> str:
    pieces = [
        "You are an ingestion assistant for Omnifin.",
        "Return a JSON object with keys: summary, confidence, objects.",
        "objects[] item format: {object_type, data, note}.",
        "",
        "Filename: {{filename}}",
        "Row index: {{row_index}}",
        "Document hash: {{document_hash}}",
        "Row hash: {{row_hash}}",
        "Headers: {{headers_json}}",
        "Checks: {{checks_json}}",
    ]

    pieces.extend([
        "",
        "Source account (optional):\n{{source_account_json}}",
        "",
        "Existing accounts:\n{{existing_accounts_json}}",
        "Existing assets:\n{{existing_assets_json}}",
        "",
        "Input row JSON:\n{{row_json}}",
        "",
        "Produce practical objects with complete required fields for transfer/date/unit/sender/receiver/amount.",
    ])
    return "\n".join(pieces)


def _build_row_checks(row: dict[str, str]) -> list[str]:
    checks: list[str] = []
    lower = {k.strip().lower(): v for k, v in row.items()}

    if not any(value.strip() for value in row.values()):
        checks.append("Row appears empty")

    date_value = next((value for key, value in lower.items() if "date" in key and value.strip()), "")
    if date_value and parse_date(date_value) is None:
        checks.append(f"Unparseable date: {date_value}")
    if not date_value:
        checks.append("No date-like field found")

    inferred_amount = infer_amount(row)
    if inferred_amount == 0.0:
        checks.append("No non-zero amount detected")

    symbol = infer_asset_symbol(row)
    if symbol == "USD" and "symbol" not in lower:
        checks.append("No explicit symbol found, defaulted to USD")

    action = infer_event_type(row)
    checks.append(f"Inferred event type: {action}")
    return checks


def _fallback_interpretation(filename: str, row: RowState) -> RowInterpretation:
    inferred_date = _coerce_date(row.edited_row)
    inferred_amount = infer_amount(row.edited_row)
    symbol = infer_asset_symbol(row.edited_row)
    event_type = infer_event_type(row.edited_row)

    transfer_data: dict[str, Any] = {
        "date": inferred_date.isoformat(),
        "amount": abs(inferred_amount if inferred_amount != 0 else 1.0),
        "unit_symbol": symbol,
        "sender_account_name": "Imported External",
        "receiver_account_name": "Imported Internal",
        "event_type": event_type,
        "event_name": f"{event_type} row {row.index}",
        "tags": [f"source:{filename}", f"row:{row.index}"],
    }

    if inferred_amount < 0:
        transfer_data["sender_account_name"] = "Imported Internal"
        transfer_data["receiver_account_name"] = "Imported External"

    return RowInterpretation(
        summary="Fallback interpretation generated because LLM call failed.",
        confidence=0.3,
        objects=[
            ProposedObject(object_type="asset", data={"symbol": symbol}),
            ProposedObject(object_type="transfer", data=transfer_data),
        ],
    )


def _load_existing_context() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    accounts: list[dict[str, str]] = []
    assets: list[dict[str, str]] = []

    with DatabaseSession(_db_path()) as session:
        for account in session.all(Account, limit=200):
            if account.name:
                accounts.append(
                    {
                        "name": account.name,
                        "type": account.type or "",
                        "institution": account.institution or "",
                    }
                )
        for asset in session.all(Asset, limit=400):
            if asset.symbol:
                assets.append(
                    {
                        "symbol": asset.symbol,
                        "name": asset.name or "",
                        "category": str(asset.category or ""),
                    }
                )

    account_counts = Counter(item["name"] for item in accounts)
    ordered_accounts = sorted(
        accounts,
        key=lambda item: (
            -account_counts[item["name"]],
            item["name"].lower(),
        ),
    )
    ordered_assets = sorted(assets, key=lambda item: item["symbol"].lower())
    return ordered_accounts[:80], ordered_assets[:160]


def _build_objects_from_interpretation(
    *,
    session: DatabaseSession,
    row: RowState,
    filename: str,
    document_hash: str,
    assets_by_symbol: dict[str, Asset],
    accounts_by_name: dict[str, Account],
) -> list[Any]:
    out: list[Any] = []

    def get_asset(symbol: str) -> Asset:
        clean_symbol = symbol.strip().upper() or "USD"
        existing = assets_by_symbol.get(clean_symbol)
        if existing is not None:
            return existing
        created = Asset(_session=session, symbol=clean_symbol)
        assets_by_symbol[clean_symbol] = created
        return created

    def get_account(name: str, default_type: str = "internal") -> Account:
        clean = name.strip() or "Imported Account"
        key = clean.lower()
        existing = accounts_by_name.get(key)
        if existing is not None:
            return existing
        created = Account(_session=session, name=clean, type=default_type)
        accounts_by_name[key] = created
        return created

    for proposal in row.interpretation.objects if row.interpretation else []:
        data = dict(proposal.data)
        if proposal.object_type == "asset":
            symbol = str(data.get("symbol") or infer_asset_symbol(row.edited_row)).strip().upper()
            asset = get_asset(symbol)
            if data.get("name"):
                asset.name = str(data["name"])
            if data.get("category"):
                asset.category = str(data["category"])
            out.append(asset)
            continue

        if proposal.object_type == "account":
            account = get_account(str(data.get("name") or "Imported Account"), str(data.get("type") or "internal"))
            if data.get("institution"):
                account.institution = str(data["institution"])
            out.append(account)
            continue

        if proposal.object_type == "statement":
            unit_symbol = str(data.get("unit_symbol") or infer_asset_symbol(row.edited_row))
            statement = Statement(
                _session=session,
                date=_coerce_date_with_fallback(data.get("date"), row.edited_row),
                account=get_account(str(data.get("account_name") or "Imported Account")),
                unit=get_asset(unit_symbol),
                balance=_coerce_float(data.get("balance"), default=0.0),
            )
            statement.add_tags(f"source:{filename}", f"row:{row.index}")
            statement.comment(
                json.dumps(
                    {
                        "document_hash": document_hash,
                        "row_hash": row.row_hash,
                        "row_index": row.index,
                        "checks": row.checks,
                    },
                    ensure_ascii=False,
                )
            )
            out.append(statement)
            continue

        if proposal.object_type == "event":
            event = Event(
                _session=session,
                name=str(data.get("name") or f"row-{row.index}-event"),
                type=str(data.get("type") or infer_event_type(row.edited_row)),
            )
            out.append(event)
            continue

        if proposal.object_type == "investment_sale":
            sale = InvestmentSale(
                _session=session,
                acquisition_date=_coerce_date_with_fallback(data.get("acquisition_date"), row.edited_row),
                cost_basis=_coerce_float(data.get("cost_basis"), default=0.0),
                term=str(data.get("term") or "unknown"),
            )
            out.append(sale)
            continue

        if proposal.object_type == "transfer":
            amount = _coerce_float(data.get("amount"), default=0.0)
            if amount == 0.0:
                amount = infer_amount(row.edited_row)
            if amount == 0.0:
                amount = 1.0

            sender_name = str(data.get("sender_account_name") or "Imported External")
            receiver_name = str(data.get("receiver_account_name") or "Imported Internal")
            if amount < 0:
                sender_name, receiver_name = receiver_name, sender_name

            transfer = Transfer(
                _session=session,
                date=_coerce_date_with_fallback(data.get("date"), row.edited_row),
                sender=get_account(sender_name, "external"),
                receiver=get_account(receiver_name, "internal"),
                unit=get_asset(str(data.get("unit_symbol") or infer_asset_symbol(row.edited_row))),
                amount=abs(amount),
                raw_hash=bytes.fromhex(row.row_hash),
            )

            event_name = str(data.get("event_name") or f"{infer_event_type(row.edited_row)} row {row.index}")
            event_type = str(data.get("event_type") or infer_event_type(row.edited_row))
            transfer.add_involved(Event(_session=session, name=event_name, type=event_type))

            tags = data.get("tags")
            if isinstance(tags, list) and tags:
                transfer.add_tags(*[str(tag) for tag in tags])
            transfer.add_tags(f"source:{filename}", f"row:{row.index}")
            transfer.comment(
                json.dumps(
                    {
                        "document_hash": document_hash,
                        "row_hash": row.row_hash,
                        "row_index": row.index,
                        "checks": row.checks,
                    },
                    ensure_ascii=False,
                )
            )
            out.append(transfer)
            continue

    if not out:
        fallback = _fallback_interpretation(filename, row)
        row.interpretation = fallback
        return _build_objects_from_interpretation(
            session=session,
            row=row,
            filename=filename,
            document_hash=document_hash,
            assets_by_symbol=assets_by_symbol,
            accounts_by_name=accounts_by_name,
        )

    return out


def _coerce_float(value: Any, *, default: float) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("$", "")
    if not text:
        return default
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    try:
        return float(text)
    except ValueError:
        return default


def _coerce_date_with_fallback(value: Any, row: dict[str, str]) -> datetime:
    if isinstance(value, str):
        parsed = parse_date(value)
        if parsed is not None:
            return parsed
    return _coerce_date(row)


def _coerce_date(row: dict[str, str]) -> datetime:
    for key, value in row.items():
        if "date" in key.strip().lower() and value.strip():
            parsed = parse_date(value)
            if parsed is not None:
                return parsed
    return datetime.now(UTC)


manager = IngestionJobManager()


@router.get("/accounts", response_model=list[AccountInfo])
async def list_accounts() -> list[AccountInfo]:
    return await manager.list_accounts()


@router.post("/jobs", response_model=IngestJob)
async def create_ingest_job(payload: CreateJobRequest) -> IngestJob:
    return await manager.create_job(payload)


@router.get("/jobs/{job_id}", response_model=IngestJob)
async def get_ingest_job(job_id: str) -> IngestJob:
    return await manager.get_job(job_id)


@router.post("/jobs/{job_id}/pause", response_model=IngestJob)
async def pause_ingest_job(job_id: str) -> IngestJob:
    return await manager.pause(job_id)


@router.post("/jobs/{job_id}/resume", response_model=IngestJob)
async def resume_ingest_job(job_id: str) -> IngestJob:
    return await manager.resume(job_id)


@router.post("/jobs/{job_id}/rerun-all", response_model=IngestJob)
async def rerun_all_ingest_rows(job_id: str) -> IngestJob:
    return await manager.rerun_all(job_id)


@router.post("/jobs/{job_id}/rerun-rows", response_model=IngestJob)
async def rerun_ingest_rows(job_id: str, payload: RerunRowsRequest) -> IngestJob:
    return await manager.rerun_rows(job_id, payload.row_indices)


@router.patch("/jobs/{job_id}/rows/{row_index}", response_model=RowState)
async def update_ingest_row(job_id: str, row_index: int, payload: UpdateRowRequest) -> RowState:
    return await manager.update_row(job_id, row_index, payload)


@router.post("/jobs/{job_id}/commit", response_model=CommitResponse)
async def commit_ingest_job(job_id: str, payload: CommitJobRequest) -> CommitResponse:
    return await manager.commit(job_id, payload)