from pathlib import Path

REQUIRED_ENV_KEYS = [
    "DATABASE_URL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "PING_INTERVAL_SECONDS",
    "PING_TIMEOUT_SECONDS",
    "STATUS_HISTORY_KEEP",
    "DISPLAY_TIMEZONE",
    "ADMIN_USERNAME",
    "ADMIN_PASSWORD_HASH",
    "SESSION_SECRET_KEY",
]


def test_env_example_exists_and_documents_all_required_keys():
    env_example_path = Path(__file__).resolve().parent.parent / ".env.example"
    assert env_example_path.exists(), (
        ".env.example is missing from the project root — anyone cloning "
        "this repo won't know which environment variables to set."
    )
    content = env_example_path.read_text()
    missing = [key for key in REQUIRED_ENV_KEYS if key not in content]
    assert not missing, f".env.example is missing these keys: {missing}"