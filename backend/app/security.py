from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.config import get_config

COOKIE_NAME = "session"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int) -> str:
    cfg = get_config()
    payload = {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(hours=cfg.token_hours)}
    return jwt.encode(payload, cfg.secret_key, algorithm="HS256")


def decode_token(token: str) -> int | None:
    try:
        payload = jwt.decode(token, get_config().secret_key, algorithms=["HS256"])
        return int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
