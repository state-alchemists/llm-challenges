# Migration to new_auth

- [ ] Replace all calls to legacy_auth() with new_auth() in identified code sections and adjust the scope accordingly.
- [ ] Update import statements for legacy_auth to use new_auth in all relevant files.
- [ ] Verify after changes, ensuring there are no remaining calls to legacy_auth and that the project still passes `python -c "import app"`.