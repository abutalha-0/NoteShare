# Fieldnotes schema

[`fieldnotes.dbml`](./fieldnotes.dbml) is the combined 24-table design for the current UI. The other documents in this directory explain page ownership, integrity rules, and the review findings. This folder contains design specifications, not Django models or applied migrations.

The diagram was transferred from the UI planning workspace and adapted to the backend's **MySQL 8** target:

- Logical UUIDs are represented as `char(32)`, matching Django's `UUIDField` storage on MySQL. Use `UUIDField` in Python models and the same type on every related key.
- Time values are `datetime(6)`; keep Django `USE_TZ=True` and store UTC through the ORM.
- Unique refresh/action token hashes are `char(64)` for SHA-256 hex digests. Never store raw tokens.
- Exactly-one-target checks use MySQL boolean expressions rather than PostgreSQL's `num_nonnulls` function.
- MySQL cannot use PostgreSQL-style partial unique indexes. Enforce one active moderation case per target with a generated active-target key and a unique index in a migration, or an equally strong database-level design. A service-only read-before-insert check is insufficient under concurrent requests.

The DBML enums describe allowed values. When writing Django models, choose `TextChoices`/`CharField` or native MySQL enums deliberately, and keep the migration representation consistent. Do not generate SQL directly from this diagram without reviewing Django model field types, indexes, and constraints.

The project currently has no application models or database migrations. Define the custom user model before the first migration.
