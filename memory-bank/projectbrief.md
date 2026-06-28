Omnifin is designed with a dual-interface architecture, providing two primary ways to interact with the system:

1. **Command Line Interface (`fin`):** An installable Python package providing a globally accessible CLI entry point. This allows you to directly run data pipelines, normalization scripts, and tax calculations from your terminal (e.g., `fin normalize data.csv --broker ibkr`) without needing to spin up a server.
2. **Full-Stack Web Application:** A unified monorepo containing a Vite frontend and a FastAPI backend. For local development, the entire stack boots up with a single command (`npm run dev`). This utilizes a tool like `concurrently` to launch both servers simultaneously, with the Vite dev server proxying `/api` requests to FastAPI to eliminate CORS issues.

---

### **Omnifin Implementation Plan**

#### **Phase 1: CLI Foundation & Normalization (Milestone 1)**

* **Goal:** Build the installable `omnifin` Python package and the `fin` CLI tool.
* **Tasks:**
* Initialize the monorepo structure and set up `pyproject.toml` (using Poetry or uv) to define the `fin` entry point pointing to a Click command group.
* Implement the core Pydantic models (`Asset`, `UniversalEvent`) and configure SQLite with strict schemas.
* Write the `fin normalize` script to ingest Fidelity/IBKR CSVs, utilizing the local LLM for unknown assets/events, and outputting to the console and database.



#### **Phase 2: The Core Ledger & Reconciliation Engine**

* **Goal:** Implement the business logic for the four pillars (Transactions, Assets, Statements, Accounts).
* **Tasks:**
* Expand the CLI with commands for statement ingestion (`fin ingest-statement`).
* Build the reconciliation algorithm to validate account balances against ingested events.
* Implement the `TransferMatch` logic to automatically detect and link transfers between internal accounts.



#### **Phase 3: Dual-Jurisdiction Tax Engine**

* **Goal:** Calculate taxable events for both US and German jurisdictions.
* **Tasks:**
* Develop the US module: implement FIFO/LIFO lot matching, Wash Sale tracking, and short/long-term capital gains.
* Develop the German module: implement strict FIFO, asset-class specific *Teilfreistellung* exemptions, and accumulating ETF *Vorabpauschale* logic.
* Expose these calculations via a new CLI command (`fin calculate-taxes --year 2026`).



#### **Phase 4: Full-Stack Integration & UI**

* **Goal:** Transition to the unified web interface for family-wide financial tracking.
* **Tasks:**
* Implement the FastAPI backend (`backend/omnifin/api/server.py`) to serve the SQLite data, and expose it via the CLI (`fin serve`).
* Initialize the Vite frontend (`frontend/`) and configure `package.json` with `concurrently` for the `npm run dev` command.
* Set up the Vite proxy to route `/api` to port 8000.
* Build the data-table views for manual overrides and visualization widgets for cross-currency net worth.
