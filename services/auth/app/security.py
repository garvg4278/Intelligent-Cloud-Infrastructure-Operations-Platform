from datetime import UTC, datetime, timedelta

import bcrypt
import jwt


def hash_password(password: str) -> str:
    hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


BCRYPT_MAX_BYTES = 72


def verify_password(plain_password: str, hashed_password: str) -> bool:
    encoded = plain_password.encode("utf-8")
    # bcrypt 5 raises ValueError past 72 BYTES. Login accepts any length, so
    # an over-long guess used to become an unhandled 500; it can never match
    # a stored hash (registration enforces the same limit), so it is simply
    # "wrong password".
    if len(encoded) > BCRYPT_MAX_BYTES:
        return False
    return bcrypt.checkpw(encoded, hashed_password.encode("utf-8"))


def create_token(subject: str, role: str, token_type: str, expires_delta: timedelta, secret: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str) -> dict:
    return jwt.decode(token, secret, algorithms=["HS256"])
