from __future__ import annotations

import argparse
import getpass
import secrets

from cryptography.fernet import Fernet

from apps.api.wearo_api.admin_auth import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Cost Lab credentials")
    parser.add_argument("command", choices=("hash-password", "generate-secrets"))
    args = parser.parse_args()
    if args.command == "hash-password":
        first = getpass.getpass("Password: ")
        if first != getpass.getpass("Confirm password: "):
            raise SystemExit("Passwords do not match")
        print(hash_password(first).decode())
    else:
        print(f"COST_LAB_SESSION_SECRET={secrets.token_urlsafe(48)}")
        print(f"COST_LAB_ENCRYPTION_KEY={Fernet.generate_key().decode()}")


if __name__ == "__main__":
    main()
