# Audit: logger.py

## What it does

Provides structured logging for authentication events.
`log_login_attempt()` records a username, password, and success flag to
the `auth` logger.

## Problem: passwords logged in cleartext

The `password` parameter is included verbatim in the log message via
`password=%s`. Any log sink (file, stdout, external aggregator) will
contain users' plaintext passwords.

**Impact:** a log breach or even routine log-access by internal staff
leaks authentication secrets. Passwords must never appear in log output.
The function should either redact the password (e.g. `"****"`) or omit it
entirely. The username and success/failure flag are sufficient for an
audit trail.
