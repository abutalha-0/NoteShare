# Fieldnotes backend

Initial Django project scaffold. It uses the Django ORM with MySQL through Oracle's Connector/Python backend. No product apps or migrations have been added yet.

## Local setup

Requires Python 3.12 and a local MySQL 8 server.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Replace the example secret and database password in `.env`. Create a local MySQL database and user with permission to create and change tables:

```sql
CREATE DATABASE fieldnotes CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
CREATE USER 'fieldnotes'@'127.0.0.1' IDENTIFIED BY 'replace-with-local-database-password';
GRANT ALL PRIVILEGES ON fieldnotes.* TO 'fieldnotes'@'127.0.0.1';
```

Then verify the project:

```bash
.venv/bin/python manage.py check
```

**Before the first `migrate`:** define the intended custom user model with UUID IDs, or explicitly reconcile the existing authentication model. Django's default user model uses a different ID type than the proposed Fieldnotes schema. Switching user models after applying initial auth migrations is difficult, so database migrations intentionally begin in the next phase.

The proposed data model is in the adjacent `fieldnotes-site/fieldnotes.dbml` file. Local secrets and the virtual environment are ignored by Git.
