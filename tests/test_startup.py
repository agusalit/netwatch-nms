from pathlib import Path

from app import config
from app.logging_config import configure_logging
from app.startup_checks import run_startup_checks


def test_configure_logging_is_idempotent_and_creates_log_dir():
    configure_logging()
    configure_logging()  # must not raise or stack a second handler
    assert Path("logs").exists()


def test_run_startup_checks_does_not_raise_with_missing_config(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_PASSWORD_HASH", "")
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    run_startup_checks()


def test_run_startup_checks_does_not_raise_with_partial_telegram_config(monkeypatch):
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "sometoken")
    monkeypatch.setattr(config, "TELEGRAM_CHAT_ID", "")
    run_startup_checks()