# Refactoring Server Log Pipeline

## Overview
Durable learnings and conventions established during the log processing pipeline refactor challenge.

## Log Parsing via Regex
- Rather than using custom split logic which fails on dynamic-length values or varying line lengths, pre-compiled regex objects (`re.compile`) provide reliable pattern matching for dates, logging levels, user actions, and API latencies.
- Breaking line parsing into a modular line parser `_parse_line` reduces nesting depth and cognitive complexity, making the code much easier to maintain.

## SQL Parameterization in SQLite
- Parameterizing sqlite3 query inputs via `?` placeholders prevents SQL injection vulnerabilities and ensures type safety.
- Avoid passing formatted/concatenated strings (using `%`, `+`, or f-strings) directly into execution methods.

## Environment-based Configurations
- Defining connection attributes and source/destination file paths through environment variables via `os.getenv` allows external configuration without leaking raw credentials.
- Keeping defaults aligned with local developer fixtures ensures smooth out-of-the-box local executions.

## Backlinks
- [index](../index.md)
- [2026-07-30 log](../activity-log/2026/2026-07/2026-07-30.md)
