import os
from pathlib import Path
from dotenv import load_dotenv

# Locate the root directory (one level up from /app) where .env lives
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"

# Load the environment variables from the .env file
load_dotenv(dotenv_path=env_path)

# Export the variables
DATABASE_URL = os.getenv("DATABASE_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
PING_INTERVAL_SECONDS = int(os.getenv("PING_INTERVAL_SECONDS", "60"))
