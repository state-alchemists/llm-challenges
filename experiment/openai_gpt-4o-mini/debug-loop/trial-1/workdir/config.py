"""Configuration constants for the pipeline."""

CONFIG = {
    "source": "events.csv",
    "batch_size": 1,
}
settings = {
    "source": CONFIG["source"],
    "batch_size": CONFIG["batch_size"]
}