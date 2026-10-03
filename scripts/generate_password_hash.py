"""
Generates a bcrypt hash for the ADMIN_PASSWORD_HASH .env value.

Usage:
    python scripts/generate_password_hash.py
    python scripts/generate_password_hash.py "my-password"   # less safe: visible in shell history
"""
import sys
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.auth import hash_password


def main():
    password = sys.argv[1] if len(sys.argv) > 1 else getpass("Password to hash: ")
    print(hash_password(password))


if __name__ == "__main__":
    main()