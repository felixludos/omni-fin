"""FastAPI server for the Omnifin web interface."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from omnifin.api.ingest import router as ingest_router
from omnifin.core.db import DatabaseSession
from omnifin.models import Account, Asset, Investment, InvestmentSale, Report, Statement, Transfer

DB_ENV = "OMNIFIN_DB"
SCAN_DIR_ENV = "OMNIFIN_DB_DIR"

# Mutable runtime state so the frontend can switch databases without restarting.
_current_db_path: str | None = None

app = FastAPI(title="Omnifin API", version="0.1.0")
app.include_router(ingest_router)

# Allow frontend dev server to proxy requests without CORS issues.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def db_path() -> str:
    if _current_db_path is not None:
        return _current_db_path
    val = os.environ.get(DB_ENV)
    if val:
        return val
    repo_root = Path(__file__).resolve().parents[3]
    return str(repo_root / "cloud_data" / "omnifin.db")


def _scan_dir() -> Path:
    """Directory to scan for .db files and create new databases."""
    env_dir = os.environ.get(SCAN_DIR_ENV)
    if env_dir:
        return Path(env_dir)
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "cloud_data"


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


@app.get("/api/investments")
def list_investments(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> list[dict[str, Any]]:
    with DatabaseSession(db_path()) as session:
        return serialize(session.all(Investment, limit=limit, offset=offset))


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


@app.get("/api/investment-sales")
def list_investment_sales(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)) -> list[dict[str, Any]]:
    with DatabaseSession(db_path()) as session:
        return serialize(session.all(InvestmentSale, limit=limit, offset=offset))


# ── Database management endpoints ──────────────────────────────────────────────


class DbInfoResponse(BaseModel):
    path: str
    filename: str
    exists: bool
    size_bytes: int
    dir: str


class DbFileInfo(BaseModel):
    path: str
    filename: str
    size_bytes: int


@app.get("/api/db", response_model=DbInfoResponse)
def get_db_info() -> DbInfoResponse:
    path = db_path()
    p = Path(path)
    return DbInfoResponse(
        path=path,
        filename=p.name,
        exists=p.exists(),
        size_bytes=p.stat().st_size if p.exists() else 0,
        dir=str(p.parent),
    )


@app.get("/api/db/scan", response_model=list[DbFileInfo])
def scan_databases() -> list[DbFileInfo]:
    scan_dir = _scan_dir()
    if not scan_dir.is_dir():
        return []
    results: list[DbFileInfo] = []
    for p in sorted(scan_dir.glob("*.db")):
        results.append(
            DbFileInfo(path=str(p), filename=p.name, size_bytes=p.stat().st_size)
        )
    return results


class OpenDbRequest(BaseModel):
    path: str


@app.post("/api/db/open", response_model=DbInfoResponse)
def open_database(payload: OpenDbRequest) -> DbInfoResponse:
    p = Path(payload.path)
    if not p.exists():
        raise HTTPException(status_code=404, detail=f"Database file not found: {payload.path}")
    if not p.is_file():
        raise HTTPException(status_code=400, detail="Not a file")

    # Validate the file is a readable SQLite database
    try:
        with DatabaseSession(str(p), initialize=False) as session:
            session.execute("SELECT 1")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Not a valid SQLite database: {exc}")

    global _current_db_path
    _current_db_path = str(p)

    return DbInfoResponse(
        path=str(p),
        filename=p.name,
        exists=True,
        size_bytes=p.stat().st_size,
        dir=str(p.parent),
    )


class CreateDbRequest(BaseModel):
    filename: str


@app.post("/api/db/create", response_model=DbInfoResponse)
def create_database(payload: CreateDbRequest) -> DbInfoResponse:
    filename = payload.filename.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="filename cannot be empty")

    # Normalize – append .db if no extension
    if "." not in filename:
        filename = filename + ".db"

    db_dir = _scan_dir()
    db_dir.mkdir(parents=True, exist_ok=True)
    db_path_str = str(db_dir / filename)

    if Path(db_path_str).exists():
        raise HTTPException(
            status_code=409,
            detail=f"Database already exists: {db_path_str}",
        )

    try:
        with DatabaseSession(db_path_str) as session:
            pass
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create database: {exc}")

    global _current_db_path
    _current_db_path = db_path_str

    p = Path(db_path_str)
    return DbInfoResponse(
        path=str(p),
        filename=p.name,
        exists=True,
        size_bytes=p.stat().st_size,
        dir=str(p.parent),
    )
