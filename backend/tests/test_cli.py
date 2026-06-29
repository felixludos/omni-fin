from __future__ import annotations

import json
from pathlib import Path

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

    assert Path(temp_db).exists()

def test_cli_normalize_basic(runner, sample_csv, temp_db):
    result = runner.invoke(cli, ["normalize", sample_csv, "--db", temp_db])
    assert result.exit_code == 0
    assert "Plan valid: True" in result.output
    assert "Inserts:" in result.output

def test_cli_normalize_save(runner, sample_csv, temp_db):
    result = runner.invoke(cli, ["normalize", sample_csv, "--db", temp_db, "--save"])
    assert result.exit_code == 0
    assert "Saved report" in result.output

    with DatabaseSession(temp_db) as session:
        count = session.execute("SELECT COUNT(*) AS c FROM reports").fetchone()["c"]
        assert count == 1

def test_cli_normalize_output_csv(runner, sample_csv, temp_db, tmp_path):
    output_csv = str(tmp_path / "output.csv")
    result = runner.invoke(cli, ["normalize", sample_csv, "--db", temp_db, "--output", output_csv])
    assert result.exit_code == 0
    assert f"Wrote normalized CSV to {output_csv}" in result.output
    assert Path(output_csv).exists()


def test_cli_normalize_json_plan(runner, sample_csv, temp_db, tmp_path):
    output_csv = str(tmp_path / "normalized.csv")
    result = runner.invoke(
        cli,
        [
            "normalize",
            sample_csv,
            "--db",
            temp_db,
            "--output",
            output_csv,
            "--json-plan",
        ],
    )
    assert result.exit_code == 0
    json_start = result.output.find("{")
    assert json_start != -1
    plan = json.loads(result.output[json_start:])
    assert plan["is_valid"] is True
    assert plan["inserts"]["Transfer"] == 1

def test_cli_tax_us(runner, temp_db):
    result = runner.invoke(cli, ["tax", "--db", temp_db, "--jurisdiction", "US", "--year", "2026"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["jurisdiction"] == "US"
    assert payload["tax_year"] == 2026
    assert payload["warnings"]

def test_cli_tax_de(runner, temp_db):
    result = runner.invoke(cli, ["tax", "--db", temp_db, "--jurisdiction", "DE", "--year", "2026"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["jurisdiction"] == "DE"
    assert payload["tax_year"] == 2026
    assert payload["warnings"]

def test_cli_serve_command_invokes_uvicorn(runner, temp_db, monkeypatch):
    observed: dict[str, object] = {}

    def fake_run(app_path: str, host: str, port: int, reload: bool) -> None:
        observed["app_path"] = app_path
        observed["host"] = host
        observed["port"] = port
        observed["reload"] = reload

    monkeypatch.setattr("omnifin.cli.main.uvicorn.run", fake_run)

    result = runner.invoke(
        cli,
        [
            "serve",
            "--db",
            temp_db,
            "--host",
            "0.0.0.0",
            "--port",
            "8765",
            "--no-reload",
        ],
    )

    assert result.exit_code == 0
    assert observed["app_path"] == "omnifin.api.server:app"
    assert observed["host"] == "0.0.0.0"
    assert observed["port"] == 8765
    assert observed["reload"] is False
