import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nms.db")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
PING_INTERVAL_SECONDS = int(os.getenv("PING_INTERVAL_SECONDS", "30"))
PING_TIMEOUT_SECONDS = float(os.getenv("PING_TIMEOUT_SECONDS", "2"))
STATUS_HISTORY_KEEP = int(os.getenv("STATUS_HISTORY_KEEP", "30"))  # readings kept per device for sparkline