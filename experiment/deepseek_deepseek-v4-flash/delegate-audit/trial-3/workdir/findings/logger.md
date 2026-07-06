# Audit: logger.py

**What it does:** Provides structured logging for authentication events.
`log_login_attempt` records the username, password, and success status
of each login attempt for the audit trail.

**Problem — logging plaintext passwords:**

The function accepts the cleartext `password` parameter and passes it to
`log.info(...)`. Every login attempt password is written to the log
stream in plain text.

Consequences:
- Logs are a high-exposure surface: they are shipped to log
  aggregators, indexed by SIEM tools, retained for compliance, and
  often visible to operators, SREs, and support staff. Anyone with log
  access can harvest user passwords.
- This violates fundamental security hygiene (never log secrets) and
  likely breaches compliance requirements (PCI DSS 3.2 — 10.3
  prohibits logging sensitive auth data; GDPR Art. 32 — failure to
  protect personal data).
- If logs are ingested into a search/index system without access
  controls, a compromise of that system leaks every credential.

**Fix:** Remove `password` from the log call entirely. If the audit
trail needs to distinguish login attempts, log a one-way hash of the
password (e.g. `sha256(password).hexdigest()[:16]`) but be aware that
short hashes of low-entropy secrets are still guessable — the safer
choice is to log only the username and success status.
