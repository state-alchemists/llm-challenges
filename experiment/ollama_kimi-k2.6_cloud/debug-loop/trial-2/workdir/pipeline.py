"""A tiny ETL pipeline used by run.sh."""

from __future__ import annotations

from config import settings


def extract() -> list[int]:
    return [10, 20, 30, 40]


def transform(values: list[int]) -> float:
    total = sum(values)
    return total / len(values)


def load(value: float) -> None:
    print(f"loaded mean={value:.2f}")


def main() -> None:
    rows = extract()
    mean = transform(rows)
    load(mean)


if __name__ == "__main__":
    main()
