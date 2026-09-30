import sqlite3

from fastapi import APIRouter, Depends, Header, HTTPException

from ..database import get_db
from ..schemas import LoginIn, RegisterIn
from ..security import create_session, extract_token, get_current_user, hash_password, verify_password

router = APIRouter(prefix="/api/auth", tags=["Authentication"])


@router.post("/register", status_code=201, summary="Create a new account")
def register(body: RegisterIn, db: sqlite3.Connection = Depends(get_db)):
    if db.execute("SELECT 1 FROM users WHERE email = ?", (body.email,)).fetchone():
        raise HTTPException(409, "An account with this email already exists.")
    pw_hash, salt = hash_password(body.password)
    cur = db.execute("INSERT INTO users(name, email, password_hash, salt) VALUES (?,?,?,?)",
                     (body.name, body.email, pw_hash, salt))
    db.commit()
    token = create_session(db, cur.lastrowid)
    return {"token": token, "user": {"id": cur.lastrowid, "name": body.name, "email": body.email}}


@router.post("/login", summary="Log in and receive a bearer token")
def login(body: LoginIn, db: sqlite3.Connection = Depends(get_db)):
    user = db.execute("SELECT * FROM users WHERE email = ?", (body.email,)).fetchone()
    if user is None or not verify_password(body.password, user["password_hash"], user["salt"]):
        raise HTTPException(401, "Incorrect email or password.")
    token = create_session(db, user["id"])
    return {"token": token, "user": {"id": user["id"], "name": user["name"], "email": user["email"]}}


@router.post("/logout", summary="Invalidate the current token")
def logout(authorization: str | None = Header(default=None), db: sqlite3.Connection = Depends(get_db),
           _user=Depends(get_current_user)):
    db.execute("DELETE FROM sessions WHERE token = ?", (extract_token(authorization),))
    db.commit()
    return {"message": "Logged out successfully."}


@router.get("/me", summary="Current user profile")
def me(user=Depends(get_current_user)):
    return {"id": user["id"], "name": user["name"], "email": user["email"]}
