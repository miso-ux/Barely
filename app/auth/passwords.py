import secrets

from pwdlib import PasswordHash

from app.services.errors import WeakPassword

MIN_PASSWORD_LENGTH = 8

_hasher = PasswordHash.recommended()  # Argon2id


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _hasher.verify(password, password_hash)


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise WeakPassword(min_length=MIN_PASSWORD_LENGTH)


def generate_temporary_password() -> str:
    return secrets.token_urlsafe(9)
