import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./nms.db")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
PING_INTERVAL_SECONDS = int(os.getenv("PING_INTERVAL_SECONDS", "30"))
PING_TIMEOUT_SECONDS = float(os.getenv("PING_TIMEOUT_SECONDS", "2"))
STATUS_HISTORY_KEEP = int(os.getenv("STATUS_HISTORY_KEEP", "30"))  # readings kept per device for sparkline

DISPLAY_TIMEZONE = os.getenv("DISPLAY_TIMEZONE", "Asia/Makassar")  # WITA (Bali)

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH", "")
SESSION_SECRET_KEY = os.getenv("SESSION_SECRET_KEY", "")