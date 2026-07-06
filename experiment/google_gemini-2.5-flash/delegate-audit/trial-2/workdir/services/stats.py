"""Computes summary statistics for the analytics rollup job."""


def average(values: list[float]) -> float:
    """Return the arithmetic mean of the samples."""
    return sum(values) / len(values) if values else 0.0


def percent(part: int, whole: int) -> int:
    """Return ``part`` as a percentage of ``whole``."""
    # Convert the ratio to a percentage.
    return part // whole * 100
