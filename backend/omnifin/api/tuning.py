"""AI tuning endpoints for prompt experimentation and schema validation."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from omnifin.ai.structured import raw_completion, structured_completion
from omnifin.core.db import DatabaseSession
from omnifin.models import Account, Asset
from omnifin.models.composites import ParsingRowResult, Portfolio, Sale, Trade
from omnifin.models.domain import (
    Comment,
    Event,
    Investment,
    InvestmentSale,
    Location,
    Report,
    Statement,
    Tag,
    Transfer,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_ENV = "OMNIFIN_DB"

router = APIRouter(prefix="/api/ingest/tuning", tags=["tuning"])

SCHEMA_MODELS: dict[str, type[BaseModel]] = {
    "Report": Report,
    "Asset": Asset,
    "Investment": Investment,
    "Account": Account,
    "Statement": Statement,
    "Transfer": Transfer,
    "Location": Location,
    "Event": Event,
    "InvestmentSale": InvestmentSale,
    "Tag": Tag,
    "Comment": Comment,
    "Portfolio": Portfolio,
    "Trade": Trade,
    "Sale": Sale,
    "ParsingRowResult": ParsingRowResult,
}


def _db_path() -> str:
    configured = os.environ.get(DB_ENV)
    if configured:
        return configured
    return str(REPO_ROOT / "cloud_data" / "omnifin.db")


class RunTuningRequest(BaseModel):
    prompt: str
    model: str = "gemma4:31b"
    base_url: str = "http://localhost:11434/v1"
    temperature: float = 0.0
    max_tokens: int = 8000
    response_schema: Optional[str] = None


class RunTuningResponse(BaseModel):
    content: str
    reasoning: Optional[str] = None
    parsed: Optional[dict[str, Any]] = None
    validation_notes: list[str] = Field(default_factory=list)


@router.get("/schemas")
async def get_schemas() -> dict[str, dict[str, Any]]:
    """Return JSON schemas for all high-level Pydantic models."""
    result: dict[str, dict[str, Any]] = {}
    for name, model_cls in SCHEMA_MODELS.items():
        schema = model_cls.model_json_schema()
        # Remove $defs to keep the output readable; each schema is self-contained.
        schema.pop("$defs", None)
        result[name] = schema
    return result


@router.get("/context")
async def get_context() -> dict[str, list[dict[str, str]]]:
    """Return accounts and assets from the current database for context selection."""
    accounts: list[dict[str, str]] = []
    assets: list[dict[str, str]] = []

    with DatabaseSession(_db_path()) as session:
        for account in session.all(Account, limit=200):
            if account.name:
                accounts.append({
                    "name": account.name,
                    "type": account.type or "",
                    "institution": account.institution or "",
                })
        for asset in session.all(Asset, limit=400):
            if asset.symbol:
                assets.append({
                    "symbol": asset.symbol,
                    "name": asset.name or "",
                    "category": str(asset.category or ""),
                })

    accounts.sort(key=lambda a: a["name"].lower())
    assets.sort(key=lambda a: a["symbol"].lower())

    return {"accounts": accounts[:80], "assets": assets[:160]}


@router.post("/run", response_model=RunTuningResponse)
async def run_tuning(payload: RunTuningRequest) -> RunTuningResponse:
    """Run an LLM call with the given prompt and hyperparameters.

    If ``response_schema`` is provided, structured output mode is used with
    that schema; otherwise a raw completion is performed.
    """

    if payload.response_schema:
        model_cls = SCHEMA_MODELS.get(payload.response_schema)
        if model_cls is None:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown response schema '{payload.response_schema}'. "
                f"Available: {', '.join(sorted(SCHEMA_MODELS))}",
            )

        try:
            parsed = await _run_structured(
                prompt=payload.prompt,
                model_cls=model_cls,
                model=payload.model,
                base_url=payload.base_url,
                temperature=payload.temperature,
                max_tokens=payload.max_tokens,
            )
            return RunTuningResponse(
                content=_model_to_dict(parsed),
                parsed=_model_to_dict(parsed),
                validation_notes=["Structured output validated successfully against schema."],
            )
        except Exception as exc:
            return RunTuningResponse(
                content="",
                validation_notes=[f"Structured output failed: {exc}"],
            )

    content, reasoning = await _run_raw(
        prompt=payload.prompt,
        model=payload.model,
        base_url=payload.base_url,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
    )

    notes: list[str] = []
    parsed: dict[str, Any] | None = None
    if content.strip():
        try:
            parsed = json.loads(content)
            notes.append("Response is valid JSON.")
        except json.JSONDecodeError as e:
            notes.append(f"Response is not valid JSON: {e}")

    return RunTuningResponse(
        content=content,
        reasoning=reasoning,
        parsed=parsed,
        validation_notes=notes,
    )


async def _run_raw(
    prompt: str,
    model: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
) -> tuple[str, str | None]:
    """Run a raw completion in a thread to avoid blocking the event loop."""
    import functools

    fn = functools.partial(
        raw_completion,
        prompt,
        model=model,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    from omnifin.ai.structured import raw_completion as _raw

    return await asyncio.to_thread(fn)


async def _run_structured(
    prompt: str,
    model_cls: type[BaseModel],
    model: str,
    base_url: str,
    temperature: float,
    max_tokens: int,
) -> BaseModel:
    """Run a structured completion in a thread to avoid blocking the event loop."""
    import functools

    fn = functools.partial(
        structured_completion,
        prompt,
        model_cls,
        model=model,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return await asyncio.to_thread(fn)


def _model_to_dict(model: BaseModel) -> dict[str, Any]:
    """Convert a Pydantic model to a JSON-safe dict."""
    return json.loads(model.model_dump_json())
