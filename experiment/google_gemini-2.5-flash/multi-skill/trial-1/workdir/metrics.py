"""Computes service health metrics from the raw event log."""

from __future__ import annotations

import csv


def load_events(path: str) -> list[dict[str, str]]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def success_rate(rows: list[dict[str, str]], endpoint: str | None = None) -> float:
    if endpoint:
        filtered_rows = [row for row in rows if row["endpoint"] == endpoint]
    else:
        filtered_rows = rows

    if not filtered_rows:
        return 0.0

    # A request is successful when its status is OK (case-insensitive).
    ok = sum(1 for r in filtered_rows if r["status"].lower() == "ok")
    return round(100.0 * ok / len(filtered_rows), 1)


def main() -> None:
    rows = load_events("events.csv")
    print(f"TOTAL={len(rows)}")
    print(f"SUCCESS_RATE={success_rate(rows, endpoint='/checkout')}")


if __name__ == "__main__":
    main()
