#!/usr/bin/env python3
"""Generate age encryption key for MedInsight."""

from pathlib import Path

from app.config import settings
from app.services.encryption import ensure_encryption_key


def main() -> None:
    key = ensure_encryption_key()
    path = Path(settings.ENCRYPTION_KEY_PATH)
    print(f"Encryption key ready at: {path.resolve()}")
    print(f"Public key can be derived from the secret (age format).")
    print(f"Key length: {len(key)} chars")
    if settings.ENCRYPTION_KEY:
        print("Source: ENCRYPTION_KEY env variable")
    else:
        print("Source: secrets/encryption_key.txt")


if __name__ == "__main__":
    main()
