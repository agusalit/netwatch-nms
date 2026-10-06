import logging

from app import config

logger = logging.getLogger("nms.startup")


def run_startup_checks():
    """Logs warnings for common misconfigurations at boot, so gaps are
    visible immediately in the log instead of surfacing later as a silent
    no-op (e.g. a login nobody can complete, or an alert that never sends).
    Deliberately doesn't block startup — this is a basic, single-admin
    tool, not a service with hard config requirements."""
    if not config.ADMIN_PASSWORD_HASH:
        logger.warning(
            "ADMIN_PASSWORD_HASH is not set — no one will be able to log in "
            "until you run scripts/generate_password_hash.py and set it in .env."
        )

    has_token = bool(config.TELEGRAM_BOT_TOKEN)
    has_chat_id = bool(config.TELEGRAM_CHAT_ID)
    if has_token != has_chat_id:
        logger.warning(
            "Only one of TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID is set in .env — "
            "both are required for Telegram alerts; status-change alerts will "
            "silently do nothing until both are set."
        )
    elif not has_token:
        logger.info("Telegram alerts are not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID empty).")