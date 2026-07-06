## services/logger.py

This module is responsible for structured request logging, specifically for login attempts in the auth service.

The critical security problem in this module is that the `log_login_attempt` function logs the user's password in plain text. Logging sensitive information like passwords, even in an audit trail, is a severe security vulnerability. If these logs are compromised, user credentials would be exposed. Passwords should never be logged; instead, only the username or a non-identifying hash of the attempt should be recorded for auditing purposes.