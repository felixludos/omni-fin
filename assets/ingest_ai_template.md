# Omnifin Ingestion Prompt Template

You are converting one CSV row into Omnifin database objects.

Return only valid JSON with this schema shape:
- summary: string
- confidence: number between 0 and 1
- objects: array of objects

Each object entry:
- object_type: one of asset, account, transfer, event, investment_sale, statement
- data: object payload
- note: optional string

## Context
- filename: {{filename}}
- row_index: {{row_index}}
- document_hash: {{document_hash}}
- row_hash: {{row_hash}}

## CSV Metadata
headers:
{{headers_json}}

checks:
{{checks_json}}

## Existing Accounts
{{existing_accounts_json}}

## Existing Assets
{{existing_assets_json}}

## Input Row
{{row_json}}

## Output Guidance
1. Reuse existing accounts/assets when possible.
2. Prefer canonical object sets with complete required fields.
3. For transfer objects, include:
   - date (ISO-8601)
   - amount (positive numeric)
   - unit_symbol
   - sender_account_name
   - receiver_account_name
   - event_type
   - event_name
4. Use statement object only for balance-style rows.
5. Keep uncertain values in note and lower confidence.
6. Do not include markdown or explanations.
