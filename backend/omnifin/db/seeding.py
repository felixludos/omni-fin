"""Seed data loader for Omnifin database initialization.

Loads YAML seed files from ``cloud_data/seed_data/`` and inserts them into the
database using the domain model layer (``Tag``, ``Account``, ``Asset``).
"""

from __future__ import annotations

import hashlib
import sqlite3
import yaml
from pathlib import Path
from typing import Any

from omnifin.models import Account, Asset, Tag, Investment


SEED_DATA_DIR = Path(__file__).resolve().parents[3] / "cloud_data" / "seed_data"


class SeedDataLoader:
    """Loads seed data from YAML files and inserts into the database."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)

    def load_tags(self) -> list[Tag]:
        """Load tags from tags_seed.yaml and return a list of Tag objects."""
        data = self._load_yaml("tags_seed.yaml")
        tags_data = data.get("tags", [])
        tags: list[Tag] = []
        for item in tags_data:
            tag = Tag(name=item["name"], 
                      category=item.get("category"))
            tags.append(tag)
        return tags

    def load_accounts(self) -> list[Account]:
        """Load accounts from accounts_seed.yaml and return a list of Account objects."""
        data = self._load_yaml("accounts_seed.yaml")
        accounts_data = data.get("accounts", [])
        accounts: list[Account] = []
        for item in accounts_data:
            account = Account(name=item["name"],
                              type=item.get("type"),
                              institution=item.get("institution"))
            accounts.append(account)
            for tag in item.get("tags", []):
                account.add_tags(Tag(name=tag))
        return accounts

    def load_assets(self) -> list[Asset]:
        """Load assets from assets_seed.yaml and return a list of Asset objects."""
        data = self._load_yaml("assets_seed.yaml")
        assets_data = data.get("assets", [])
        investment_data = data.get("investments", [])
        assets: list[Asset] = []
        for item in assets_data:
            asset = Asset(symbol=item["symbol"], 
                          name=item.get("name"), 
                          category=item.get("category"))
            assets.append(asset)
            for tag in item.get("tags", []):
                asset.add_tags(Tag(name=tag))
        for item in investment_data:
            investment = Investment(symbol=item["symbol"], 
                                    name=item.get("name"), 
                                    category=item.get("category"), 
                                    identifier=item.get("identifier"),
                                    nyse_ticker=item.get("nyse_ticker"), 
                                    ibkr_ticker=item.get("ibkr_ticker"),
                                    country=item.get("country"), 
                                    fund_type=item.get("fund_type"), 
                                    fund_focus=item.get("fund_focus"))
            assets.append(investment)
            for tag in item.get("tags", []):
                investment.add_tags(Tag(name=tag))
        return assets

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        """Load a YAML file from the seed data directory and parse it."""
        yaml_path = SEED_DATA_DIR / filename
        if not yaml_path.exists():
            raise FileNotFoundError(f"Seed data file not found: {yaml_path}")

        with open(yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


def _tables_are_empty(conn: sqlite3.Connection) -> bool:
    """Return True if all three seed tables (tags, accounts, assets) are empty.

    Handles both ``dict_factory`` and default tuple row_factory by extracting
    the first value from each fetched row safely.
    """
    for table in ("tags", "accounts", "assets"):
        cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
        row = cursor.fetchone()
        if row is None:
            continue
        # Extract the count value regardless of row_factory type.
        if isinstance(row, dict):
            # dict_factory returns a dict like {"COUNT(*)": 0}
            count_val = next(iter(row.values()), 0)
        else:
            # tuple access: (0,) for COUNT(*)
            count_val = int(row[0])
        if count_val > 0:
            return False
    return True


def _create_seed_report(conn: sqlite3.Connection) -> bytes:
    """Create a dedicated ``reports`` row for seed data and return its report_id.

    The seed report carries provenance context so all seeded objects can be
    traced back to the initialization event rather than being orphaned (NULL).
    Uses a deterministic UUID derived from a fixed content string so re-running
    on an already-seeded DB produces no duplicates via ``INSERT OR IGNORE``.
    """
    import datetime

    report_id = _deterministic_uuid_bytes("seed:report")
    today = datetime.date.today().isoformat()  # e.g. "2026-07-01"

    conn.execute(
        "INSERT OR IGNORE INTO reports (report_id, date, name, author) VALUES (?, ?, ?, ?)",
        (report_id, today, "System Seed", "omnifin"),
    )
    return report_id


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    """Seed the database from YAML files IF all seed tables are currently empty.

    This is a no-op when called on an already-populated database, making it safe
    to call on every ``init_db()`` invocation. It takes an open ``sqlite3.Connection``
    so it can participate in the same transaction as schema initialization.

    All seeded objects are linked to a dedicated "System Seed" report for provenance.
    """
    if not _tables_are_empty(conn):
        return  # data already present — skip

    loader = SeedDataLoader("")  # path only used for file resolution; SEED_DATA_DIR is absolute
    cursor = conn.cursor()

    # Create a dedicated seed report for provenance tracking.
    seed_report_id = _create_seed_report(conn)

    # --- tags -------------------------------------------------------------------
    for tag in loader.load_tags():
        tag_id_bytes = _deterministic_uuid_bytes(f"tag:{tag.name}")
        cursor.execute(
            "INSERT OR IGNORE INTO tags (tag_id, name, category, report_id) VALUES (?, ?, ?, ?)",
            (tag_id_bytes, tag.name, tag.category, seed_report_id),
        )

    # --- accounts ---------------------------------------------------------------
    for account in loader.load_accounts():
        acc_id_bytes = _deterministic_uuid_bytes(f"acc:{account.name}")
        cursor.execute(
            "INSERT OR IGNORE INTO accounts (account_id, name, type, report_id) VALUES (?, ?, ?, ?)",
            (acc_id_bytes, account.name, account.type, seed_report_id),
        )

    # --- assets -----------------------------------------------------------------
    for asset in loader.load_assets():
        category_str = asset.category.value if hasattr(asset.category, 'value') else str(asset.category) if asset.category else None
        cursor.execute(
            "INSERT OR IGNORE INTO assets (symbol, name, category, report_id) VALUES (?, ?, ?, ?)",
            (asset.symbol, asset.name, category_str, seed_report_id),
        )


def _is_connection(obj: object) -> bool:
    """Duck-typing check for a sqlite3.Connection."""
    if not hasattr(obj, "execute"):
        return False
    # Verify it's actually a Connection by checking its type name.
    cls_name = type(obj).__name__
    return cls_name == "Connection"


def seed_database(db_path: str | Path | sqlite3.Connection = "omnifin.db") -> None:
    """Seed the database with default objects from YAML files.

    This function loads tags, accounts, and assets from their respective YAML
    files in ``cloud_data/seed_data/`` and inserts them into the database.
    It uses upsert logic to avoid duplicating existing entries and links all
    seeded objects to a dedicated "System Seed" report for provenance tracking.

    Args:
        db_path: Either a path-like object (str | Path) or an open sqlite3.Connection.
                 When a connection is passed, it will be used directly without creating
                 a new DatabaseSession. When a path is passed, the database at that path
                 is initialized and seeded.
    """
    if _is_connection(db_path):  # type: ignore[arg-type]
        seed_database_with_conn(db_path)  # type: ignore[arg-type]
        return

    from omnifin.core.db import DatabaseSession
    session = DatabaseSession(db_path, initialize=True)
    with session:
        seed_database_with_conn(session.conn)  # type: ignore[arg-type]


def _tag_bytes(tag: Tag) -> bytes:
    """Return deterministic UUID-like bytes for a tag."""
    return hashlib.sha256(f"tag:{tag.name}".encode()).digest()[:16]


def _account_bytes(account: Account) -> bytes:
    """Return deterministic UUID-like bytes for an account."""
    return hashlib.sha256(f"acc:{account.name}".encode()).digest()[:16]


def _seed_investment_metadata(
    cursor: sqlite3.Cursor,
    investment: Investment,
    raw_item: dict[str, Any],
    seed_report_id: bytes,
) -> None:
    """Create comments and tags for investment metadata fields.

    Maps Investment domain fields (nyse_ticker, ibkr_ticker, identifier) to
    comments and raw YAML fields (identifier_type, country, fund_type,
    fund_focus) to tags.  Null-valued fields are skipped.
    """
    import datetime

    symbol = investment.symbol
    now = datetime.datetime.now().isoformat()

    # --- Comments: nyse_ticker, ibkr_ticker, identifier -----------------------
    comment_mapping: dict[str, tuple[str, Any]] = {
        "nyse_ticker": ("nyse_ticker", getattr(investment, "nyse_ticker", None)),
        "ibkr_ticker": ("ibkr_ticker", getattr(investment, "ibkr_ticker", None)),
        "identifier": ("asset_identifier", getattr(investment, "identifier", None)),
    }

    for comment_type, value in comment_mapping.values():
        if value is None:
            continue
        content = str(value)
        comment_id = _deterministic_uuid_bytes(f"comment:{symbol}:{comment_type}")
        cursor.execute(
            "INSERT OR IGNORE INTO comments (comment_id, content, type, created_at, report_id) VALUES (?, ?, ?, ?, ?)",
            (comment_id, content, comment_type, now, seed_report_id),
        )
        cursor.execute(
            "INSERT OR IGNORE INTO asset_comments (asset_symbol, comment_id) VALUES (?, ?)",
            (symbol, comment_id),
        )

    # --- Tags: identifier_type, country, fund_type, fund_focus ----------------
    tag_mapping: dict[str, tuple[str, Any]] = {
        "identifier_type": ("asset_identifier_type", raw_item.get("identifier_type")),
        "country": ("country", raw_item.get("country")),
        "fund_type": ("fund_type", raw_item.get("fund_type")),
        "fund_focus": ("fund_focus", raw_item.get("fund_focus")),
    }

    for category, value in tag_mapping.values():
        if value is None:
            continue
        name = str(value)
        tag_id = _deterministic_uuid_bytes(f"tag:{symbol}:{category}")
        cursor.execute(
            "INSERT OR IGNORE INTO tags (tag_id, name, category, report_id) VALUES (?, ?, ?, ?)",
            (tag_id, name, category, seed_report_id),
        )
        cursor.execute(
            "INSERT OR IGNORE INTO asset_tags (asset_symbol, tag_id) VALUES (?, ?)",
            (symbol, tag_id),
        )


def seed_database_with_conn(conn: sqlite3.Connection) -> None:
    """Internal helper that seeds using an open connection.

    Called by ``seed_database`` after resolving the appropriate connection source.
    """
    loader = SeedDataLoader("")

    # Create seed report if not already present (idempotent).
    seed_report_id = _create_seed_report(conn)

    cursor = conn.cursor()

    # Load and insert tags
    tags = loader.load_tags()
    for tag in tags:
        cursor.execute(
            "INSERT OR IGNORE INTO tags (tag_id, name, category, report_id) VALUES (?, ?, ?, ?)",
            (_tag_bytes(tag), tag.name, tag.category, seed_report_id),
        )

    # Load and insert accounts
    accounts = loader.load_accounts()
    for account in accounts:
        cursor.execute(
            "INSERT OR IGNORE INTO accounts (account_id, name, type, report_id) VALUES (?, ?, ?, ?)",
            (_account_bytes(account), account.name, account.type, seed_report_id),
        )

    # Load and insert assets
    assets = loader.load_assets()
    for asset in assets:
        category_str = asset.category.value if hasattr(asset.category, 'value') else str(asset.category) if asset.category else None
        cursor.execute(
            "INSERT OR IGNORE INTO assets (symbol, name, category, report_id) VALUES (?, ?, ?, ?)",
            (asset.symbol, asset.name, category_str, seed_report_id),
        )

    # --- Investment metadata --------------------------------------------------
    raw_data = loader._load_yaml("assets_seed.yaml")
    raw_investments = {item["symbol"]: item for item in raw_data.get("investments", [])}

    for asset in assets:
        if isinstance(asset, Investment) and asset.symbol in raw_investments:
            _seed_investment_metadata(cursor, asset, raw_investments[asset.symbol], seed_report_id)

    conn.commit()


def _deterministic_uuid_bytes(value: str) -> bytes:
    """Return deterministic UUID-like bytes derived from a content string."""
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).digest()[:16]


if __name__ == "__main__":
    seed_database()
