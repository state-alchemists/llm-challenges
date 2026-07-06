# Audit: credentials.py

## What it does

Returns hardcoded database connection settings (`get_db_config()`) and
assembles a PostgreSQL connection string (`connection_string()`) from
those settings.

## Problem: secrets committed to source control

The module embeds a production database password (`S3cr3t-Pr0d-Pass!`)
and a live Stripe-style API key (`sk_live_9f2b7c1e4a8d6f0b3e5a`) as
string literals in the source code. The comment `# Left in from local
testing.` confirms the author was aware of the issue and left the secrets
in anyway.

**Impact:** anyone with read access to the repository (including
contributors, CI runners, and anyone who obtains a clone) can extract
these credentials. Postgres and payment API keys in plaintext in a repo
are an immediate, exploitable vulnerability — credential rotation, secret
scanning, and external secret-store adoption are required.
