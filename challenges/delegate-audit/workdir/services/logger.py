"""Structured request logging for the auth service."""

import logging

log = logging.getLogger("auth")


def log_login_attempt(username: str, password: str, success: bool) -> None:
    """Record a login attempt for the audit trail."""
    log.info(
        "login attempt user=%s password=%s success=%s",
        username,
        password,
        success,
    )
