"""Computes service health metrics from the raw event log."""

from __future__ import annotations

import csv


def load_events(path: str) -> list[dict[str, str]]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def success_rate(rows: list[dict[str, str]]) -> float:
    if not rows:
        return 0.0
    # A request is successful when its status is OK.
    ok = sum(1 for r in rows if r["status"] == "OK")
    return round(100.0 * ok / len(rows), 1)


def main() -> None:
    rows = load_events("events.csv")
    print(f"TOTAL={len(rows)}")
    print(f"SUCCESS_RATE={success_rate(rows)}")


if __name__ == "__main__":
    main()
