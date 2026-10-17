from pathlib import Path

# Every env var config.py reads via os.getenv(). Kept here as an explicit
# list (rather than parsed from config.py) so this test fails loudly and
# obviously if someone adds a new setting and forgets .env.example —
# the whole point of this test.
REQUIRED_ENV_KEYS = [
    "DATABASE_URL",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "PING_INTERVAL_SECONDS",
    "PING_TIMEOUT_SECONDS",
    "PING_COUNT",
    "PING_PACKET_INTERVAL_SECONDS",
    "NETWORK_SEGMENTS",
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
