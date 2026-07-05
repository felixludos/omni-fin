"""Investment Asset Parser API - CSV upload with AI-assisted investment extraction."""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from omnifin.ai.structured import structured_completion
from omnifin.core.db import DatabaseSession
from omnifin.core.ids import stable_hash_bytes, utcnow
from omnifin.models import Asset, Investment, Report, Tag, Comment

router = APIRouter(prefix="/api/invest-parse", tags=["invest-parse"])

REPO_ROOT = Path(__file__).resolve().parents[3]
PROMPT_TEMPLATE_PATH = REPO_ROOT / "assets" / "invest_parse_prompt.md"
DB_ENV = "OMNIFIN_DB"


def _db_path() -> str:
    from omnifin.api.server import db_path as server_db_path
    return server_db_path()


def _strip_bom(text: str) -> str:
    """Remove BOM (Byte Order Mark) from text if present."""
    if text.startswith('\ufeff'):
        return text[1:]
    return text


def _normalize_headers(headers: list[str]) -> list[str]:
    """Normalize header names by stripping whitespace and BOM."""
    return [h.strip() for h in headers if h] if headers else []


class InvestmentGroup(BaseModel):
    """Group of rows representing the same investment."""
    group_id: str
    row_indices: list[int] = Field(default_factory=list)
    investment: dict[str, Any] | None = None
    summary: str = ""
    confidence: float = 0.0


class RowAttachment(BaseModel):
    """Attachment of a child row to a parent row."""
    child_index: int
    parent_index: int
    attachment_type: str = "wash_sale"
    summary: str = ""


class InvestmentParseResult(BaseModel):
    """Result of parsing a single row - either existing symbol or new investment."""
    status: Literal["known", "new", "no_investment", "attached"]
    symbol: str | None = None
    investment: dict[str, Any] | None = None
    attached_to: int | None = None


class RowInterpretation(BaseModel):
    summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    result: InvestmentParseResult | None = None


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


class InvestParseJob(BaseModel):
    id: str
    filename: str
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    document_hash: str
    headers: list[str]
    paused: bool = False
    status: Literal["running", "paused", "completed", "error"] = "running"
    rows: list[RowState]
    temperature: float = 0.6
    model: str = "gemma4:31b"
    base_url: str = "http://localhost:11434/v1"
    investment_groups: list[InvestmentGroup] = Field(default_factory=list)
    group_column: str | None = None
    row_attachments: list[RowAttachment] = Field(default_factory=list)


class CreateJobRequest(BaseModel):
    filename: str
    csv_text: str
    temperature: float = 0.6
    model: str = "gemma4:31b"
    base_url: str = "http://localhost:11434/v1"


class LoadExampleRequest(BaseModel):
    filename: str


class GroupRowsRequest(BaseModel):
    group_column: str


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
    result: InvestmentParseResult | None = None


class GroupRow(BaseModel):
    row_indices: list[int]
    summary: str = ""
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


def _load_existing_symbols() -> list[str]:
    """Load all existing asset symbols from the database."""
    with DatabaseSession(_db_path()) as session:
        symbols = []
        for asset in session.all(Asset, limit=1000):
            if asset.symbol:
                symbols.append(asset.symbol.upper())
        return sorted(set(symbols))


class InvestParseJobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, InvestParseJob] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def create_job(self, payload: CreateJobRequest) -> InvestParseJob:
        csv_text = _strip_bom(payload.csv_text)
        reader = csv.DictReader(io.StringIO(csv_text))
        if not reader.fieldnames:
            raise HTTPException(status_code=400, detail="CSV has no header row")

        headers = _normalize_headers(list(reader.fieldnames))
        
        rows: list[RowState] = []
        for idx, raw_row in enumerate(reader, start=1):
            source_row = {_normalize_headers([str(k)])[0]: ("" if v is None else str(v)) for k, v in raw_row.items()}
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

        job = InvestParseJob(
            id=uuid4().hex,
            filename=payload.filename,
            document_hash=stable_hash_bytes(csv_text).hex(),
            headers=headers,
            rows=rows,
            temperature=payload.temperature,
            model=payload.model,
            base_url=payload.base_url,
        )

        async with self._lock:
            self._jobs[job.id] = job
            self._ensure_task_locked(job.id)
        return job

    async def load_example(self, payload: LoadExampleRequest) -> InvestParseJob:
        example_dir = REPO_ROOT / "cloud_data" / "examples"
        file_path = example_dir / payload.filename
        if not file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Example file '{payload.filename}' not found in {example_dir}",
            )

        csv_text = _strip_bom(file_path.read_text(encoding="utf-8"))
        create_payload = CreateJobRequest(filename=payload.filename, csv_text=csv_text)
        job = await self.create_job(create_payload)

        async with self._lock:
            job.paused = True
            job.status = "paused"
            job.updated_at = utcnow()

        return job

    async def group_rows(self, job_id: str, group_column: str) -> InvestParseJob:
        async with self._lock:
            job = self._require_job_locked(job_id)
            
            if group_column not in job.headers:
                raise HTTPException(status_code=400, detail=f"Column '{group_column}' not found in CSV headers")
            
            # Group rows by column value
            groups_by_value: dict[str, list[int]] = {}
            for row in job.rows:
                value = row.source_row.get(group_column, "")
                # Extract symbol from Symbol(CUSIP) format if applicable
                if "symbol" in group_column.lower() or "ticker" in group_column.lower():
                    value = _extract_symbol(value)
                
                if value not in groups_by_value:
                    groups_by_value[value] = []
                groups_by_value[value].append(row.index)
            
            # Create InvestmentGroup objects
            groups = []
            for value, row_indices in groups_by_value.items():
                groups.append(InvestmentGroup(
                    group_id=f"group_{stable_hash_bytes(str(row_indices).encode()).hex()[:8]}",
                    row_indices=sorted(row_indices),
                    investment=None,
                    summary=value if value else "Unknown",
                    confidence=0.9,
                ))
            
            job.investment_groups = groups
            job.group_column = group_column
            job.updated_at = utcnow()
            
            return job

    async def get_job(self, job_id: str) -> InvestParseJob:
        async with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise HTTPException(status_code=404, detail="Job not found")
            return job

    async def pause(self, job_id: str) -> InvestParseJob:
        async with self._lock:
            job = self._require_job_locked(job_id)
            job.paused = True
            job.status = "paused"
            job.updated_at = utcnow()
            return job

    async def resume(self, job_id: str) -> InvestParseJob:
        async with self._lock:
            job = self._require_job_locked(job_id)
            job.paused = False
            if job.status != "error":
                job.status = "running"
            job.updated_at = utcnow()
            self._ensure_task_locked(job_id)
            return job

    async def rerun_rows(self, job_id: str, indices: list[int]) -> InvestParseJob:
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

    async def rerun_all(self, job_id: str) -> InvestParseJob:
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
            if row.selected and row.interpretation is not None and row.interpretation.result is not None and (not index_filter or row.index in index_filter)
        ]
        if not selected_rows:
            raise HTTPException(status_code=400, detail="No selected rows with investment parsing results")

        with DatabaseSession(_db_path()) as session:
            report = Report(
                _session=session,
                name=f"Invest Parse {job.filename}",
                author=payload.author,
                raw_hash=bytes.fromhex(job.document_hash),
            )
            
            investments_by_symbol: dict[str, Investment] = {}
            for asset in session.all(Asset, limit=1000):
                if asset.symbol:
                    investments_by_symbol[asset.symbol.upper()] = Investment(_session=session, symbol=asset.symbol.upper())

            objects: list[Any] = []
            for row in selected_rows:
                row_objects = _build_investment_objects_from_result(
                    session=session,
                    row=row,
                    filename=job.filename,
                    document_hash=job.document_hash,
                    investments_by_symbol=investments_by_symbol,
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
                elif job.investment_groups:
                    # Process by groups - find first pending group
                    pending_group = None
                    for group in job.investment_groups:
                        group_rows = [r for r in job.rows if r.index in group.row_indices]
                        if any(r.status == "pending" for r in group_rows):
                            pending_group = group
                            break
                    
                    if pending_group is None:
                        # Check if any rows have errors
                        if any(row.status == "error" for row in job.rows):
                            job.status = "error"
                        else:
                            job.status = "completed"
                        job.updated_at = utcnow()
                        self._tasks.pop(job_id, None)
                        return
                    
                    next_row = next(r for r in job.rows if r.index == pending_group.row_indices[0])
                    next_row.status = "processing"
                    next_row.updated_at = utcnow()
                    job.status = "running"
                    job.updated_at = utcnow()
                else:
                    # Find next pending row (skip attached/no_investment rows)
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
                    
                    # If job has groups, apply interpretation to all rows in the group
                    if current_job.investment_groups:
                        for group in current_job.investment_groups:
                            if next_row.index in group.row_indices:
                                if interpretation.result:
                                    group.investment = interpretation.result.investment
                                else:
                                    group.investment = None
                                group.summary = interpretation.summary
                                group.confidence = interpretation.confidence
                                # Apply to all rows in the group
                                for row in current_job.rows:
                                    if row.index in group.row_indices and row.status != "processed":
                                        row.interpretation = interpretation
                                        row.status = "processed"
                                        row.error = None
                                        row.llm_error = None
                                        row.updated_at = utcnow()
                    
                    current_job.updated_at = utcnow()
            except Exception as exc:
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

    def _require_job_locked(self, job_id: str) -> InvestParseJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job

    @staticmethod
    def _require_row_locked(job: InvestParseJob, row_index: int) -> RowState:
        for row in job.rows:
            if row.index == row_index:
                return row
        raise HTTPException(status_code=404, detail=f"Row {row_index} not found")

    def _ensure_task_locked(self, job_id: str) -> None:
        task = self._tasks.get(job_id)
        if task is not None and not task.done():
            return
        self._tasks[job_id] = asyncio.create_task(self._run_job(job_id))


async def _interpret_row_with_llm(job: InvestParseJob, row: RowState) -> tuple[RowInterpretation, str | None]:
    existing_symbols = _load_existing_symbols()

    prompt = _build_prompt(
        filename=job.filename,
        row_index=row.index,
        headers=job.headers,
        document_hash=job.document_hash,
        row_hash=row.row_hash,
        row=row.edited_row,
        checks=row.checks,
        existing_symbols=existing_symbols,
    )

    try:
        interpreted = await asyncio.to_thread(
            structured_completion,
            prompt,
            LlmRowResponse,
            model=job.model,
            base_url=job.base_url,
            api_key="ollama",
            temperature=job.temperature,
            max_tokens=5000,
            timeout=90.0,
        )
        return (
            RowInterpretation(
                summary=interpreted.summary,
                confidence=interpreted.confidence,
                result=interpreted.result,
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
    existing_symbols: list[str],
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
        "existing_symbols_json": json.dumps(existing_symbols, ensure_ascii=False, indent=2),
    }

    rendered = template
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _extract_symbol(symbol_cusip: str) -> str:
    """Extract ticker symbol from Symbol(CUSIP) format like 'COST(22160K105)'."""
    if not symbol_cusip:
        return ""
    match = re.match(r'^([A-Z]+)', symbol_cusip)
    return match.group(1) if match else symbol_cusip


def _default_prompt_template() -> str:
    pieces = [
        "You are an investment asset parser for Omnifin.",
        "Your task is to determine if the investment involved in a transaction is already known or needs to be added to the database.",
        "",
        "## Input",
        "Row JSON: {{row_json}}",
        "",
        "## Existing Assets (symbols only)",
        "{{existing_symbols_json}}",
        "",
        "## Instructions",
        "1. First, determine if the investment mentioned in the row is already in the database.",
        "2. If KNOWN: Return {\"status\": \"known\", \"symbol\": \"SYMBOL\"} with the existing symbol.",
        "3. If NEW: Return {\"status\": \"new\", \"investment\": {...}} with all required investment fields.",
        "",
        "## Investment Field Definitions",
        "- symbol: Canonical ticker (e.g., AAPL, VWCE, SPY). Required. Uppercase.",
        "- name: Full security name (e.g., 'Apple Inc. Common Stock').",
        "- category: AssetType - 'stock', 'etf', 'mutual_fund', 'bond', 'crypto', 'commodity', 'derivative', 'cash_equivalent', 'fiat', or 'other'.",
        "- nyse_ticker: NYSE ticker if different from symbol (e.g., 'BRK/B' for BRK.B).",
        "- ibkr_ticker: Interactive Brokers ticker identifier.",
        "- identifier: ISIN, CUSIP, WKN, etc. (e.g., 'US0378331005' for AAPL).",
        "- identifier_type: Type of identifier - 'cusip', 'isin', 'wkn', etc.",
        "- country: Domicile country code - 'US', 'IE', 'DE', 'UK', 'NL', etc.",
        "- fund_type: For funds - 'etf', 'mutual_fund', 'index_fund', 'real_estate_fund', 'other_fund', or 'N/A'.",
        "- fund_focus: Equity exposure - 'equity_heavy' (>50% equities), 'mixed' (25-50%), 'other_fund' (<25%), or 'N/A'.",
        "",
        "## Output Requirements",
        "Return only valid JSON matching this schema:",
        "{\"summary\": \"string\", \"confidence\": 0.0-1.0, \"result\": {\"status\": \"known|new\", \"symbol\": \"string|null\", \"investment\": {...}|null}}",
        "Do not include markdown fences or explanatory prose.",
    ]
    return "\n".join(pieces)


def _build_row_checks(row: dict[str, str]) -> list[str]:
    checks: list[str] = []
    lower = {k.strip().lower(): v for k, v in row.items()}

    if not any(value.strip() for value in row.values()):
        checks.append("Row appears empty")

    symbol = next((v for k, v in lower.items() if "symbol" in k or "ticker" in k or "security" in k), None)
    if symbol:
        checks.append(f"Potential symbol/ticker found: {symbol}")

    return checks


def _fallback_interpretation(filename: str, row: RowState) -> RowInterpretation:
    return RowInterpretation(
        summary="Fallback interpretation generated because LLM call failed.",
        confidence=0.3,
        result=InvestmentParseResult(status="new", investment={"symbol": "UNKNOWN"}),
    )


def _build_investment_objects_from_result(
    *,
    session: DatabaseSession,
    row: RowState,
    filename: str,
    document_hash: str,
    investments_by_symbol: dict[str, Investment],
) -> list[Any]:
    out: list[Any] = []
    result = row.interpretation.result if row.interpretation else None
    
    if result is None:
        return out
    
    # Handle no_investment status - skip commit entirely
    if result.status == "no_investment":
        return out
    
    # Handle attached status - will use parent's investment data
    if result.status == "attached":
        return out
    
    if result.investment is None:
        return out
    
    investment_data = result.investment
    symbol = investment_data.get("symbol", "UNKNOWN")
    
    if not symbol:
        return out
    
    clean_symbol = symbol.strip().upper()
    
    existing = investments_by_symbol.get(clean_symbol)
    if existing is not None and result.status == "known":
        return out
    
    created = Investment(_session=session, symbol=clean_symbol)
    investments_by_symbol[clean_symbol] = created
    
    if investment_data.get("name"):
        created.name = str(investment_data["name"])
    if investment_data.get("category"):
        created.category = str(investment_data["category"])
    
    if investment_data.get("nyse_ticker"):
        created.comment(Comment(_session=session, content=str(investment_data["nyse_ticker"]), type="nyse_ticker", created_at=utcnow()))
    if investment_data.get("ibkr_ticker"):
        created.comment(Comment(_session=session, content=str(investment_data["ibkr_ticker"]), type="ibkr_ticker", created_at=utcnow()))
    if investment_data.get("identifier"):
        created.comment(Comment(_session=session, content=str(investment_data["identifier"]), type="asset_identifier", created_at=utcnow()))
    
    if investment_data.get("identifier_type"):
        created.add_tags(Tag(_session=session, name=str(investment_data["identifier_type"]), category="asset_identifier_type"))
    if investment_data.get("country"):
        created.add_tags(Tag(_session=session, name=str(investment_data["country"]), category="country"))
    if investment_data.get("fund_type"):
        created.add_tags(Tag(_session=session, name=str(investment_data["fund_type"]), category="fund_type"))
    if investment_data.get("fund_focus"):
        created.add_tags(Tag(_session=session, name=str(investment_data["fund_focus"]), category="fund_focus"))
    
    out.append(created)
    return out


def _is_wash_sale_row(row: RowState) -> bool:
    """Check if a row represents a wash sale adjustment."""
    source = row.source_row
    security_desc = source.get("Security description", "").lower()
    symbol = source.get("Symbol(CUSIP)", "")
    
    # Check for wash sale indicators
    if "wash sale" in security_desc:
        return True
    
    # Check if it's a row with no symbol but has gain/loss info
    if not symbol or symbol.strip() == "":
        proceeds = source.get("Proceeds", "")
        if proceeds and proceeds != "--" and proceeds != "$0.00":
            return True
    
    return False


def _find_parent_row_index(rows: list[RowState], current_index: int, symbol: str) -> int | None:
    """Find the previous row with the same symbol for attachment."""
    current_row = next((r for r in rows if r.index == current_index), None)
    if not current_row:
        return None
    
    # Look backwards for a row with the same symbol
    for i in range(current_index - 1, 0, -1):
        prev_row = next((r for r in rows if r.index == i), None)
        if prev_row and prev_row.source_row.get("Symbol(CUSIP)", "").startswith(symbol[:4]):
            return prev_row.index
    
    return None


manager = InvestParseJobManager()


@router.get("/symbols", response_model=list[str])
async def list_existing_symbols() -> list[str]:
    """Return all existing asset symbols for context in AI prompts."""
    return _load_existing_symbols()


@router.post("/jobs", response_model=InvestParseJob)
async def create_invest_parse_job(payload: CreateJobRequest) -> InvestParseJob:
    return await manager.create_job(payload)


@router.post("/examples/load", response_model=InvestParseJob)
async def load_example_job(payload: LoadExampleRequest) -> InvestParseJob:
    return await manager.load_example(payload)


@router.get("/jobs/{job_id}", response_model=InvestParseJob)
async def get_invest_parse_job(job_id: str) -> InvestParseJob:
    return await manager.get_job(job_id)


@router.post("/jobs/{job_id}/pause", response_model=InvestParseJob)
async def pause_invest_parse_job(job_id: str) -> InvestParseJob:
    return await manager.pause(job_id)


@router.post("/jobs/{job_id}/resume", response_model=InvestParseJob)
async def resume_invest_parse_job(job_id: str) -> InvestParseJob:
    return await manager.resume(job_id)


@router.post("/jobs/{job_id}/rerun-all", response_model=InvestParseJob)
async def rerun_all_invest_parse_rows(job_id: str) -> InvestParseJob:
    return await manager.rerun_all(job_id)


@router.post("/jobs/{job_id}/rerun-rows", response_model=InvestParseJob)
async def rerun_invest_parse_rows(job_id: str, payload: RerunRowsRequest) -> InvestParseJob:
    return await manager.rerun_rows(job_id, payload.row_indices)


@router.patch("/jobs/{job_id}/rows/{row_index}", response_model=RowState)
async def update_invest_parse_row(job_id: str, row_index: int, payload: UpdateRowRequest) -> RowState:
    return await manager.update_row(job_id, row_index, payload)


@router.post("/jobs/{job_id}/commit", response_model=CommitResponse)
async def commit_invest_parse_job(job_id: str, payload: CommitJobRequest) -> CommitResponse:
    return await manager.commit(job_id, payload)


@router.post("/jobs/{job_id}/group-rows", response_model=InvestParseJob)
async def group_invest_parse_rows(job_id: str, payload: GroupRowsRequest) -> InvestParseJob:
    return await manager.group_rows(job_id, payload.group_column)