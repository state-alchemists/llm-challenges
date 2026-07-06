# Audit: credentials.py

**What it does:** Returns database connection settings (host, port, user,
password, and an API key) for the primary database, and constructs a
connection string from those values.

**Problem — hardcoded secrets in source code:**

The module embeds a production password (`S3cr3t-Pr0d-Pass!`) and a live
Stripe API key (`sk_live_9f2b7c1e4a8d6f0b3e5a`) as string literals in
`get_db_config()`. The comment `# Left in from local testing` confirms
these were meant to be removed before deployment but were not.

Consequences:
- Anyone with read access to the repository — including CI logs, backups,
  or a developer's local checkout — has the production database password
  and a live Stripe secret key.
- A leaked `sk_live_` key can be used to make fraudulent charges, refund
  payments, or access customer PII through the Stripe API.
- If the database is exposed to the internet (or an attacker reaches it
  through another vector), the hardcoded credential provides direct
  access.

**Fix:** Remove secrets from the source. Read them from environment
variables or a secrets manager at startup. Rotate the compromised
credentials immediately.
