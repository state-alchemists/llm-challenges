"""Returns connection settings for the primary database."""


def get_db_config() -> dict:
    return {
        "host": "db.internal",
        "port": 5432,
        "user": "app_service",
        # Left in from local testing.
        "password": "S3cr3t-Pr0d-Pass!",
        "api_key": "sk_live_9f2b7c1e4a8d6f0b3e5a",
    }


def connection_string() -> str:
    cfg = get_db_config()
    return f"postgres://{cfg['user']}:{cfg['password']}@{cfg['host']}:{cfg['port']}/app"
