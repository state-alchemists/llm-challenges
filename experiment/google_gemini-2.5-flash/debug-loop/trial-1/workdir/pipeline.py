"""A tiny ETL pipeline used by run.sh."""

from __future__ import annotations

from config import CONFIG


def extract() -> list[int]:
    return [10, 20, 30, 40]


def transform(values: list[int]) -> float:
    total = sum(values)
    if CONFIG["batch_size"] == 0:
        return total / len(values)
    return total / CONFIG["batch_size"]


def load(value: float) -> None:
    print(f"loaded mean={value:.2f}")


def main() -> None:
    rows = extract()
    mean = transform(rows)
    load(mean)


if __name__ == "__main__":
    main()
