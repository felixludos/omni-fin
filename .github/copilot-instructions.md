# Omnifin Global Coding Standards

You are assisting an experienced engineer building Omnifin, a dual-interface financial orchestration and tax engine (Python CLI + FastAPI + Vite/TS Frontend).

## General Principles
- **No Fluff:** Provide code directly. Avoid conversational preambles ("Sure, I can help with that") or generic post-summaries unless clarifying a critical edge case.
- **Type Safety:** Enforce absolute type safety across both language ecosystems. No `any` in TypeScript; explicit type hints and Pydantic models in Python.
- **Performance:** Optimize for memory efficiency when processing large financial datasets (e.g., streaming large CSV reads via pandas/generators instead of loading everything into memory at once).
- **Security:** Never hardcode credentials, test API keys, or personal financial data. Ensure SQLite parameterized inputs are used everywhere to avoid SQL injection.