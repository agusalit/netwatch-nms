"""
Backs up the current database, then replaces it with a fresh empty one built
from the current models. Use it to start clean after development, and to pick
up schema changes (the app's create_all never alters existing tables).

Stop NetWatch first (launcher/NetWatch-Stop.bat) — a running app would keep
writing to the file you are replacing.

Usage (run from the project root, with the venv active):
    python scripts/reset_database.py              # asks for confirmation
    python scripts/reset_database.py --yes        # no prompt
    python scripts/reset_database.py --no-backup  # skip the backup copy
"""
import argparse
import os
import sqlite3
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.engine import make_url

from app import config

COUNT_TABLES = ("devices", "status_logs", "traffic_logs")


def sqlite_path():
    url = make_url(config.DATABASE_URL)
    if url.get_backend_name() != "sqlite" or not url.database:
        sys.exit(f"reset_database.py only handles SQLite databases (DATABASE_URL={config.DATABASE_URL}).")
    return Path(url.database)


def app_is_running():
    port = os.getenv("NETWATCH_PORT", "8000")
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1)
        return True
    except Exception:
        return False


def row_counts(path):
    counts = {}
    with sqlite3.connect(path) as conn:
        for table in COUNT_TABLES:
            try:
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.OperationalError:
                counts[table] = 0
    return counts


def backup(path):
    backup_dir = path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{path.stem}-{datetime.now():%Y%m%d-%H%M%S}.db"
    # sqlite3's online backup API gives a consistent copy even if the file is in use.
    with sqlite3.connect(path) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return target


def main():
    parser = argparse.ArgumentParser(description="Back up and reset the NetWatch database")
    parser.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    parser.add_argument("--no-backup", action="store_true", help="skip the backup copy")
    parser.add_argument("--force", action="store_true", help="continue even if the app looks like it is running")
    args = parser.parse_args()

    path = sqlite_path()
    if app_is_running() and not args.force:
        sys.exit("NetWatch appears to be running. Stop it first (launcher/NetWatch-Stop.bat), "
                 "or pass --force if you are sure.")

    existed = path.exists()
    if existed:
        counts = row_counts(path)
        print(f"Database: {path}")
        print("Current contents: " + ", ".join(f"{n} {t}" for t, n in counts.items()))
    else:
        print(f"No database at {path} yet; a fresh one will be created.")

    if existed and not args.yes:
        if input("Replace it with an empty database? [y/N] ").strip().lower() != "y":
            sys.exit("Cancelled. Nothing was changed.")

    if existed and not args.no_backup:
        print(f"Backup written to {backup(path)}")

    if existed:
        for suffix in ("", "-wal", "-shm", "-journal"):
            Path(str(path) + suffix).unlink(missing_ok=True)

    path.parent.mkdir(parents=True, exist_ok=True)
    from app.models.database import init_db  # imported late: it builds the engine from DATABASE_URL
    init_db()
    print("Fresh database created with the current schema.")
    print("Next: add targets with  python scripts/import_devices.py <file.csv>  or from the dashboard.")


if __name__ == "__main__":
    main()
