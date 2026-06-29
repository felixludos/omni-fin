from __future__ import annotations

import os
import pytest
from click.testing import CliRunner

from omnifin.cli.main import cli
from omnifin.core.db import DatabaseSession
from omnifin.models import clear_global_identity_map

@pytest.fixture(autouse=True)
def clear_identity_maps():
    clear_global_identity_map()
    yield
    clear_global_identity_map()

@pytest.fixture
def runner():
    return CliRunner()

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_cli.db"
    return str(db_file)

@pytest.fixture
def sample_csv(tmp_path):
    csv_content = (
        "Trade Date,Symbol,Amount,Description\n"
        "2026-01-01,AAPL,100.00,Bought shares\n"
    )
    p = tmp_path / "sample.csv"
    p.write_text(csv_content, encoding="utf-8")
    return str(p)

def test_cli_init_db(runner, temp_db):
    result = runner.invoke(cli, ["init-db", "--db", temp_db])
    assert result.exit_code == 0
    assert f"Initialized {temp_db}" in result.output
    
    # Verify database file was created
    assert os.path.exists(temp_db)

def test_cli_normalize_basic(runner, sample_csv, temp_db):
    # Test normalization without saving
    result = runner.invoke(cli, ["normalize", sample_csv, "--db", temp_db])
    assert result.exit_code == 0
    assert "Plan valid: True" in result.output
    assert "Inserts:" in result.output

def test_cli_normalize_save(runner, sample_csv, temp_db):
    # Test normalization with saving to DB
    result = runner.invoke(cli, ["normalize", sample_csv, "--db", temp_db, "--save"])
    assert result.exit_code == 0
    assert "Saved report" in result.output
    
    # Verify persistence
    with DatabaseSession(temp_db) as session:
        count = session.execute("SELECT COUNT(*) AS c FROM reports").fetchone()["c"]
        assert count == 1

def test_cli_normalize_output_csv(runner, sample_csv, temp_db, tmp_path):
    output_csv = str(tmp_path / "output.csv")
    result = runner.invoke(cli, ["normalize", sample_csv, "--db", temp_db, "--output", output_csv])
    assert result.exit_code == 0
    assert f"Wrote normalized CSV to {output_csv}" in result.output
    assert os.path.exists(output_csv)

def test_cli_tax_us(runner, temp_db):
    # Since we have no transfers, it should just return an empty result/json
    result = runner.invoke(cli, ["tax", "--db", temp_db, "--jurisdiction", "US", "--year", "2026"])
    assert result.exit_code == 0
    # The tax command outputs JSON
    assert "{" in result.output
    assert "}" in result.output

def test_cli_tax_de(runner, temp_db):
    result = runner.invoke(cli, ["tax", "--db", temp_db, "--jurisdiction", "DE", "--year", "2026"])
    assert result.exit_code == 0
    assert "{" in result.output
    assert "}" in result.output

# test_cli_serve_command is removed because uvicorn.run is blocking
# and would hang the test suite. Server functionality is verified via test_api.py.
