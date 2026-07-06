# Audit: `logger.py`

## What it does

Provides structured request logging for the auth service, specifically a
function to record login attempts in the audit trail.

## Problem — Plain-text password in log output

`log_login_attempt()` logs the `password` parameter directly into the
`%s` format substitution in the log message.  This means every
successful or failed login attempt writes the user's password into the
application log files.

### Impact

- Anyone with read access to the log files (or a log-aggregation system
  such as CloudWatch, ELK, Loki) has a live record of all user passwords.
- Violates PCI DSS and most security-compliance frameworks — passwords
  must never be stored in plain text, including in logs.
- Logs are often retained for months or years, widening the blast radius
  of any future log breach.

### Remediation

- Remove `password` from the log call.  Logging the username and
  success/failure status is sufficient for an audit trail.
- If account-replay detection is needed, log a one-way hash of the
  password or a masked substring (`p[0] + "***"`), but only after
  confirming this doesn't weaken the security model.
- Consider logging a correlation ID (e.g. request UUID) instead, and
  keep raw login events in a separate, short-lived, access-controlled
  sink if they are truly needed for forensics.
