from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from .database import AuthSession, User, get_db


router = APIRouter(prefix="/api/auth", tags=["auth"])
COOKIE_NAME = "ai_kb_session"
SESSION_DAYS = 30
PBKDF2_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, expected = stored.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations))
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_login_session(response: Response, user: User, db: Session) -> None:
    token = secrets.token_urlsafe(48)
    expires = datetime.utcnow() + timedelta(days=SESSION_DAYS)
    db.add(AuthSession(user_id=user.id, token_hash=token_digest(token), expires_at=expires))
    db.commit()
    response.set_cookie(COOKIE_NAME, token, max_age=SESSION_DAYS * 86400, httponly=True, samesite="lax", secure=False, path="/")


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME, "")
    if not token:
        raise HTTPException(status_code=401, detail="请先登录")
    session = db.query(AuthSession).filter(AuthSession.token_hash == token_digest(token), AuthSession.expires_at > datetime.utcnow()).first()
    if not session:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录")
    user = db.get(User, session.user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def credentials(payload: dict) -> tuple[str, str]:
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    if not re_username(username):
        raise HTTPException(status_code=400, detail="用户名需为 3-32 位中文、字母、数字或下划线")
    if len(password) < 6 or len(password) > 128:
        raise HTTPException(status_code=400, detail="密码长度需为 6-128 位")
    return username, password


def re_username(username: str) -> bool:
    return 3 <= len(username) <= 32 and all(char == "_" or char.isalnum() or "\u4e00" <= char <= "\u9fff" for char in username)


@router.post("/register")
async def register(request: Request, response: Response, db: Session = Depends(get_db)):
    username, password = credentials(await request.json())
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=409, detail="用户名已存在")
    user = User(username=username, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    create_login_session(response, user, db)
    return {"user": {"id": user.id, "username": user.username}}


@router.post("/login")
async def login(request: Request, response: Response, db: Session = Depends(get_db)):
    username, password = credentials(await request.json())
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    create_login_session(response, user, db)
    return {"user": {"id": user.id, "username": user.username}}


@router.post("/logout")
async def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE_NAME, "")
    if token:
        db.query(AuthSession).filter(AuthSession.token_hash == token_digest(token)).delete(synchronize_session=False)
        db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user: User = Depends(current_user)):
    return {"user": {"id": user.id, "username": user.username}}

