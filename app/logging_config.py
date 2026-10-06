import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logging():
    """Adds a rotating file handler alongside uvicorn's existing console
    output — nothing is removed, this just also writes to logs/netwatch.log
    so history survives past your terminal's scrollback. Rotates at 2MB,
    keeping 5 backups (~10MB total ceiling)."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    root = logging.getLogger()

    # Idempotent — avoids stacking duplicate handlers (and duplicate log
    # lines) if this ever gets called more than once in the same process.
    already_configured = any(getattr(h, "_netwatch_marker", False) for h in root.handlers)
    if already_configured:
        return

    file_handler = RotatingFileHandler(
        log_dir / "netwatch.log", maxBytes=2_000_000, backupCount=5
    )
    file_handler._netwatch_marker = True
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    file_handler.setLevel(logging.INFO)

    root.setLevel(logging.INFO)
    root.addHandler(file_handler)