"""Seed data loader for Omnifin database initialization.

Loads YAML seed files from ``cloud_data/seed_data/`` and inserts them into the
database using the domain model layer (``Tag``, ``Account``, ``Asset``).
"""

from __future__ import annotations

import sqlite3
import yaml
from pathlib import Path
from typing import Any

from omnifin.models import Account, Asset, Tag


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
            tag = Tag(name=item["name"], category=item.get("category"))
            tags.append(tag)
        return tags

    def load_accounts(self) -> list[Account]:
        """Load accounts from accounts_seed.yaml and return a list of Account objects."""
        data = self._load_yaml("accounts_seed.yaml")
        accounts_data = data.get("accounts", [])
        accounts: list[Account] = []
        for item in accounts_data:
            account = Account(name=item["name"], type=item.get("type"))
            accounts.append(account)
        return accounts

    def load_assets(self) -> list[Asset]:
        """Load assets from assets_seed.yaml and return a list of Asset objects."""
        data = self._load_yaml("assets_seed.yaml")
        assets_data = data.get("assets", [])
        assets: list[Asset] = []
        for item in assets_data:
            asset = Asset(symbol=item["symbol"], name=item.get("name"), category=item.get("category"))
            assets.append(asset)
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


def _seed_if_empty(conn: sqlite3.Connection) -> None:
    """Seed the database from YAML files IF all seed tables are currently empty.

    This is a no-op when called on an already-populated database, making it safe
    to call on every ``init_db()`` invocation. It takes an open ``sqlite3.Connection``
    so it can participate in the same transaction as schema initialization.
    """
    if not _tables_are_empty(conn):
        return  # data already present — skip

    loader = SeedDataLoader("")  # path only used for file resolution; SEED_DATA_DIR is absolute
    cursor = conn.cursor()

    # --- tags -------------------------------------------------------------------
    for tag in loader.load_tags():
        tag_id_bytes = _deterministic_uuid_bytes(f"tag:{tag.name}")
        cursor.execute(
            "INSERT OR IGNORE INTO tags (tag_id, name, category) VALUES (?, ?, ?)",
            (tag_id_bytes, tag.name, tag.category),
        )

    # --- accounts ---------------------------------------------------------------
    for account in loader.load_accounts():
        acc_id_bytes = _deterministic_uuid_bytes(f"acc:{account.name}")
        cursor.execute(
            "INSERT OR IGNORE INTO accounts (account_id, name, type) VALUES (?, ?, ?)",
            (acc_id_bytes, account.name, account.type),
        )

    # --- assets -----------------------------------------------------------------
    for asset in loader.load_assets():
        category_str = asset.category.value if hasattr(asset.category, 'value') else str(asset.category) if asset.category else None
        cursor.execute(
            "INSERT OR IGNORE INTO assets (symbol, name, category) VALUES (?, ?, ?)",
            (asset.symbol, asset.name, category_str),
        )


def seed_database(db_path: str | Path = "omnifin.db") -> None:
    """Seed the database with default objects from YAML files.

    This function loads tags, accounts, and assets from their respective YAML
    files in ``cloud_data/seed_data/`` and inserts them into the database.
    It uses upsert logic to avoid duplicating existing entries.
    """
    import sqlite3
    from omnifin.core.db import DatabaseSession

    loader = SeedDataLoader(db_path)

    with DatabaseSession(db_path, initialize=True) as session:
        # Load and insert tags
        tags = loader.load_tags()
        cursor = session.conn.cursor()  # type: ignore[union-attr]
        for tag in tags:
            cursor.execute(
                "INSERT OR IGNORE INTO tags (tag_id, name, category) VALUES (?, ?, ?)",
                (str(tag.id), tag.name, tag.category),
            )

        # Load and insert accounts
        accounts = loader.load_accounts()
        for account in accounts:
            cursor.execute(
                "INSERT OR IGNORE INTO accounts (account_id, name, type) VALUES (?, ?, ?)",
                (str(account.id), account.name, account.type),
            )

        # Load and insert assets
        assets = loader.load_assets()
        for asset in assets:
            category_str = asset.category.value if hasattr(asset.category, 'value') else str(asset.category) if asset.category else None
            cursor.execute(
                "INSERT OR IGNORE INTO assets (symbol, name, category) VALUES (?, ?, ?)",
                (asset.symbol, asset.name, category_str),
            )

        session.conn.commit()  # type: ignore[union-attr]


def _deterministic_uuid_bytes(value: str) -> bytes:
    """Return deterministic UUID-like bytes derived from a content string."""
    import hashlib
    return hashlib.sha256(value.encode("utf-8")).digest()[:16]


if __name__ == "__main__":
    seed_database()
