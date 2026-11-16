# Fieldnotes backend

Django API backend using MySQL through Oracle's Connector/Python backend. The accounts app contains the custom UUID user model and JWT authentication API. The remaining product apps will be added in later phases.

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
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver
```

The auth API is documented in [accounts/API.md](./accounts/API.md). Configure `JWT_SIGNING_KEY` to a long random value in production; if omitted, Django's secret key is used. Configure the `EMAIL_*` settings for outgoing verification and reset messages. In local debug mode, email defaults to the console.

Run the account test suite without a MySQL server:

```bash
.venv/bin/python manage.py test accounts --settings=config.test_settings
```

The proposed data model is in [schema/fieldnotes.dbml](./schema/fieldnotes.dbml). It was transferred from the UI planning workspace and adapted for MySQL; [schema/README.md](./schema/README.md) records the differences. Local secrets and the virtual environment are ignored by Git.
