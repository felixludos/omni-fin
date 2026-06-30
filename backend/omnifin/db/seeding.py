"""Seed data loader for Omnifin database initialization.

Loads YAML seed files from ``cloud_data/seed_data/`` and inserts them into the
database using the domain model layer (``Tag``, ``Account``, ``Asset``).
"""

from __future__ import annotations

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


if __name__ == "__main__":
    seed_database()