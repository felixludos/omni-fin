"""Browse and detail API for exploring database contents."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from omnifin.core.ids import parse_uuid

router = APIRouter(prefix="/api/browse", tags=["browse"])


# ── DB path (same strategy as ingest.py) ──────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parents[3]
DB_ENV = "OMNIFIN_DB"


def _db_path() -> str:
    from omnifin.api.server import db_path as server_db_path
    return server_db_path()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _open() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _hex(val: Any) -> str | None:
    if val is None:
        return None
    if isinstance(val, (bytes, bytearray)):
        return val.hex()
    return str(val)


def _name_text(val:Any) -> str | None:
    return str(val) if val is not None else None


# ── Column definitions per model ──────────────────────────────────────────────

MODEL_DEFS: dict[str, dict[str, Any]] = {
    "assets": {
        "table": "assets",
        "pk": "symbol",
        "pk_type": "str",
        "label": "Assets",
        "low_columns": ["symbol", "name", "category", "report_id"],
        "high_columns": ["Symbol", "Name", "Category", "Type", "Identifier", "ID Type", "NYSE Ticker", "IBKR Ticker", "Country", "Fund Type", "Fund Focus"],
        "high_fields": ["symbol", "name", "category", "type", "identifier", "identifier_type", "nyse_ticker", "ibkr_ticker", "country", "fund_type", "fund_focus"],
        "search_cols": ["symbol", "name", "category"],
        "order_by": "symbol",
    },
    "accounts": {
        "table": "accounts",
        "pk": "account_id",
        "pk_type": "uuid",
        "label": "Accounts",
        "low_columns": ["account_id", "name", "type", "report_id"],
        "high_columns": ["ID", "Name", "Type", "Recorded By"],
        "high_fields": ["id", "name", "type", "recorded_by"],
        "search_cols": ["name", "type"],
        "order_by": "name",
    },
    "transfers": {
        "table": "transfers",
        "pk": "transfer_id",
        "pk_type": "uuid",
        "label": "Transfers",
        "low_columns": ["transfer_id", "date", "sender_account_id", "receiver_account_id", "asset_symbol", "amount", "report_id"],
        "high_columns": ["ID", "Date", "Sender", "Receiver", "Asset", "Amount", "Recorded By"],
        "high_fields": ["id", "date", "sender", "receiver", "asset", "amount", "recorded_by"],
        "search_cols": ["date", "asset_symbol"],
        "order_by": "date DESC",
    },
    "statements": {
        "table": "statements",
        "pk": "statement_id",
        "pk_type": "uuid",
        "label": "Statements",
        "low_columns": ["statement_id", "date", "account_id", "asset_symbol", "balance", "report_id"],
        "high_columns": ["ID", "Date", "Account", "Asset", "Balance", "Recorded By"],
        "high_fields": ["id", "date", "account", "asset", "balance", "recorded_by"],
        "search_cols": ["date", "asset_symbol"],
        "order_by": "date DESC",
    },
    "events": {
        "table": "events",
        "pk": "event_id",
        "pk_type": "uuid",
        "label": "Events",
        "low_columns": ["event_id", "name", "type"],
        "high_columns": ["ID", "Name", "Type"],
        "high_fields": ["id", "name", "type"],
        "search_cols": ["name", "type"],
        "order_by": "name",
    },
    "reports": {
        "table": "reports",
        "pk": "report_id",
        "pk_type": "uuid",
        "label": "Reports",
        "low_columns": ["report_id", "date", "name", "author"],
        "high_columns": ["ID", "Date", "Name", "Author"],
        "high_fields": ["id", "date", "name", "author"],
        "search_cols": ["name", "author"],
        "order_by": "date DESC",
    },
}

JUNCTION_TAGS: dict[str, tuple[str, str]] = {
    "assets": ("asset_tags", "asset_symbol"),
    "accounts": ("account_tags", "account_id"),
    "transfers": ("transfer_tags", "transfer_id"),
    "statements": ("statement_tags", "statement_id"),
    "events": ("event_tags", "event_id"),
    "reports": ("report_tags", "report_id"),
}

JUNCTION_COMMENTS: dict[str, tuple[str, str]] = {
    "assets": ("asset_comments", "asset_symbol"),
    "accounts": ("account_comments", "account_id"),
    "transfers": ("transfer_comments", "transfer_id"),
    "statements": ("statement_comments", "statement_id"),
    "events": ("event_comments", "event_id"),
    "reports": ("report_comments", "report_id"),
}


def _id_to_pk_value(model: str, id_str: str) -> bytes | str:
    """Convert a frontend hex ID string to the SQL column value."""
    spec = MODEL_DEFS[model]
    if spec["pk_type"] == "str":
        return id_str
    # UUID type — stored as 16-byte BLOB
    try:
        return parse_uuid(id_str).bytes
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid id: {id_str}")


def _resolve_name(conn: sqlite3.Connection, table: str, pk_col: str, pk_val: Any, name_col: str = "name") -> str | None:
    if pk_val is None:
        return None
    cur = conn.execute(f"SELECT {name_col} FROM {table} WHERE {pk_col} = ?", (pk_val,))
    row = cur.fetchone()
    if row:
        return str(row[name_col])
    return _hex(pk_val)


def _fetch_tags(conn: sqlite3.Connection, junction_table: str, owner_column: str, owner_val: Any) -> list[dict]:
    cur = conn.execute(
        f"SELECT t.tag_id, t.name, t.category FROM tags t "
        f"JOIN {junction_table} j ON j.tag_id = t.tag_id "
        f"WHERE j.{owner_column} = ? ORDER BY t.name",
        (owner_val,)
    )
    return [
        {"id": _hex(r["tag_id"]), "name": r["name"], "category": r["category"]}
        for r in cur.fetchall()
    ]


def _fetch_comments(conn: sqlite3.Connection, junction_table: str, owner_column: str, owner_val: Any) -> list[dict]:
    cur = conn.execute(
        f"SELECT c.comment_id, c.content, c.type, c.created_at FROM comments c "
        f"JOIN {junction_table} j ON j.comment_id = c.comment_id "
        f"WHERE j.{owner_column} = ? ORDER BY c.created_at",
        (owner_val,)
    )
    return [
        {"id": _hex(r["comment_id"]), "content": r["content"], "type": r["type"], "created_at": r["created_at"]}
        for r in cur.fetchall()
    ]


def _build_low_row(spec: dict, row: sqlite3.Row) -> dict[str, Any]:
    raw = dict(row)
    return {spec["low_columns"][i]: _hex(raw.get(col))
            for i, col in enumerate(spec["low_columns"])}


def _build_high_row(conn: sqlite3.Connection, model: str, spec: dict, row: sqlite3.Row) -> dict[str, Any]:
    if model == "assets":
        return _build_asset_high_row(conn, spec, row)

    raw = dict(row)
    out: dict[str, Any] = {}
    pk = spec["pk"]
    spec["table"]

    high_fields = spec["high_fields"]
    high_columns = spec["high_columns"]
    for i, hf in enumerate(high_fields):
        lc = spec["low_columns"][i]
        val = raw.get(lc)
        key = high_columns[i]

        if hf == "id":
            out[key] = _hex(val) if pk != "symbol" else val
        elif hf == "recorded_by":
            out[key] = _resolve_name(conn, "reports", "report_id", val)
        elif hf == "sender":
            out[key] = _resolve_name(conn, "accounts", "account_id", val)
        elif hf == "receiver":
            out[key] = _resolve_name(conn, "accounts", "account_id", val)
        elif hf == "account":
            out[key] = _resolve_name(conn, "accounts", "account_id", val)
        elif hf == "asset":
            out[key] = val  # already the symbol string
        elif hf == "date":
            out[key] = str(val) if val else None
        elif hf in ("amount", "balance"):
            out[key] = float(val) if val is not None else None
        else:
            out[key] = _name_text(val)

    return out


def _build_asset_high_row(conn: sqlite3.Connection, spec: dict, row: sqlite3.Row) -> dict[str, Any]:
    raw = dict(row)
    symbol = raw.get("symbol", "")

    # Fetch investment comments for this symbol
    comments: dict[str, str] = {}
    cur = conn.execute(
        "SELECT c.type, c.content FROM asset_comments ac "
        "JOIN comments c ON c.comment_id = ac.comment_id "
        "WHERE ac.asset_symbol = ? AND c.type IN (?, ?, ?)",
        (symbol, "nyse_ticker", "ibkr_ticker", "asset_identifier"),
    )
    for r in cur.fetchall():
        comments[r["type"]] = r["content"]

    # Fetch investment tags for this symbol
    tags: dict[str, str] = {}
    cur = conn.execute(
        "SELECT t.category, t.name FROM asset_tags at "
        "JOIN tags t ON t.tag_id = at.tag_id "
        "WHERE at.asset_symbol = ? AND t.category IN (?, ?, ?, ?)",
        (symbol, "asset_identifier_type", "country", "fund_type", "fund_focus"),
    )
    for r in cur.fetchall():
        tags[r["category"]] = r["name"]

    has_investment_meta = bool(comments) or bool(tags)

    return {
        "Symbol": raw.get("symbol"),
        "Name": raw.get("name"),
        "Category": raw.get("category"),
        "Type": "Security" if has_investment_meta else "Asset",
        "Identifier": comments.get("asset_identifier"),
        "ID Type": tags.get("asset_identifier_type"),
        "NYSE Ticker": comments.get("nyse_ticker"),
        "IBKR Ticker": comments.get("ibkr_ticker"),
        "Country": tags.get("country"),
        "Fund Type": tags.get("fund_type"),
        "Fund Focus": tags.get("fund_focus"),
    }


def _fetch_column_hints(conn: sqlite3.Connection, model: str) -> dict[str, list[str]]:
    """Return possible values for categorical columns shown in the table."""
    hints: dict[str, list[str]] = {}
    if model != "assets":
        return hints

    # Distinct values from assets.category
    cur = conn.execute("SELECT DISTINCT category FROM assets WHERE category IS NOT NULL")
    vals = [str(r["category"]) for r in cur.fetchall() if r["category"] is not None]
    if vals:
        hints["Category"] = vals

    # Distinct tag values per category for investment-related tags
    # Map tag categories to their display column names
    col_map: dict[str, str] = {
        "asset_identifier_type": "ID Type",
        "country": "Country",
        "fund_type": "Fund Type",
        "fund_focus": "Fund Focus",
    }
    for tag_cat, col_name in col_map.items():
        cur = conn.execute(
            "SELECT DISTINCT t.name FROM asset_tags at "
            "JOIN tags t ON t.tag_id = at.tag_id "
            "WHERE t.category = ? ORDER BY t.name",
            (tag_cat,),
        )
        vals = [str(r["name"]) for r in cur.fetchall() if r["name"] is not None]
        if vals:
            hints[col_name] = vals

    return hints


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/{model}")
def browse_list(
    model: str,
    q: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    spec = MODEL_DEFS.get(model)
    if not spec:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model}")

    conn = _open()
    try:
        table = spec["table"]
        pk = spec["pk"]
        select_cols = ", ".join(spec["low_columns"])
        search_cols = spec["search_cols"]
        order_by = spec["order_by"]

        base_sql = f"SELECT {select_cols} FROM {table}"
        params: list[Any] = []

        if q:
            clauses = []
            for col in search_cols:
                clauses.append(f"{col} LIKE ?")
                params.append(f"%{q}%")
            base_sql += " WHERE " + " OR ".join(clauses)

        # Count
        count_sql = base_sql.replace(f"SELECT {select_cols}", "SELECT COUNT(*)", 1)
        count_row = conn.execute(count_sql, params).fetchone()
        total = count_row[0] if count_row else 0

        # Fetch
        data_sql = base_sql + f" ORDER BY {order_by} LIMIT ? OFFSET ?"
        rows = conn.execute(data_sql, params + [limit, offset]).fetchall()

        # Build result rows
        result_rows = []
        for row in rows:
            raw = dict(row)
            result_rows.append({
                "id": _hex(raw.get(pk)) if spec["pk_type"] != "str" else str(raw.get(pk, "")),
                "low": _build_low_row(spec, row),
                "high": _build_high_row(conn, model, spec, row),
            })

        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "low_columns": spec["low_columns"],
            "high_columns": spec["high_columns"],
            "rows": result_rows,
            "column_hints": _fetch_column_hints(conn, model),
        }
    finally:
        conn.close()


@router.get("/{model}/{id}")
def browse_detail(model: str, id: str) -> dict[str, Any]:
    spec = MODEL_DEFS.get(model)
    if not spec:
        raise HTTPException(status_code=404, detail=f"Unknown model: {model}")

    pk_val = _id_to_pk_value(model, id)
    conn = _open()
    try:
        table = spec["table"]
        pk = spec["pk"]
        select_cols = ", ".join(spec["low_columns"])

        cur = conn.execute(f"SELECT {select_cols} FROM {table} WHERE {pk} = ?", (pk_val,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"{model}/{id} not found")

        low = _build_low_row(spec, row)
        high = _build_high_row(conn, model, spec, row)

        # Tags & comments
        tags = []
        comments = []
        if model in JUNCTION_TAGS:
            jt, owner_col = JUNCTION_TAGS[model]
            tags = _fetch_tags(conn, jt, owner_col, pk_val)
        if model in JUNCTION_COMMENTS:
            jc, owner_col = JUNCTION_COMMENTS[model]
            comments = _fetch_comments(conn, jc, owner_col, pk_val)

        # Related objects
        related: dict[str, Any] = {}

        if model == "assets":
            pass

        elif model == "accounts":
            # Associated entities
            ent_cur = conn.execute(
                "SELECT e.entity_id, e.name, e.legal_type, ea.relationship "
                "FROM entities e "
                "JOIN entity_accounts ea ON ea.entity_id = e.entity_id "
                "WHERE ea.account_id = ? ORDER BY e.name",
                (pk_val,)
            )
            entities = []
            for er in ent_cur.fetchall():
                entities.append({
                    "id": _hex(er["entity_id"]),
                    "name": er["name"],
                    "legal_type": er["legal_type"],
                    "relationship": er["relationship"],
                })
            related["entities"] = entities

        elif model == "transfers":
            # Sender account
            sender_id = row["sender_account_id"]
            receiver_id = row["receiver_account_id"]
            row["asset_symbol"]
            if sender_id:
                srow = conn.execute("SELECT account_id, name, type FROM accounts WHERE account_id = ?", (sender_id,)).fetchone()
                if srow:
                    related["sender_account"] = {
                        "id": _hex(srow["account_id"]),
                        "name": srow["name"],
                        "type": srow["type"],
                    }
            if receiver_id:
                rrow = conn.execute("SELECT account_id, name, type FROM accounts WHERE account_id = ?", (receiver_id,)).fetchone()
                if rrow:
                    related["receiver_account"] = {
                        "id": _hex(rrow["account_id"]),
                        "name": rrow["name"],
                        "type": rrow["type"],
                    }
            # Linked events
            ev_cur = conn.execute(
                "SELECT e.event_id, e.name, e.type, tx.association "
                "FROM events e "
                "JOIN transactions tx ON tx.event_id = e.event_id "
                "WHERE tx.transfer_id = ? ORDER BY e.name",
                (pk_val,)
            )
            events = []
            for ev in ev_cur.fetchall():
                ev_tags = _fetch_tags(conn, "event_tags", "event_id", ev["event_id"])
                ev_comments = _fetch_comments(conn, "event_comments", "event_id", ev["event_id"])
                events.append({
                    "id": _hex(ev["event_id"]),
                    "name": ev["name"],
                    "type": ev["type"],
                    "association": ev["association"],
                    "tags": ev_tags,
                    "comments": ev_comments,
                })
            related["events"] = events

        elif model == "statements":
            acct_id = row["account_id"]
            if acct_id:
                arow = conn.execute("SELECT account_id, name, type FROM accounts WHERE account_id = ?", (acct_id,)).fetchone()
                if arow:
                    related["account"] = {
                        "id": _hex(arow["account_id"]),
                        "name": arow["name"],
                        "type": arow["type"],
                    }

        elif model == "events":
            # Linked transfers (reverse of transactions)
            tx_cur = conn.execute(
                "SELECT t.transfer_id, t.date, t.asset_symbol, t.amount, "
                "       t.sender_account_id, t.receiver_account_id, tx.association "
                "FROM transfers t "
                "JOIN transactions tx ON tx.transfer_id = t.transfer_id "
                "WHERE tx.event_id = ? ORDER BY t.date",
                (pk_val,)
            )
            transfers = []
            for tr in tx_cur.fetchall():
                sender_name = _resolve_name(conn, "accounts", "account_id", tr["sender_account_id"])
                receiver_name = _resolve_name(conn, "accounts", "account_id", tr["receiver_account_id"])
                transfers.append({
                    "id": _hex(tr["transfer_id"]),
                    "date": str(tr["date"]) if tr["date"] else None,
                    "asset_symbol": tr["asset_symbol"],
                    "amount": tr["amount"],
                    "sender": sender_name,
                    "receiver": receiver_name,
                    "association": tr["association"],
                })
            related["transfers"] = transfers

        elif model == "reports":
            pass

        return {
            "low": low,
            "high": high,
            "tags": tags,
            "comments": comments,
            "related": related,
        }
    finally:
        conn.close()


@router.get("/search/all")
def browse_search(
    q: str = Query(..., min_length=1),
    limit: int = Query(5, ge=1, le=50),
) -> dict[str, list[dict[str, Any]]]:
    """Cross-model search — returns top matches from each model."""
    conn = _open()
    try:
        results: dict[str, list[dict[str, Any]]] = {}
        for model, spec in MODEL_DEFS.items():
            table = spec["table"]
            pk = spec["pk"]
            search_cols = spec["search_cols"]
            select_cols = ", ".join(spec["low_columns"])

            clauses = [f"{col} LIKE ?" for col in search_cols]
            params = [f"%{q}%"] * len(search_cols)
            where = " OR ".join(clauses)

            cur = conn.execute(
                f"SELECT {select_cols} FROM {table} WHERE {where} ORDER BY {spec['order_by']} LIMIT ?",
                params + [limit],
            )
            hits = []
            for row in cur.fetchall():
                raw = dict(row)
                hits.append({
                    "id": _hex(raw.get(pk)) if spec["pk_type"] != "str" else str(raw.get(pk, "")),
                    "low": _build_low_row(spec, row),
                    "high": _build_high_row(conn, model, spec, row),
                })
            if hits:
                results[model] = hits

        return results
    finally:
        conn.close()
