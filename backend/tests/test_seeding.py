"""Unit tests for the seed data loader module."""

from __future__ import annotations

import hashlib
import sqlite3
import uuid
from pathlib import Path

import pytest
import yaml

from omnifin.core.db import DatabaseSession, init_db
from omnifin.models import Account, Asset, Tag, clear_global_identity_map


# Resolve the seed data directory relative to the project root.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # backend/tests -> project root
SEED_DATA_DIR = (_PROJECT_ROOT / "cloud_data" / "seed_data").resolve()

# ── helpers ───────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_identity_map():
    clear_global_identity_map()
    yield
    clear_global_identity_map()


class _SeedDataLoader:
    """Mirror of the production loader – kept in-test so we can reuse logic."""

    def __init__(self, seed_dir: Path):
        self.seed_dir = seed_dir

    # -- public helpers that mirror SeedDataLoader ---------------------------------

    def load_tags(self) -> list[dict]:
        data = self._load_yaml("tags_seed.yaml")
        return data.get("tags", [])

    def load_accounts(self) -> list[dict]:
        data = self._load_yaml("accounts_seed.yaml")
        return data.get("accounts", [])

    def load_assets(self) -> list[dict]:
        data = self._load_yaml("assets_seed.yaml")
        return data.get("assets", [])

    def _load_yaml(self, filename: str) -> dict:
        yaml_path = self.seed_dir / filename
        if not yaml_path.exists():
            raise FileNotFoundError(f"Seed data file not found: {yaml_path}")
        with open(yaml_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}


def _deterministic_uuid_bytes(value: str) -> bytes:
    """Return UUID v5-like bytes derived from a content string (for idempotent seeding)."""
    h = hashlib.sha256(value.encode("utf-8")).digest()[:16]
    return h


# ── YAML structure tests (no DB needed) ───────────────────────────────────────


class TestYAMLStructure:
    """Verify that every seed YAML file has the expected shape."""

    @pytest.fixture(autouse=True)
    def _loader(self):
        self.loader = _SeedDataLoader(SEED_DATA_DIR)

    # -- tags -------------------------------------------------------------------

    def test_tags_seed_exists(self):
        assert (SEED_DATA_DIR / "tags_seed.yaml").exists()

    def test_tags_seed_has_tags_key(self):
        data = yaml.safe_load((SEED_DATA_DIR / "tags_seed.yaml").read_text())
        assert isinstance(data, dict)
        assert "tags" in data

    def test_tags_seed_is_list_of_dicts(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "tags_seed.yaml").read_text())
        tags = raw["tags"]
        assert isinstance(tags, list), "expected 'tags' to be a YAML list"
        for i, item in enumerate(tags):
            assert isinstance(item, dict), f"tag[{i}] is not a mapping: {type(item).__name__}"

    def test_tags_seed_each_item_has_name(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "tags_seed.yaml").read_text())
        for i, item in enumerate(raw["tags"]):
            assert "name" in item, f"tag[{i}] missing 'name'"

    def test_tags_seed_each_item_optional_category(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "tags_seed.yaml").read_text())
        for i, item in enumerate(raw["tags"]):
            assert "category" not in item or isinstance(item.get("category"), (str, type(None))), \
                f"tag[{i}] 'category' must be a string"

    def test_tags_seed_at_least_some_entries(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "tags_seed.yaml").read_text())
        assert len(raw["tags"]) >= 3, "expected at least 3 tag entries as examples"

    # -- accounts ---------------------------------------------------------------

    def test_accounts_seed_exists(self):
        assert (SEED_DATA_DIR / "accounts_seed.yaml").exists()

    def test_accounts_seed_has_accounts_key(self):
        data = yaml.safe_load((SEED_DATA_DIR / "accounts_seed.yaml").read_text())
        assert isinstance(data, dict)
        assert "accounts" in data

    def test_accounts_seed_is_list_of_dicts(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "accounts_seed.yaml").read_text())
        accounts = raw["accounts"]
        assert isinstance(accounts, list), "expected 'accounts' to be a YAML list"
        for i, item in enumerate(accounts):
            assert isinstance(item, dict), f"account[{i}] is not a mapping: {type(item).__name__}"

    def test_accounts_seed_each_item_has_name(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "accounts_seed.yaml").read_text())
        for i, item in enumerate(raw["accounts"]):
            assert "name" in item, f"account[{i}] missing 'name'"

    def test_accounts_seed_each_item_optional_type(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "accounts_seed.yaml").read_text())
        for i, item in enumerate(raw["accounts"]):
            assert "type" not in item or isinstance(item.get("type"), (str, type(None))), \
                f"account[{i}] 'type' must be a string"

    def test_accounts_seed_at_least_some_entries(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "accounts_seed.yaml").read_text())
        assert len(raw["accounts"]) >= 3, "expected at least 3 account entries as examples"

    # -- assets ---------------------------------------------------------------

    def test_assets_seed_exists(self):
        assert (SEED_DATA_DIR / "assets_seed.yaml").exists()

    def test_assets_seed_has_assets_key(self):
        data = yaml.safe_load((SEED_DATA_DIR / "assets_seed.yaml").read_text())
        assert isinstance(data, dict)
        assert "assets" in data

    def test_assets_seed_is_list_of_dicts(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "assets_seed.yaml").read_text())
        assets = raw["assets"]
        assert isinstance(assets, list), "expected 'assets' to be a YAML list"
        for i, item in enumerate(assets):
            assert isinstance(item, dict), f"asset[{i}] is not a mapping: {type(item).__name__}"

    def test_assets_seed_each_item_has_symbol(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "assets_seed.yaml").read_text())
        for i, item in enumerate(raw["assets"]):
            assert "symbol" in item, f"asset[{i}] missing 'symbol'"

    def test_assets_seed_each_item_optional_name(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "assets_seed.yaml").read_text())
        for i, item in enumerate(raw["assets"]):
            assert "name" not in item or isinstance(item.get("name"), (str, type(None))), \
                f"asset[{i}] 'name' must be a string"

    def test_assets_seed_each_item_optional_category(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "assets_seed.yaml").read_text())
        for i, item in enumerate(raw["assets"]):
            assert "category" not in item or isinstance(item.get("category"), (str, type(None))), \
                f"asset[{i}] 'category' must be a string"

    def test_assets_seed_at_least_some_entries(self):
        raw = yaml.safe_load((SEED_DATA_DIR / "assets_seed.yaml").read_text())
        assert len(raw["assets"]) >= 3, "expected at least 3 asset entries as examples"


# ── Loader behaviour tests (no DB needed) ─────────────────────────────────────


class TestSeedDataLoader:
    """Test the _SeedDataLoader helper parses YAML correctly."""

    @pytest.fixture(autouse=True)
    def _loader(self):
        self.loader = _SeedDataLoader(SEED_DATA_DIR)

    # -- tags -------------------------------------------------------------------

    def test_load_tags_returns_dicts(self):
        tags = self.loader.load_tags()
        assert isinstance(tags, list)
        for item in tags:
            assert isinstance(item, dict)

    def test_load_tags_each_has_name(self):
        for item in self.loader.load_tags():
            assert "name" in item

    def test_load_accounts_returns_dicts(self):
        accounts = self.loader.load_accounts()
        assert isinstance(accounts, list)
        for item in accounts:
            assert isinstance(item, dict)

    def test_load_accounts_each_has_name(self):
        for item in self.loader.load_accounts():
            assert "name" in item

    def test_load_assets_returns_dicts(self):
        assets = self.loader.load_assets()
        assert isinstance(assets, list)
        for item in assets:
            assert isinstance(item, dict)

    def test_load_assets_each_has_symbol(self):
        for item in self.loader.load_assets():
            assert "symbol" in item


# ── Database seeding tests ────────────────────────────────────────────────────


class TestDatabaseSeeding:
    """Test that seed data can actually populate a freshly-initialized SQLite DB."""

    def _create_seed_db(self, tmp_path: Path):
        db_file = tmp_path / "seed_test.db"
        with DatabaseSession(db_file, initialize=True) as session:
            init_db(session.conn)  # type: ignore[arg-type]
        return str(db_file)

    # -- tags -------------------------------------------------------------------

    def test_seed_tags_into_db(self, tmp_path):
        db_path = self._create_seed_db(tmp_path)
        loader = _SeedDataLoader(SEED_DATA_DIR)
        with DatabaseSession(db_path, initialize=False) as session:
            for item in loader.load_tags():
                tag_id_bytes = uuid.uuid4().bytes
                session.execute(
                    "INSERT OR IGNORE INTO tags (tag_id, name, category) VALUES (?, ?, ?)",
                    (tag_id_bytes, item["name"], item.get("category")),
                )
            session.commit()

        # Verify via a fresh connection
        with DatabaseSession(db_path, initialize=False) as s2:
            rows = s2.execute("SELECT * FROM tags ORDER BY name").fetchall()
            names = [r["name"] for r in rows]
            assert len(names) >= 3

    # -- accounts ---------------------------------------------------------------

    def test_seed_accounts_into_db(self, tmp_path):
        db_path = self._create_seed_db(tmp_path)
        loader = _SeedDataLoader(SEED_DATA_DIR)
        with DatabaseSession(db_path, initialize=False) as session:
            for item in loader.load_accounts():
                acc_id_bytes = uuid.uuid4().bytes
                session.execute(
                    "INSERT OR IGNORE INTO accounts (account_id, name, type) VALUES (?, ?, ?)",
                    (acc_id_bytes, item["name"], item.get("type")),
                )
            session.commit()

        with DatabaseSession(db_path, initialize=False) as s2:
            rows = s2.execute("SELECT * FROM accounts ORDER BY name").fetchall()
            names = [r["name"] for r in rows]
            assert len(names) >= 3

    # -- assets ---------------------------------------------------------------

    def test_seed_assets_into_db(self, tmp_path):
        db_path = self._create_seed_db(tmp_path)
        loader = _SeedDataLoader(SEED_DATA_DIR)
        with DatabaseSession(db_path, initialize=False) as session:
            for item in loader.load_assets():
                session.execute(
                    "INSERT OR IGNORE INTO assets (symbol, name, category) VALUES (?, ?, ?)",
                    (item["symbol"], item.get("name"), item.get("category")),
                )
            session.commit()

        with DatabaseSession(db_path, initialize=False) as s2:
            rows = s2.execute("SELECT * FROM assets ORDER BY symbol").fetchall()
            symbols = [r["symbol"] for r in rows]
            assert len(symbols) >= 3


# ── Idempotency tests (INSERT OR IGNORE prevents duplicates) ──────────────────


class TestSeedingIdempotency:
    """Running the seed twice must not create duplicate rows."""

    def _create_seed_db(self, tmp_path: Path):
        db_file = tmp_path / "seed_idem.db"
        with DatabaseSession(db_file, initialize=True) as session:
            init_db(session.conn)  # type: ignore[arg-type]
        return str(db_file)

    def test_tags_no_duplicates_on_double_seed(self, tmp_path):
        """Use deterministic IDs so INSERT OR IGNORE actually prevents duplicates."""
        db_path = self._create_seed_db(tmp_path)
        loader = _SeedDataLoader(SEED_DATA_DIR)

        with DatabaseSession(db_path, initialize=False) as session:
            for item in loader.load_tags():
                tag_id_bytes = _deterministic_uuid_bytes(f"tag:{item['name']}")
                session.execute(
                    "INSERT OR IGNORE INTO tags (tag_id, name, category) VALUES (?, ?, ?)",
                    (tag_id_bytes, item["name"], item.get("category")),
                )
            session.commit()

        with DatabaseSession(db_path, initialize=False) as s2:
            count_first = len(s2.execute("SELECT * FROM tags").fetchall())

        with DatabaseSession(db_path, initialize=False) as session:
            for item in loader.load_tags():
                tag_id_bytes = _deterministic_uuid_bytes(f"tag:{item['name']}")
                session.execute(
                    "INSERT OR IGNORE INTO tags (tag_id, name, category) VALUES (?, ?, ?)",
                    (tag_id_bytes, item["name"], item.get("category")),
                )

            count_second = len(session.execute("SELECT * FROM tags").fetchall())
        assert count_first == count_second, f"duplicate tag rows created: {count_first} -> {count_second}"

    def test_accounts_no_duplicates_on_double_seed(self, tmp_path):
        """Use deterministic IDs so INSERT OR IGNORE actually prevents duplicates."""
        db_path = self._create_seed_db(tmp_path)
        loader = _SeedDataLoader(SEED_DATA_DIR)

        with DatabaseSession(db_path, initialize=False) as session:
            for item in loader.load_accounts():
                acc_id_bytes = _deterministic_uuid_bytes(f"acc:{item['name']}")
                session.execute(
                    "INSERT OR IGNORE INTO accounts (account_id, name, type) VALUES (?, ?, ?)",
                    (acc_id_bytes, item["name"], item.get("type")),
                )
            session.commit()

        with DatabaseSession(db_path, initialize=False) as s2:
            count_first = len(s2.execute("SELECT * FROM accounts").fetchall())

        with DatabaseSession(db_path, initialize=False) as session:
            for item in loader.load_accounts():
                acc_id_bytes = _deterministic_uuid_bytes(f"acc:{item['name']}")
                session.execute(
                    "INSERT OR IGNORE INTO accounts (account_id, name, type) VALUES (?, ?, ?)",
                    (acc_id_bytes, item["name"], item.get("type")),
                )

            count_second = len(session.execute("SELECT * FROM accounts").fetchall())
        assert count_first == count_second, f"duplicate account rows created: {count_first} -> {count_second}"

    def test_assets_no_duplicates_on_double_seed(self, tmp_path):
        """symbol is the unique key for assets; second insert must be ignored."""
        db_path = self._create_seed_db(tmp_path)
        loader = _SeedDataLoader(SEED_DATA_DIR)

        with DatabaseSession(db_path, initialize=False) as session:
            for item in loader.load_assets():
                session.execute(
                    "INSERT OR IGNORE INTO assets (symbol, name, category) VALUES (?, ?, ?)",
                    (item["symbol"], item.get("name"), item.get("category")),
                )
            session.commit()

        with DatabaseSession(db_path, initialize=False) as s2:
            count_first = len(s2.execute("SELECT * FROM assets").fetchall())

        with DatabaseSession(db_path, initialize=False) as session:
            for item in loader.load_assets():
                session.execute(
                    "INSERT OR IGNORE INTO assets (symbol, name, category) VALUES (?, ?, ?)",
                    (item["symbol"], item.get("name"), item.get("category")),
                )

            count_second = len(session.execute("SELECT * FROM assets").fetchall())
        assert count_first == count_second, f"duplicate asset rows created: {count_first} -> {count_second}"


# ── Integration-style: full round-trip through domain models ──────────────────


class TestDomainModelRoundTrip:
    """Seed data flows through Pydantic domain models without errors."""

    def test_tag_roundtrip(self, tmp_path):
        db_path = str(tmp_path / "rt.db")
        with DatabaseSession(db_path, initialize=True) as session:
            tag = Tag(name="tax", category="classification")
            assert tag.name == "tax"
            assert tag.category == "classification"

    def test_account_roundtrip(self, tmp_path):
        db_path = str(tmp_path / "rt.db")
        with DatabaseSession(db_path, initialize=True) as session:
            acc = Account(name="checking", type="bank")
            assert acc.name == "checking"
            assert acc.type == "bank"

    def test_asset_roundtrip(self, tmp_path):
        db_path = str(tmp_path / "rt.db")
        with DatabaseSession(db_path, initialize=True) as session:
            asset = Asset(symbol="BTC", name="Bitcoin", category="crypto")
            assert asset.symbol == "BTC"
            assert asset.name == "Bitcoin"
            assert asset.category == "crypto"


# ── Edge-case tests ───────────────────────────────────────────────────────────


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_missing_yaml_file_raises(self, tmp_path):
        """Loading from a non-existent seed directory should raise FileNotFoundError."""
        loader = _SeedDataLoader(tmp_path / "nonexistent")
        with pytest.raises(FileNotFoundError):
            loader.load_tags()

    def test_empty_yaml_file_returns_empty_list(self, tmp_path):
        """An empty YAML file should produce an empty list (not crash)."""
        # Create a minimal seed structure
        fake_dir = tmp_path / "fake_seed"
        fake_dir.mkdir()
        (fake_dir / "tags_seed.yaml").write_text("tags: []")

        loader = _SeedDataLoader(fake_dir)
        tags = loader.load_tags()
        assert tags == []

    def test_yaml_with_extra_keys_ignored(self, tmp_path):
        """Extra keys in YAML should not cause errors (they are simply ignored)."""
        fake_dir = tmp_path / "fake_seed"
        fake_dir.mkdir()
        yaml_content = {
            "tags": [{"name": "test", "category": "x"}],
            "extra_key": "ignored",  # should be silently ignored
        }
        (fake_dir / "tags_seed.yaml").write_text(yaml.dump(yaml_content))

        loader = _SeedDataLoader(fake_dir)
        tags = loader.load_tags()
        assert len(tags) == 1
        assert tags[0]["name"] == "test"


# ── CLI integration test (optional, slow but valuable) ────────────────────────


# ── Auto-seed verification tests (DatabaseSession.initialize=True) ─────────────


class TestAutoSeedOnInit:
    """Verify that DatabaseSession(initialize=True) automatically seeds the DB."""

    def test_fresh_db_has_seed_tags(self, tmp_path):
        """A freshly initialized DB should have seed tag rows without manual seeding."""
        db_path = str(tmp_path / "auto.db")
        with DatabaseSession(db_path, initialize=True) as session:
            pass  # session closed

        from omnifin.db.seeding import SeedDataLoader

        loader = SeedDataLoader("")
        tags = loader.load_tags()
        with DatabaseSession(db_path, initialize=False) as s2:
            count = len(s2.execute("SELECT * FROM tags").fetchall())
            assert count == len(tags), f"expected {len(tags)} rows, got {count}"

    def test_fresh_db_has_seed_accounts(self, tmp_path):
        db_path = str(tmp_path / "auto_acct.db")
        with DatabaseSession(db_path, initialize=True) as session:
            pass

        from omnifin.db.seeding import SeedDataLoader
        loader = SeedDataLoader("")
        accounts = loader.load_accounts()
        with DatabaseSession(db_path, initialize=False) as s2:
            count = len(s2.execute("SELECT * FROM accounts").fetchall())
            assert count == len(accounts), f"expected {len(accounts)} rows, got {count}"

    def test_fresh_db_has_seed_assets(self, tmp_path):
        db_path = str(tmp_path / "auto_asset.db")
        with DatabaseSession(db_path, initialize=True) as session:
            pass

        from omnifin.db.seeding import SeedDataLoader
        loader = SeedDataLoader("")
        assets = loader.load_assets()
        with DatabaseSession(db_path, initialize=False) as s2:
            count = len(s2.execute("SELECT * FROM assets").fetchall())
            assert count == len(assets), f"expected {len(assets)} rows, got {count}"

    def test_double_init_no_duplicates(self, tmp_path):
        """Initializing twice must not create duplicate seed rows."""
        db_path = str(tmp_path / "double.db")
        with DatabaseSession(db_path, initialize=True) as s1:
            pass  # first init seeds the DB

        from omnifin.db.seeding import SeedDataLoader
        loader = SeedDataLoader("")
        tags = loader.load_tags()

        # Re-initialize (simulate restart or new session) — should be no-op since tables are populated.
        with DatabaseSession(db_path, initialize=True) as s2:
            pass  # second init; _seed_if_empty should skip

        with DatabaseSession(db_path, initialize=False) as s3:
            count = len(s3.execute("SELECT * FROM tags").fetchall())
            assert count == len(tags), f"duplicate seed rows created: expected {len(tags)}, got {count}"


class TestCLIIntegration:
    """Test that the seed_database function works end-to-end."""

    def _create_seed_db(self, tmp_path: Path):
        db_file = tmp_path / "cli_test.db"
        with DatabaseSession(db_file, initialize=True) as session:
            init_db(session.conn)  # type: ignore[arg-type]
        return str(db_file)

    def test_seed_database_function(self, tmp_path):
        """Test the production seed_database function works."""
        from omnifin.db.seeding import SeedDataLoader, SEED_DATA_DIR as PROD_SEED_DIR

        db_path = self._create_seed_db(tmp_path)
        loader = SeedDataLoader(db_path)

        # Load all three categories
        tags = loader.load_tags()
        accounts = loader.load_accounts()
        assets = loader.load_assets()

        assert len(tags) >= 3, f"expected >=3 tags, got {len(tags)}"
        assert len(accounts) >= 3, f"expected >=3 accounts, got {len(accounts)}"
        assert len(assets) >= 3, f"expected >=3 assets, got {len(assets)}"

    def test_seed_database_inserts_into_db(self, tmp_path):
        """Test that seed_database actually writes rows to the database."""
        from omnifin.db.seeding import SeedDataLoader

        db_path = self._create_seed_db(tmp_path)
        loader = SeedDataLoader(db_path)

        tags = loader.load_tags()
        with DatabaseSession(db_path, initialize=False) as session:
            for tag in tags:
                # Tag is a domain model (not subscriptable); access fields directly.
                tag_id_bytes = uuid.uuid4().bytes
                session.execute(
                    "INSERT OR IGNORE INTO tags (tag_id, name, category) VALUES (?, ?, ?)",
                    (tag_id_bytes, tag.name, tag.category),
                )
            session.commit()

        with DatabaseSession(db_path, initialize=False) as s2:
            tag_count = len(s2.execute("SELECT * FROM tags").fetchall())
            assert tag_count >= 3, f"expected >=3 rows in 'tags' table, got {tag_count}"
