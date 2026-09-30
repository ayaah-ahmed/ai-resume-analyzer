"""Password hashing + bearer-token sessions stored in SQLite."""
import hashlib
import hmac
import secrets
import sqlite3

from fastapi import Depends, Header, HTTPException

from .database import get_db


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return digest.hex(), salt


def verify_password(password: str, password_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return hmac.compare_digest(candidate, password_hash)


def create_session(db: sqlite3.Connection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.execute("INSERT INTO sessions(token, user_id) VALUES (?, ?)", (token, user_id))
    db.commit()
    return token


def extract_token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing or invalid Authorization header (use 'Bearer <token>').")
    return authorization.split(" ", 1)[1].strip()


def get_current_user(
    authorization: str | None = Header(default=None),
    db: sqlite3.Connection = Depends(get_db),
) -> sqlite3.Row:
    token = extract_token(authorization)
    row = db.execute(
        "SELECT u.* FROM users u JOIN sessions s ON s.user_id = u.id WHERE s.token = ?", (token,)
    ).fetchone()
    if row is None:
        raise HTTPException(401, "Session expired or invalid. Please log in again.")
    return row
