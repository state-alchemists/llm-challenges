# Audit: `credentials.py`

## What it does

Returns connection settings (host, port, user, password, API key) for the
primary database and exposes a convenience function that builds a
PostgreSQL connection string from those settings.

## Problem — Hardcoded production secrets in source

`get_db_config()` returns a dictionary containing a plain-text production
password (`S3cr3t-Pr0d-Pass!`) and a Stripe live-mode API key
(`sk_live_9f2b7c1e4a8d6f0b3e5a`). A comment on line 9 acknowledges these
were "Left in from local testing."

This is not a configuration or environment-variable lookup — every call
to `get_db_config()` or `connection_string()` exposes these secrets
directly from the source code.

### Impact

- Anyone with read access to the repository (or a compiled artifact,
  error traceback, or debug dump containing a call to this module)
  obtains a live API key and database credentials.
- Violates the most basic secret-management principle: credentials must
  never live alongside code.

### Remediation

- Rotate both the database password and the Stripe API key immediately
  — they are compromised by virtue of having been committed.
- Replace the hardcoded values with environment-variable lookups
  (e.g. `os.environ["DB_PASSWORD"]`) or a dedicated secrets manager.
- Add `credentials.py` to `.gitignore` and ship a `.env.example` or
  config template with placeholder values instead.
