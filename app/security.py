
from datetime import datetime, timezone, timedelta
from typing import Optional

import bcrypt
import jwt
from jwt.exceptions import InvalidTokenError, PyJWTError

from app.config import settings


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt with a random salt."""
    pwd_bytes = password.encode("utf-8")

    if len(pwd_bytes) > 72:
        raise ValueError("Password cannot exceed 72 bytes in length")

    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)

    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash."""
    try:
        plain_bytes = plain_password.encode("utf-8")

        if len(plain_bytes) > 72:
            return False

        hash_bytes = hashed_password.encode("utf-8")

        return bcrypt.checkpw(plain_bytes, hash_bytes)

    except Exception:
        return False


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Generate a signed JWT access token with an expiration claim."""
    to_encode = data.copy()
    now = datetime.now(timezone.utc)

    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(
            minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
        )

    to_encode.update({
        "exp": expire,
        "iat": now,
    })

    return jwt.encode(
        to_encode,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> dict:
    """Decode and validate a signed JWT access token."""
    try:
        return jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

    except PyJWTError:
        raise InvalidTokenError("Invalid or expired token")
