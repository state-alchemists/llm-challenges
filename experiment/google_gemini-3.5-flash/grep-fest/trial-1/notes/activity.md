# Activity Log

## [2026-06-19] Migrate `legacy_auth` to `new_auth`
- Automated AST/regex migration of 37 auto-generated modules under `app/`.
- Correctly classified modules into read vs write scope based on the specified naming conventions.
- Kept `legacy_auth` definition in `app/auth.py` intact for external callers.
- Verified zero residual call sites and clean importability of the `app` package.
