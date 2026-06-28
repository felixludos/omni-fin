"""FastAPI server for the Omnifin web interface."""

from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI, Query
from fastapi.encoders import jsonable_encoder

from omnifin.core.db import DatabaseSession
from omnifin.models import Account, Asset, Report, Statement, Transfer

DB_ENV = "OMNIFIN_DB"

app = FastAPI(title="Omnifin API", version="0.1.0")


def db_path() -> str:
    return os.environ.get(DB_ENV, "omnifin.db")


def serialize(obj: Any) -> Any:
    if isinstance(obj, list):
        return [serialize(item) for item in obj]
    if hasattr(obj, "model_dump"):
        return jsonable_encoder(obj.model_dump(mode="json"))
    return jsonable_encoder(obj)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "database": db_path()}


@app.get("/api/assets")
def list_assets(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> list[dict[str, Any]]:
    with DatabaseSession(db_path()) as session:
        return serialize(session.all(Asset, limit=limit, offset=offset))


@app.get("/api/accounts")
def list_accounts(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> list[dict[str, Any]]:
    with DatabaseSession(db_path()) as session:
        return serialize(session.all(Account, limit=limit, offset=offset))


@app.get("/api/statements")
def list_statements(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> list[dict[str, Any]]:
    with DatabaseSession(db_path()) as session:
        return serialize(session.all(Statement, limit=limit, offset=offset))


@app.get("/api/transfers")
def list_transfers(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> list[dict[str, Any]]:
    with DatabaseSession(db_path()) as session:
        return serialize(session.all(Transfer, limit=limit, offset=offset))


@app.get("/api/reports")
def list_reports(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> list[dict[str, Any]]:
    with DatabaseSession(db_path()) as session:
        return serialize(session.all(Report, limit=limit, offset=offset))
