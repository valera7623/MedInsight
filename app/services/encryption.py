import logging
from functools import lru_cache
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    pass


@lru_cache(maxsize=1)
def _get_identity_secret() -> str:
    if settings.ENCRYPTION_KEY:
        return settings.ENCRYPTION_KEY.strip()

    key_path = Path(settings.ENCRYPTION_KEY_PATH)
    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()

    raise EncryptionError("Encryption key not configured")


def ensure_encryption_key() -> str:
    """Generate encryption key file if missing."""
    if settings.ENCRYPTION_KEY:
        return settings.ENCRYPTION_KEY

    key_path = Path(settings.ENCRYPTION_KEY_PATH)
    key_path.parent.mkdir(parents=True, exist_ok=True)

    if key_path.exists():
        return key_path.read_text(encoding="utf-8").strip()

    try:
        from pyrage import x25519

        identity = x25519.Identity.generate()
        secret = str(identity)
        key_path.write_text(secret, encoding="utf-8")
        key_path.chmod(0o600)
        logger.info("Generated new age encryption key at %s", key_path)
        return secret
    except ImportError:
        raise EncryptionError("Cannot generate key: install pyrage") from None


def _encrypt_bytes(data: bytes) -> bytes:
    if not settings.ENCRYPTION_ENABLED:
        return data

    secret = _get_identity_secret()
    from pyrage import encrypt, x25519

    identity = x25519.Identity.from_str(secret)
    return encrypt(data, [identity.to_public()])


def _decrypt_bytes(data: bytes) -> bytes:
    if not settings.ENCRYPTION_ENABLED:
        return data

    secret = _get_identity_secret()
    from pyrage import decrypt, x25519

    identity = x25519.Identity.from_str(secret)
    return decrypt(data, [identity])


def encrypted_storage_path(tenant_id: int, patient_id: int, filename: str) -> Path:
    base = Path(settings.STORAGE_PATH) / "encrypted" / f"tenant_{tenant_id}" / f"patient_{patient_id}"
    base.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    if not safe_name.endswith(".age"):
        safe_name = f"{safe_name}.age"
    return base / safe_name


def encrypt_bytes(data: bytes, tenant_id: int, patient_id: int, filename: str) -> tuple[str, int]:
    """Encrypt bytes and save to disk. Returns (path, size)."""
    if settings.ENCRYPTION_ENABLED:
        ensure_encryption_key()
        _get_identity_secret.cache_clear()

    if not settings.ENCRYPTION_ENABLED:
        plain_dir = Path(settings.STORAGE_PATH) / str(tenant_id) / str(patient_id)
        plain_dir.mkdir(parents=True, exist_ok=True)
        dest = plain_dir / Path(filename).name
        dest.write_bytes(data)
        return str(dest), len(data)

    encrypted = _encrypt_bytes(data)
    dest = encrypted_storage_path(tenant_id, patient_id, filename)
    dest.write_bytes(encrypted)
    return str(dest), len(encrypted)


def encrypt_file(file_path: str, tenant_id: int, patient_id: int) -> str:
    path = Path(file_path)
    data = path.read_bytes()
    enc_path, _ = encrypt_bytes(data, tenant_id, patient_id, path.name)
    path.unlink(missing_ok=True)
    return enc_path


def decrypt_file(encrypted_path: str) -> bytes:
    """Decrypt file to memory — never writes plaintext to disk."""
    data = Path(encrypted_path).read_bytes()
    if encrypted_path.endswith(".age") or Path(encrypted_path).parent.name.startswith("tenant_"):
        return _decrypt_bytes(data)
    if settings.ENCRYPTION_ENABLED:
        return _decrypt_bytes(data)
    return data


def rotate_encryption_key(new_secret: str) -> int:
    """Re-encrypt all .age files with a new key. Returns count of rotated files."""
    old_secret = _get_identity_secret()
    encrypted_root = Path(settings.STORAGE_PATH) / "encrypted"
    if not encrypted_root.exists():
        return 0

    rotated = 0
    for enc_file in encrypted_root.rglob("*.age"):
        plaintext = _decrypt_bytes_with_secret(enc_file.read_bytes(), old_secret)
        new_encrypted = _encrypt_bytes_with_secret(plaintext, new_secret)
        enc_file.write_bytes(new_encrypted)
        rotated += 1

    key_path = Path(settings.ENCRYPTION_KEY_PATH)
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text(new_secret.strip(), encoding="utf-8")
    key_path.chmod(0o600)
    _get_identity_secret.cache_clear()
    return rotated


def _decrypt_bytes_with_secret(data: bytes, secret: str) -> bytes:
    from pyrage import decrypt, x25519

    identity = x25519.Identity.from_str(secret)
    return decrypt(data, [identity])


def _encrypt_bytes_with_secret(data: bytes, secret: str) -> bytes:
    from pyrage import encrypt, x25519

    identity = x25519.Identity.from_str(secret)
    return encrypt(data, [identity.to_public()])
