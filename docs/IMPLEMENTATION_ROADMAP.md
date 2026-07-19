
# Omnifin Implementation Roadmap for Coding Agents

> **Last updated:** 2026-07-19 — Current state audit completed.

## Current State Summary

### What works today

| Feature | CLI Command | API Endpoints | Status |
|---------|-------------|---------------|--------|
| Database init | `fin init-db` | `POST /api/db/create` | Working (no seed from CLI) |
| CSV normalization | `fin normalize` | `POST /api/ingest/jobs` | Working, full pipeline |
| Tax calculation | `fin tax` | — | Scaffold only (zeroed output) |
| API server | `fin serve` | 42 endpoints | Working |
| Browse DB | — | `GET /api/browse/{model}` | Working |
| AI ingestion | — | `POST /api/ingest/jobs` | Working |
| Investment parsing | — | `POST /api/invest-parse/jobs` | Working |
| AI tuning | — | `POST /api/ingest/tuning/run` | Working |
| Frontend | — | — | 3 views, no router, no tests |

### What's scaffold-only (no real logic)

- `tax/us.py` — returns zeroed TaxResult with warning
- `tax/de.py` — returns zeroed TaxResult with warning
- `reconcile/balance.py` — single-statement check only, untested
- `ai/structured.py` — fully implemented but untested

### Test baseline

- 83 tests passing (`uv run pytest backend/tests -q --ignore=backend/tests/test_seeding.py`)
- 43 seeding tests fail (missing `cloud_data/seed_data/*.yaml` — gitignored local files)
- Coverage: domain model, CLI commands, API endpoints, normalization
- Not covered: tuning API, DB management endpoints, AI module, reconciliation

---

## Operating principles for every milestone

Every coding agent should work in small, verifiable increments. Each task should end with tests, a manual demo path, and a short implementation note.

The default workflow should be:

```bash
uv pip install -e backend
npm install
npm --prefix frontend install

uv run pytest backend/tests -q
npm run dev
```

For backend-only tasks:

```bash
uv run pytest backend/tests -q
uv run fin --help
```

For frontend/API tasks:

```bash
npm run dev
```

Then open:

```text
http://127.0.0.1:5173
```

Agents should not make large architectural rewrites unless a milestone explicitly asks for it. Each PR should include a “Verification” section explaining exactly what was run and what the user can click or execute to confirm the improvement.

---

# Milestone 0 — Stabilize the generated repo

## Goal

Make the seed repo easy to install, test, and run on Windows, Linux, and macOS.

## User-visible outcome

The user can clone/unzip the repo, install dependencies, run tests, start the backend/frontend, and see the starter dashboard.

## Tasks

### 0.1 Add setup documentation

**Agent prompt**

> Review the existing repo setup flow. Improve the README so a new developer on Windows can install Python dependencies, install Node dependencies, run backend tests, start the dev stack, and open the web UI. Include troubleshooting notes for missing `omnifin`, missing `concurrently`, and missing `vite`.

**Implementation notes**

Document:

```powershell
uv pip install -e backend
npm install
npm --prefix frontend install
uv run pytest backend/tests -q
npm run dev
```

Also document:

```powershell
uv run fin --help
fin init-db --db data/omnifin.db
fin serve --db data/omnifin.db --reload
```

**Automated checks**

```bash
pytest backend/tests -q
```

**Manual verification**

From a clean terminal:

```powershell
uv run fin --help
npm run dev
```

Expected:

Backend starts at `http://127.0.0.1:8000`, frontend starts at `http://127.0.0.1:5173`.

---

### 0.2 Add a root health-check script

**Agent prompt**

> Add a root-level script or Makefile target that verifies the development environment: Python package import, CLI availability, pytest run, frontend dependency presence, and package.json scripts. It should fail clearly with helpful messages.

**Suggested command**

```bash
npm run check
```

or:

```bash
make check
```

**Automated checks**

The check command should confirm:

```bash
python -c "import omnifin"
uv run fin --help
pytest backend/tests -q
npm --prefix frontend run build
```

**Manual verification**

Run:

```bash
npm run check
```

Expected: one clear success message.

---

# Milestone 1 — Database foundation and migrations

## Goal

Make the SQLite layer reliable and explicit: schema creation, strict constraints, UUID BLOB handling, seed data, and migrations.

## User-visible outcome

The user can initialize a database, inspect tables, and trust that IDs, foreign keys, and core constraints behave correctly.

---

### 1.1 Finalize schema.sql

**Agent prompt**

> Review `backend/omnifin/db/schema.sql` against the current Omnifin object model. Ensure SQLite STRICT mode is used, foreign keys are enabled, UUID primary keys are BLOB where appropriate, assets use `symbol` as the primary key, reports record import/edit sessions, and junction tables exist for tags, comments, entities, locations, events, and transfer matches. Fix naming inconsistencies and add useful indexes.

**Implementation notes**

Add indexes for frequent queries:

```sql
CREATE INDEX IF NOT EXISTS idx_transfers_date ON transfers(date);
CREATE INDEX IF NOT EXISTS idx_transfers_sender ON transfers(sender_account_id);
CREATE INDEX IF NOT EXISTS idx_transfers_receiver ON transfers(receiver_account_id);
CREATE INDEX IF NOT EXISTS idx_transfers_asset ON transfers(asset_symbol);
CREATE INDEX IF NOT EXISTS idx_statements_account_date ON statements(account_id, date);
CREATE INDEX IF NOT EXISTS idx_tags_name ON tags(name);
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type);
```

**Automated checks**

Add tests that:

1. Create an in-memory database.
2. Apply schema.
3. Confirm all expected tables exist.
4. Confirm foreign keys are enabled.
5. Confirm invalid foreign keys fail.

**Manual verification**

```bash
fin init-db --db data/omnifin.db
```

Then inspect:

```bash
sqlite3 data/omnifin.db ".tables"
```

---

### 1.2 Add lightweight migration support

**Agent prompt**

> Add a simple migration system for SQLite. It does not need Alembic yet. Use a `schema_migrations` table and numbered SQL files under `backend/omnifin/db/migrations`. Add `fin migrate --db ...`.

**Implementation notes**

Suggested structure:

```text
backend/omnifin/db/
├── schema.sql
└── migrations/
    ├── 0001_initial.sql
    └── 0002_indexes.sql
```

CLI:

```bash
fin migrate --db data/omnifin.db
fin migrate --db data/omnifin.db --dry-run
```

**Automated checks**

Test that:

1. Fresh DB applies all migrations.
2. Running migration twice is idempotent.
3. Migration table records applied versions.

**Manual verification**

```bash
fin migrate --db data/test.db --dry-run
fin migrate --db data/test.db
fin migrate --db data/test.db
```

Second real run should say no pending migrations.

---

# Milestone: Clean-up interface

```
Clean up the main frontend interface somewhat, so that the top starts by printing the path to the database that is currently being used, with an option to browse to a different file, or to create a new one, with a "load/create" button.
```

Does this direction look right? A few things I want to confirm before implementing:
1. For "browse" — should I scan cloud_data/ for .db files and present them in a dropdown, or would you prefer a different mechanism?
2. For "create new" — should the user type a filename (like my_finance.db) that gets created in the default cloud_data/ directory, or should they enter a full path?
3. Do you want the existing ingestion UI to stay below the DB header, or should it only appear after a DB is successfully loaded?

```
1. As a "quick" convenience, scanning cloud_data/ (by default, or a directory specified by a corresponding environment variable) for .db files and presenting them in a dropdown is fine.
2. For "create new", the user should be able to type a filename (like my_finance.db), even without the extension (default extension is `.db`).
3. Show the existing ingestion UI below the DB header, but disable it until a DB is successfully loaded. You should also automatically load the previously used DB if it exists, and show a message like "Loaded previous database: <filename>". So the user can directly start using the app without having to select a DB every time.
```

## Browse Database

```
Below the loading database panel and above the injestion panel, there should be a "Browse Database" panel, which shows the contents of the database in nicely formatted tables including a tab for each of the main objects. There should be a toggle to switch between the "low-level" data view (showing the data with minimal inferences and transformations) and the "high-level" domain view (showing the data as it would be represented in the Python domain model). The user should be able to click on any object to see its details, including related objects, tags, comments, and events. There should also be a search bar to filter objects by name, symbol, or other relevant fields.
```

```
When creating a database and seeding it with the cloud_data/seed_data/* make sure that both assets and investments are processed correctly such that tags and comments of appropriate types/categories are created and linked to the correct objects to ensure that the seeded data is fully functional and can be used for testing and demonstration purposes. Obviously these more specialized fields that are attached by comments/tags should only be included if the data is values are not null.

Note that for investments the datatypes should be:
- built-in to `assets` table: symbol, name, category
- nyse_ticker: comment with type="nyse_ticker"
- ibkr_ticker: comment with type="ibkr_ticker"
- identifier: comment with type="asset_identifier"
- identifier_type: tag with type="asset_identifier_type" (with values like "cusip", "isin", etc.)
- country: tag with type="country" (with values like "US", "DE", etc.)
- fund_type: tag with type="fund_type" (with values like "etf", "mutual_fund", "index_fund", "real_estate_fund", "other_fund")
- fund_focus: tag with type="fund_focus" (with values like "equity_heavy", "mixed", "other_fund", "german_real_estate_fund", "real_estate_fund")
```

---

# Milestone 2 — Domain model identity, lazy loading, and staged edits

## Goal

Make the high-level Python domain layer feel natural while keeping SQLite as the source of truth.

## User-visible outcome

Developers can write:

```python
usd = Asset("USD")
statement = Statement(account=my_account, unit="USD", balance=100)
statement.add_tags("reviewed", "tax_2026")

plan = report.plan(statement)
report.save(statement)
```

and Omnifin discovers dependencies, stages changes, plans them, and saves atomically.

---

```
The AI processing in the injest step needs more attention. Specifically, I want to make sure that (1) the prompt template is written well, that (2) useful context is loaded to help the AI connect objects that are interpreted correctly, and (3) that the schemas are clear and unambiguous so that the objects can be parsed correctly. 

Start by building a new "AI tuning page with a link from the homepage where on the left there are several panels to specify an input JSON object (which would be the equivalent of a row of a uploaded CSV file) as input, below that a panel connected to the database where additional context from the database can be selected to be mentioned in the prompt, and then below that the schema of all the high-level pydantic objects can be viewed and optionally selected for the prompt. Then in the middle there should be a panel with an editable (markdown) text box on top to specify the prompt template including placeholders for the various input, context, and schemas to include, and a button to fill in all the placeholders to produce the corresponding prompt that is fed in to the AI (the prompt should be viewable in other tab on that panel). On the right column there is a panel on top to set some AI call hyperparameters as a json object, including whether structured output generation should be used and for what schema. Finally there needs to be a button to run the AI call, and then see all the output (including thoughts) in the bottom right panel - with notes on whether the responses adhere to schemas of objects so that the products can be saved to the database correctly.

One note on the UI: generally I would prefer structured input UIs with suitable widgets, but everywhere it should also be possible to switch to "JSON" mode which is just a textbox to set the values (such as inputs, or context, or AI call hyperparameters) to enable finer control of what is inputed at each step

The structured output generation in the AI tuning page of the  seems to be failing so it might not be implemented correctly or the hyperparameters need to be set differently. Here's the current error: Structured output failed: Could not parse response content as the length limit was reached - CompletionUsage(completion_tokens=10000, prompt_tokens=5603, total_tokens=15603, completion_tokens_details=None, prompt_tokens_details=None)
```

example inputs

```json
{
  "Symbol(CUSIP)": "COST(22160K105)",
  "Security description": "COSTCO WHOLESALE CORP COM",
  "Date acquired": "2025-02-20",
  "Date sold": "2025-02-27",
  "Quantity": "0.026",
  "Cost basis": "$27.49",
  "Proceeds": "$26.93",
  "Short-term gain/loss": " -$0.56",
  "Long-term gain/loss": " --",
  "None": "['']"
}
```

```json
{
  "Symbol(CUSIP)": "FZROX(31635T708)",
  "Security description": "FIDELITY ZERO TOTAL MARKET INDEX",
  "Date acquired": "Various",
  "Date sold": "2025-02-03",
  "Quantity": "240.154",
  "Cost basis": "$4,096.98",
  "Proceeds": "$5,000.00",
  "Short-term gain/loss": " --",
  "Long-term gain/loss": "$903.02",
  "None": "['']"
}
```

```json
{
  "Symbol(CUSIP)": "SPY(78462F103)",
  "Security description": "STATE STREET SPDR S&P 500 ETF UNITS",
  "Date acquired": "2024-11-18",
  "Date sold": "2025-01-15",
  "Quantity": "17",
  "Cost basis": "$9,999.23",
  "Proceeds": "$10,078.91",
  "Short-term gain/loss": "$79.68",
  "Long-term gain/loss": " --",
  "None": "['']"
}
```

### Extract investments service

```
Design and implement a new service for parsing investment assets,which should become a new panel like the ingestion and the AI tuning services. This should be a multi-step process where first a CSV file is uploaded, then (with a panel for some basic AI hyperparameters) the AI is called on each row to extract what investment was involved in a series of prompts, and then the results are displayed in a table with the ability to edit each row and then save the results to the database. The prompting protocol should be as follows:
Given the input row (displayed as a JSON object), and a basic list of all existing assets in the database (using only their symbols), the prompt should ask whether "the investment involved in this transaction is already known or if it is a new investment that needs to be added to the database". If it is already known, the AI should return the symbol of the existing asset. If it is a new investment, the AI should return a JSON object with all the fields needed to create a new investment asset in the database, including the symbol, name, category, nyse_ticker, ibkr_ticker, identifier, identifier_type, country, fund_type, and fund_focus. Make sure to provide context on how these fields are used in the database and what values are expected for each field (including examples)
Other than that the rows should be processed similarly to the existing ingestion service, with the ability to edit the AI output and save it to the database. The user should also be able to download the results as a CSV file for further analysis or record-keeping.
```

```
Currently, since each row is being processed independently, if the same new stock gets sold repeatedly, then the AI has to repeatedly parse the same information - which is very inefficient. To improve this, add a "pre-processing" step using the AI where the column names of the uploaded CSV file are analyzed to identify which columns can likely be used to uniquely identify the investment involved in each row. The rows that are merged should be visible to the user, and most importantly when the AI is called on one group, the results should be shown for all the rows in that group, so that the user can see all the rows that were merged and the AI output for each of them. This should be done in a way that is transparent to the user, so that they can see which rows were merged and what the AI output was for each of them. 
```

```
Add an option for the LLM processing to say "no new investment" for example for a row that is a dividend or interest payment, also add an option that is "attached to previous" for oddly formatted CSV rows where a subsequent row should actually be attached to the previous row (for example, a wash sale row that is attached to a previous sale row). These rows should be merged in a transparent way so that the user knows which rows were merged and what the AI output was for each of them. The user should also be able to edit the AI output for each row, and the changes should be reflected in the merged rows as well.
```

---

### 2.1 Implement identity map correctly

**Agent prompt**

> Implement or harden the identity map so objects with the same primary key are singletons within a `DatabaseSession`. Avoid a global singleton that crosses database sessions. Ensure `Asset("USD") is Asset("USD")` within one session, but separate test sessions do not contaminate each other.

**Implementation notes**

Prefer session-scoped cache:

```python
session.identity_map[(Asset, "USD")]
session.identity_map[(Account, account_uuid)]
```

Avoid process-global cache unless clearly scoped and resettable.

**Automated checks**

Test:

```python
usd1 = session.get_or_create_asset("USD")
usd2 = session.get_or_create_asset("USD")
assert usd1 is usd2
```

Also test isolation:

```python
session_a.Asset("USD") is not session_b.Asset("USD")
```

**Manual verification**

Add a debug command:

```bash
fin debug-identity --db data/omnifin.db
```

Expected: prints that repeated loads return the same Python object within a session.

---

### 2.2 Implement scalar coercion and nested dependency discovery

**Agent prompt**

> Make constructors and validators infer object types from context. `Asset("USD")` should become an asset with symbol `USD`; `Tag("tax_2026")` should become a tag with name `tax_2026`; `Statement(unit="USD", account=Account(...))` should coerce unit into `Asset("USD")`. `Report.save(statement)` should discover and save `statement.unit` and `statement.account` first.

**Automated checks**

Test:

```python
statement = Statement(account=account, unit="USD", balance=100, date=...)
assert isinstance(statement.unit, Asset)
assert statement.unit.symbol == "USD"
```

Test save graph:

```python
report.save(statement)
```

Then query DB and verify asset, account, and statement rows exist.

**Manual verification**

Create a small script:

```bash
fin demo-domain --db data/demo.db
```

Expected output:

```text
Created Asset USD
Created Account Demo Checking
Created Statement 100 USD
Plan: 3 inserts, 0 updates
Save complete
```

---

### 2.3 Implement staged tags, comments, entities, events, and locations

**Agent prompt**

> Ensure relationship mutations are staged locally, not written immediately. `add_tags`, `comment`, `add_entities`, `add_involved`, and location assignment should update local object state. These changes should appear when reading the object’s properties, but should not touch SQLite until `report.save(...)`.

**Automated checks**

Test:

1. Load or create transfer.
2. Call `transfer.add_tags("needs_review")`.
3. Confirm DB does not yet contain junction row.
4. Confirm `transfer.tags()` includes the staged tag.
5. Run `report.save(transfer)`.
6. Confirm DB now contains tag and junction row.

Repeat for comments, events, and entity-account links.

**Manual verification**

```bash
fin demo-staged-edits --db data/demo.db
```

Expected:

```text
Before save: tag visible locally, absent from database
After save: tag visible locally, present in database
```

---

### 2.4 Implement `Report.plan()`

**Agent prompt**

> Implement `Report.plan(*objects)` as a dry-run Unit of Work. It should traverse the object graph, include staged relationship changes, detect inserts, updates, unchanged records, missing required fields, missing dependencies, and destructive operations. Return a Pydantic `PlanSummary`.

**Suggested `PlanSummary` fields**

```python
class PlanSummary(BaseModel):
    is_valid: bool
    inserts: dict[str, int]
    updates: dict[str, int]
    unchanged: dict[str, int]
    relation_adds: dict[str, int]
    relation_removes: dict[str, int]
    missing_required: list[str]
    missing_dependencies: list[str]
    warnings: list[str]
```

**Automated checks**

Test:

```python
plan = report.plan(statement)
assert plan.is_valid
assert plan.inserts["Asset"] == 1
assert plan.inserts["Statement"] == 1
```

Test invalid object:

```python
bad_statement = Statement(account=account, unit=None, balance=100)
plan = report.plan(bad_statement)
assert not plan.is_valid
```

**Manual verification**

```bash
fin plan-demo --db data/demo.db
```

Expected: readable plan printed as JSON and human summary.

---

### 2.5 Implement `Report.save()`

**Agent prompt**

> Implement `Report.save(*objects)` so it runs `plan()` first, refuses invalid plans, saves all graph dependencies in dependency order, flushes staged relationship changes, and commits everything inside one SQLite transaction. If any insert/update fails, rollback completely.

**Automated checks**

Test rollback:

1. Create valid account.
2. Create invalid transfer referencing missing required field.
3. Run save.
4. Assert no partial rows were inserted.

Test dependency order:

```python
report.save(statement)
```

where statement depends on account and asset not yet in DB.

**Manual verification**

```bash
fin demo-save --db data/demo.db
```

Expected:

```text
Plan valid
Saving 3 objects and 2 relation changes
Committed
```

---

# Milestone 3 — Generic CSV normalization

## Goal

Implement the first major user-facing feature: given any CSV, produce normalized Omnifin objects and a save plan.

## User-visible outcome

The user can run:

```bash
fin normalize path\to\file.csv --db data/omnifin.db --preview
```

and see how rows were interpreted before committing.

---

### 3.1 Add raw CSV loader and source fingerprinting

**Agent prompt**

> Implement robust CSV loading for arbitrary broker exports. Preserve original rows, compute stable row hashes, compute file hash, and create a `Report` object representing the import session. Do not save anything by default.

**Implementation notes**

Use hashes for idempotency:

```text
report.raw_hash = hash(file bytes)
transfer.raw_hash = hash(canonical row JSON)
```

**Automated checks**

Test:

1. Same row produces same hash.
2. Column order differences do not change canonical row hash.
3. Different value changes hash.

**Manual verification**

```bash
fin inspect-csv tests/fixtures/simple_bank.csv
```

Expected:

```text
Rows: 10
Columns: Date, Description, Amount, Currency
File hash: ...
```

---

### 3.2 Define normalized transfer draft schema

**Agent prompt**

> Create a normalization output model that is not yet the final database object. It should capture parsed date, sender/receiver hints, asset symbol, amount, description, confidence, parser name, warnings, and raw row hash. This draft can then be converted into high-level domain objects.

**Suggested model**

```python
class TransferDraft(BaseModel):
    date: datetime | None
    sender: Account | str | None
    receiver: Account | str | None
    unit: Asset | str | None
    amount: Decimal | None
    description: str | None
    raw_hash: bytes
    parser: str
    confidence: float
    warnings: list[str]
```

**Automated checks**

Test that a simple CSV row becomes a `TransferDraft`.

**Manual verification**

```bash
fin normalize tests/fixtures/simple_bank.csv --preview --json
```

Expected: JSON list of drafts.

---

### 3.3 Implement deterministic generic parser

**Agent prompt**

> Implement a generic parser that recognizes common CSV columns such as date, amount, currency, description, debit, credit, symbol, quantity, price, and account. It should produce transfer drafts and warnings rather than failing on unfamiliar columns.

**Automated checks**

Fixtures:

```text
simple_bank.csv
simple_broker_dividend.csv
simple_trade.csv
```

Each should produce expected drafts.

**Manual verification**

```bash
fin normalize tests/fixtures/simple_bank.csv --preview
```

Expected table:

```text
date        amount   unit  sender        receiver      confidence  warnings
2026-01-02  100.00   USD   external      checking      0.82        ...
```

---

### 3.4 Add save flow for normalized CSV

**Agent prompt**

> Wire generic normalization into `Report.plan()` and `Report.save()`. `fin normalize --preview` should only print a plan. `fin normalize --save` should commit. Default should be preview, not save.

**CLI behavior**

```bash
fin normalize file.csv --db data/omnifin.db
fin normalize file.csv --db data/omnifin.db --save
fin normalize file.csv --db data/omnifin.db --output normalized.csv
```

**Automated checks**

Test preview does not mutate DB.

Test save inserts report and transfers.

Test repeated save detects duplicates by raw hash or stable import key.

**Manual verification**

```bash
fin normalize tests/fixtures/simple_bank.csv --db data/demo.db
fin normalize tests/fixtures/simple_bank.csv --db data/demo.db --save
```

Expected: first command previews; second commits.

---

# Milestone 4 — Broker-specific ingestion

## Goal

Add reliable parsers for the real target inputs: Fidelity Activity CSV, Fidelity Closed Positions CSV, and IBKR Flex CSV.

## User-visible outcome

The user can import real downloaded files and review normalized transfers/trades/dividends/fees.

---

### 4.1 Fidelity Activity parser

**Agent prompt**

> Implement a Fidelity Activity CSV parser. It should detect dividends, interest, deposits, withdrawals, fees, reinvestments, buys, sells, and journal movements. Preserve raw rows. Convert each row into one or more Omnifin transfers/events as appropriate. Add fixtures with anonymized examples.

**Automated checks**

Create fixtures for:

1. Cash dividend.
2. Reinvested dividend.
3. Buy.
4. Sell.
5. Fee.
6. Transfer in/out.
7. Interest.
8. Unknown activity type.

Each test should verify drafts and warnings.

**Manual verification**

```bash
fin normalize data/fidelity_activity.csv --broker fidelity-activity --preview
```

Expected: categorized row table with confidence and warnings.

---

### 4.2 Fidelity Closed Positions parser

**Agent prompt**

> Implement Fidelity Closed Positions parser for realized gains/losses. This should normalize closing trades and preserve lot-level information needed for US tax calculations. Do not compute taxes yet; just capture the normalized data and links to assets/accounts/events.

**Automated checks**

Fixtures:

1. Short-term gain.
2. Long-term gain.
3. Partial lot sale.
4. Wash sale field if available.
5. Missing cost basis.

**Manual verification**

```bash
fin normalize data/fidelity_closed_positions.csv --broker fidelity-closed --preview
```

Expected: lot-level normalized rows.

---

### 4.3 IBKR Flex CSV parser

**Agent prompt**

> Implement IBKR Flex CSV parser. Detect sections or statement types if present. Normalize trades, dividends, withholding tax, interest, deposits, withdrawals, fees, FX conversions, and corporate actions. Use deterministic parsing first; unresolved rows should be marked for review.

**Automated checks**

Fixtures:

1. Stock buy.
2. Stock sell.
3. FX conversion.
4. Dividend.
5. Withholding tax.
6. Activity fee.
7. Deposit/withdrawal.
8. Corporate action placeholder.

**Manual verification**

```bash
fin normalize data/ibkr_flex.csv --broker ibkr-flex --preview
```

Expected: all recognized rows classified; unknown rows retained as warnings.

---

### 4.4 Import review workflow

**Agent prompt**

> Add a review output mode that writes normalized results to CSV and JSONL. Include raw row hash, parser, confidence, warnings, inferred accounts, inferred assets, and proposed transfers/events. Make it easy for the user to inspect and manually correct before saving.

**CLI**

```bash
fin normalize file.csv --preview --output out/normalized.csv
fin normalize file.csv --preview --output-jsonl out/normalized.jsonl
```

**Automated checks**

Test output files are created and contain all raw hashes.

**Manual verification**

Open `out/normalized.csv` in a spreadsheet and verify row-by-row interpretation.

---

# Milestone 5 — Asset registry and local LLM assistance

## Goal

Make unknown asset classification modular, reviewable, and safe.

## User-visible outcome

Unknown assets are detected, classified with local Ollama if enabled, saved only after review, and reused in future imports.

---

### 5.1 JSONL asset registry

**Agent prompt**

> Implement `assets.jsonl` loading and writing. It should contain known assets with symbol, long name, category, ISIN, CUSIP, exchange, currency, tax metadata, and aliases. The database remains source of truth for saved assets, but JSONL acts as a portable bootstrap registry.

**Automated checks**

Test:

1. Load JSONL.
2. Resolve alias to asset.
3. Append new asset without duplicating existing symbol.
4. Invalid JSONL line produces clear error.

**Manual verification**

```bash
fin assets lookup USD
fin assets lookup AAPL
```

---

### 5.2 Structured local LLM wrapper

**Agent prompt**

> Implement a generic local LLM structured-output helper. It should accept a prompt, Pydantic response model, model name, timeout, temperature, and max tokens. It should use the OpenAI API client pointed at Ollama-compatible local endpoint. It must be isolated from parser logic and easy to mock in tests.

**Suggested API**

```python
extract_structured(
    prompt: str,
    response_model: type[T],
    model: str = "llama3.1",
    base_url: str = "http://127.0.0.1:11434/v1",
    timeout: int = 60,
) -> T
```

**Automated checks**

Use mocks. Do not require Ollama in CI.

Test:

1. Valid structured response.
2. Invalid response retries or fails clearly.
3. Timeout handled cleanly.

**Manual verification**

With Ollama running:

```bash
fin ai-test "Classify AAPL"
```

Expected: structured asset classification.

---

### 5.3 Unknown asset workflow

**Agent prompt**

> Integrate asset resolution into normalization. Deterministic lookup should happen first using DB and JSONL aliases. If unresolved and `--use-ai` is passed, ask local LLM to classify. If still unresolved, create a review warning and do not silently invent tax metadata.

**CLI**

```bash
fin normalize file.csv --use-ai --preview
fin normalize file.csv --no-ai --preview
```

**Automated checks**

Mock LLM and test unknown symbol resolution.

Test no-AI path produces warning.

**Manual verification**

Run with a fixture containing an unknown symbol:

```bash
fin normalize tests/fixtures/unknown_asset.csv --preview --use-ai
```

Expected: proposed asset with confidence and warning requiring review.

---

# Milestone 6 — Reconciliation engine

## Goal

Verify that transfers between statements explain account balances.

## User-visible outcome

The user can import statements and ask Omnifin whether the ledger reconciles.

---

### 6.1 Statement import

**Agent prompt**

> Add CLI support for importing account statements manually from CSV or via simple command arguments. A statement records account, asset, date, and balance. It should support multiple assets per account.

**CLI**

```bash
fin statement add --account "Fidelity Taxable" --asset USD --balance 1000 --date 2026-01-31
fin statement import statements.csv --db data/omnifin.db --preview
```

**Automated checks**

Test statement creation and graph save of account/asset dependencies.

**Manual verification**

```bash
fin statement list --db data/omnifin.db
```

---

### 6.2 Reconcile between two statements

**Agent prompt**

> Implement reconciliation for one account and one asset between two statement dates. Starting balance plus net transfers should equal ending balance. Output difference, included transfers, missing date ranges, and suspicious rows.

**CLI**

```bash
fin reconcile --account "Fidelity Taxable" --asset USD --from 2026-01-01 --to 2026-01-31
```

**Automated checks**

Fixtures:

1. Perfect reconciliation.
2. Missing transfer.
3. Duplicate transfer.
4. Wrong sign.
5. Multi-asset account.

**Manual verification**

Expected output:

```text
Starting balance: 100.00 USD
Net transfers:    25.00 USD
Expected ending:  125.00 USD
Actual ending:    125.00 USD
Status: OK
```

---

### 6.3 Transfer matching

**Agent prompt**

> Implement transfer matching between internal accounts. Match equal asset/amount transfers within a configurable date window. Store match rows only when accepted. Provide preview and save modes.

**CLI**

```bash
fin match-transfers --asset USD --days 5 --preview
fin match-transfers --asset USD --days 5 --save
```

**Automated checks**

Test:

1. Exact match found.
2. Multiple candidate ambiguity.
3. Amount mismatch tolerance.
4. Different asset no match.
5. Existing match not duplicated.

**Manual verification**

Run on demo data and confirm matched pairs are displayed before saving.

---

# Milestone 7 — Tax calculation foundation

## Goal

Build the shared tax engine primitives before implementing jurisdiction-specific rules.

## User-visible outcome

The user can produce a draft taxable-event report for a year, with lots and warnings, even before full tax-form output exists.

---

### 7.1 Taxable event classification

**Agent prompt**

> Implement classification of transfers/events into taxable and non-taxable categories. Do not yet compute final tax. Produce a reviewable list of candidate taxable events with reason codes.

**CLI**

```bash
fin tax events --year 2026 --jurisdiction US
fin tax events --year 2026 --jurisdiction DE
```

**Automated checks**

Fixtures for:

1. Buy.
2. Sell.
3. Dividend.
4. Interest.
5. Internal transfer.
6. Fee.
7. FX conversion.

**Manual verification**

Expected table:

```text
date        type      asset  amount  taxable  reason
2026-02-01  dividend  USD    12.34   yes      dividend_income
```

---

### 7.2 Lot model

**Agent prompt**

> Add tax lot models for acquisitions and disposals. Implement FIFO lot selection as a reusable engine. Do not hardcode US or German rules into the lot engine.

**Automated checks**

Test:

1. Single buy/sell.
2. Partial lot.
3. Multi-lot FIFO.
4. Sell more than held fails.
5. Fees included in basis if configured.

**Manual verification**

```bash
fin tax lots --asset AAPL --year 2026 --method FIFO
```

---

### 7.3 Shared gain/loss calculation

**Agent prompt**

> Implement generic realized gain/loss calculation using disposal proceeds, allocated cost basis, fees, dates, holding period, and currency. Output draft gain/loss records with all inputs visible.

**Automated checks**

Fixtures with known expected gains.

**Manual verification**

```bash
fin tax gains --year 2026 --jurisdiction US --preview
```

Expected: CSV/JSON report with calculation detail.

---

# Milestone 8 — US tax module

## Goal

Implement useful US tax calculations for brokerage activity.

## User-visible outcome

The user can generate a draft US capital gains/dividends/interest report from imported Fidelity/IBKR data.

---

### 8.1 US capital gains

**Agent prompt**

> Implement US capital gains classification using FIFO by default, with short-term vs long-term holding period. Include proceeds, cost basis, gain/loss, acquisition date, disposal date, and source rows.

**Automated checks**

Test short-term and long-term examples.

**Manual verification**

```bash
fin tax us capital-gains --year 2026 --output out/us_gains.csv
```

---

### 8.2 US dividends and interest

**Agent prompt**

> Implement US dividend and interest summary. Preserve qualified/non-qualified status if available from source. If unavailable, mark as unknown rather than guessing.

**Automated checks**

Test ordinary dividend, qualified dividend, interest, withholding.

**Manual verification**

```bash
fin tax us income --year 2026
```

---

### 8.3 Wash sale detection placeholder

**Agent prompt**

> Implement a conservative wash sale detector that flags possible wash sales across accounts within the relevant date window. Initially mark these as warnings requiring review instead of automatically adjusting basis unless confidence is high.

**Automated checks**

Test same-symbol buy/sell within window.

**Manual verification**

```bash
fin tax us wash-sales --year 2026
```

Expected: warning list.

---

# Milestone 9 — German tax module

## Goal

Implement useful German tax calculations while preserving reviewability.

## User-visible outcome

The user can generate a draft German capital income report with warnings for missing ISIN, fund type, Teilfreistellung, or FX rates.

---

### 9.1 German FIFO gains

**Agent prompt**

> Implement German FIFO capital gains calculation for securities. Require acquisition date, disposal date, proceeds, cost basis, fees, and currency conversion source. Missing ISIN or FX rate should produce warnings.

**Automated checks**

Test simple FIFO gain/loss.

**Manual verification**

```bash
fin tax de capital-gains --year 2026 --output out/de_gains.csv
```

---

### 9.2 German fund metadata and Teilfreistellung

**Agent prompt**

> Extend asset metadata for German fund taxation: fund type, equity ratio, Teilfreistellung category, accumulating/distributing status, ISIN, and country. Do not infer legally sensitive values without marking confidence and source.

**Automated checks**

Test metadata validation.

**Manual verification**

```bash
fin assets missing-tax-metadata --jurisdiction DE
```

Expected: list of assets needing review.

---

### 9.3 Vorabpauschale scaffold

**Agent prompt**

> Add a Vorabpauschale calculation scaffold. It should identify accumulating funds and required inputs, but may initially output “not enough data” warnings unless all required values are present.

**Automated checks**

Test that accumulating ETF with missing base interest rate emits warning.

**Manual verification**

```bash
fin tax de vorabpauschale --year 2026
```

---

# Milestone 10 — FastAPI backend

## Goal

Expose the database and workflows through stable API endpoints.

## User-visible outcome

The frontend can list accounts, assets, transfers, statements, reports, plans, and import previews.

---

### 10.1 API read endpoints

**Agent prompt**

> Implement FastAPI endpoints for listing and retrieving assets, accounts, transfers, statements, reports, tags, comments, events, and entities. Use Pydantic response models. Add pagination and basic filters for transfers.

**Endpoints**

```text
GET /api/health
GET /api/assets
GET /api/accounts
GET /api/transfers?account=&asset=&from=&to=
GET /api/statements
GET /api/reports
```

**Automated checks**

Use FastAPI TestClient.

Test health endpoint and list endpoints on seeded DB.

**Manual verification**

Open:

```text
http://127.0.0.1:8000/docs
```

---

### 10.2 API planning and save endpoints

**Agent prompt**

> Add API endpoints for import preview, plan, and save. Save endpoints should require explicit confirmation and return the same `PlanSummary` shape as CLI.

**Endpoints**

```text
POST /api/import/preview
POST /api/import/save
POST /api/report/plan
POST /api/report/save
```

**Automated checks**

Test preview does not mutate DB.

Test save mutates DB only after confirmation.

**Manual verification**

Use Swagger UI at `/docs`.

---

# Milestone 11 — Frontend MVP

## Goal

Make the web UI useful for inspection and review.

## User-visible outcome

The user can browse data, inspect imports, filter transfers, and see save plans.

---

### 11.1 Dashboard shell

**Agent prompt**

> Build a Vite dashboard shell with navigation for Dashboard, Imports, Transfers, Accounts, Assets, Statements, Reports, and Tax. Keep design simple and data-dense.

**Automated checks**

```bash
npm --prefix frontend run build
```

**Manual verification**

Open `http://127.0.0.1:5173`.

---

### 11.2 Transfers table

**Agent prompt**

> Implement a transfers table with filtering by date range, account, asset, tag, and report. Include raw hash, source report, sender, receiver, amount, asset, and warnings if available.

**Automated checks**

Frontend build passes.

Backend endpoint test passes.

**Manual verification**

Import demo data, open Transfers page, filter by asset.

---

### 11.3 Import review page

**Agent prompt**

> Build an Import Review page. User can choose a CSV file, preview normalized rows, see confidence/warnings, inspect proposed plan, and then save.

**Automated checks**

Mock API responses in frontend unit tests if test framework exists; otherwise ensure build passes.

**Manual verification**

Use a fixture CSV and verify preview-before-save workflow.

---

### 11.4 Object detail pages

**Agent prompt**

> Add detail views for Account, Asset, Transfer, Statement, and Report. Show tags, comments, related events, related transfers, source report, and raw data hash. Allow adding tags/comments locally through API save flow.

**Manual verification**

Open a transfer detail page, add a tag/comment, confirm it appears after save and persists on refresh.

---

# Milestone 12 — Data quality, auditing, and safety

## Goal

Make it hard to accidentally corrupt financial records.

## User-visible outcome

The user can see what changed, undo bad imports safely, and audit suspicious records.

---

### 12.1 Import idempotency

**Agent prompt**

> Prevent duplicate imports. If a report with the same raw file hash already exists, warn the user and require explicit `--allow-duplicate` to proceed.

**Automated checks**

Import same fixture twice and assert second import is blocked.

**Manual verification**

```bash
fin normalize file.csv --save
fin normalize file.csv --save
```

Expected: second command warns.

---

### 12.2 Audit log

**Agent prompt**

> Add an audit log table for create/update/delete/save operations. Record timestamp, actor, report, object type, object id, action, and before/after JSON where practical.

**Automated checks**

Test save creates audit rows.

**Manual verification**

```bash
fin audit list --limit 20
```

---

### 12.3 Undo report

**Agent prompt**

> Implement `fin report undo REPORT_ID`. Because core records may be shared across reports, do not blindly delete global assets/accounts. Delete or reverse only records safely attributable to the report, and show a plan before applying.

**Automated checks**

Test undo removes transfers created by report but preserves asset reused by other reports.

**Manual verification**

```bash
fin report undo <id> --preview
fin report undo <id> --confirm
```

---

# Milestone 13 — User evaluation scenarios

These are end-to-end checks the person monitoring coding agents should run periodically.

## Scenario A — Fresh install

```bash
uv pip install -e backend
npm install
npm --prefix frontend install
uv run pytest backend/tests -q
npm run dev
```

Pass criteria:

Backend, frontend, and tests all work.

---

## Scenario B — Manual domain object save

Run a demo command or script that creates:

1. Asset `USD`
2. Account `Demo Checking`
3. Statement of `100 USD`
4. Tag `reviewed`
5. Comment `Initial balance`

Pass criteria:

`Report.plan()` shows pending inserts.
`Report.save()` commits.
Reloading DB shows all objects and relations.

---

## Scenario C — Generic CSV import

```bash
fin normalize tests/fixtures/simple_bank.csv --db data/demo.db --preview
fin normalize tests/fixtures/simple_bank.csv --db data/demo.db --save
```

Pass criteria:

Preview does not mutate DB.
Save creates report and transfers.
Repeated save warns about duplicate source.

---

## Scenario D — Broker import

```bash
fin normalize data/fidelity_activity.csv --broker fidelity-activity --preview
```

Pass criteria:

Recognized rows are classified.
Unknown rows are preserved with warnings.
No raw row is silently dropped.

---

## Scenario E — Reconciliation

```bash
fin reconcile --account "Demo Checking" --asset USD --from 2026-01-01 --to 2026-01-31
```

Pass criteria:

Output clearly says `OK` or shows exact difference and contributing rows.

---

## Scenario F — Web review

```bash
npm run dev
```

Pass criteria:

User can open frontend, view transfers, view reports, inspect import warnings, and reach API docs.

---

# Coding-agent PR template

Each coding agent should include this in its final message or PR description:

````markdown
## Goal

What feature or fix was implemented?

## Files changed

- `path/to/file.py`: what changed
- `path/to/test.py`: what was tested

## Behavior added

What can the user now do?

## Verification

Commands run:

```bash
pytest backend/tests -q
npm --prefix frontend run build
````

Manual checks:

1. Started `npm run dev`
2. Opened `http://127.0.0.1:5173`
3. Verified ...

## Known limitations

What is intentionally not implemented yet?

```

---

# Recommended implementation order

The best sequence is:

1. Stabilize setup and docs.
2. Finalize schema and migrations.
3. Finish domain model, identity map, staged edits, `plan()`, and `save()`.
4. Build generic CSV normalization.
5. Add broker-specific parsers.
6. Add reconciliation.
7. Add tax primitives.
8. Add US tax.
9. Add German tax.
10. Expand FastAPI.
11. Expand frontend.
12. Add audit, undo, and safety workflows.

This order keeps the system usable after every milestone. The user should never have to wait until the end to evaluate progress; every milestone has a CLI command, test suite, or web page that proves the feature works.
```
