"""Configuration constants for the pipeline."""

CONFIG = {
    "source": "events.csv",
    "batch_size": 0,
}

# Adding settings for the import to succeed
settings = {"batch_size": 1}