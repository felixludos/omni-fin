# Omnifin Schema Design Philosophy

## Core Principle: Minimal Columns, Maximum Flexibility

The database schema intentionally keeps column counts minimal on core tables (accounts, entities, statements). This prevents schema drift and avoids the temptation to add "one more column" for every new piece of data. Instead, additional information is attached through two established mechanisms: **comments** (for free-text / structured values) and **tags** (for categorical/classification values).

## Attaching Custom Information

### Comments (Free-Text & Structured Values)

Use the `comments` table with a type-based annotation when you need to store:

- **Free text:** Notes, descriptions, metadata
- **Structured values:** Dates (`settled_at`, `acquisition_date`), IDs (`tax_id`, `ibkr_ticker`), amounts (`cost_basis`)
- **Arbitrary key-value pairs** that don't warrant a dedicated column

Comments are linked to entities via junction tables (e.g., `entity_comments`, `transfer_comments`). Each comment has a `type` field for categorization.

Example: Attaching a tax ID to an entity:
```python
entity.comment(Comment(content="US-123456789", type="tax_id"))
```

### Tags (Categorical / Classification Values)

Use the `tags` table with a category-based annotation when you need to store:

- **Classifications:** Jurisdiction (`category: "jurisdiction"`), account subtype (`category: "account_subtype"`)
- **Labels:** `tax`, `investment`, `retirement`
- **Enumerations** that are too sparse for columns but structured enough for deduplication

Tags have a UNIQUE(name, category) constraint preventing duplicate tag creation. They link to entities via junction tables (e.g., `entity_tags`, `account_tags`).

Example: Tagging an entity with its jurisdiction:
```python
entity.add_tags(Tag(name="DE", category="jurisdiction"))
```

## When to Add a Column

A column should only be added when ALL of the following are true:

1. The field is **universally required** on every row of that table (not optional)
2. The field is used in **queries/filters frequently enough** to warrant an index
3. The field represents a **core concept** intrinsic to the entity (not ancillary metadata)

If any condition fails, use comments or tags instead.

## Examples by Table

| Table | Attached via Comments (type) | Attached via Tags (category) |
|---|---|---|
| Account | `settled_at`, `institution` (legacy) | `account_subtype`, `retirement`, `tax` |
| Entity | `tax_id`, `registration_date` | `jurisdiction`, `entity_size` |
| Statement | `source_note`, `reconciliation_status` | — |
| Transfer | `settled_at`, `memo` | `recurring`, `manual_entry` |

## Schema Versioning

New columns should be added via migrations (see `schema_migrations` table) rather than modifying existing CREATE TABLE statements. This ensures backward compatibility for seed data and existing databases.