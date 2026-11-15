"""Users, scrypt password hashes and signed bearer tokens."""

import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from langgraph.store.base import BaseStore

from agent.config import Settings
from agent.local_stack import user_for

USERS = ("users",)
_fallback_secret = secrets.token_hex(32)


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or os.urandom(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return f"scrypt${salt.hex()}${digest.hex()}"


def check_password(password: str, stored: str) -> bool:
    _, salt, digest = stored.split("$")
    return hmac.compare_digest(hash_password(password, bytes.fromhex(salt)).split("$")[2], digest)


def secret(settings: Settings) -> str:
    # no key set: tokens last until restart
    return os.getenv(settings.api.secret_env) or _fallback_secret


def make_token(username: str, settings: Settings) -> tuple[str, int]:
    seconds = settings.api.token_minutes * 60
    claims = {"sub": username, "exp": datetime.now(UTC) + timedelta(seconds=seconds)}
    return jwt.encode(claims, secret(settings), algorithm="HS256"), seconds


def read_token(token: str, settings: Settings) -> str | None:
    try:
        return str(jwt.decode(token, secret(settings), algorithms=["HS256"])["sub"])
    except jwt.PyJWTError:
        return None


async def get_user(store: BaseStore, username: str) -> dict[str, Any] | None:
    item = await store.aget(USERS, username)
    return item.value if item else None


async def create_user(store: BaseStore, username: str, password: str, persona: str) -> dict[str, Any]:
    user = {"username": username, "persona": persona, "mcp_user": user_for(persona),
            "password_hash": hash_password(password)}
    await store.aput(USERS, username, user)
    return user


async def ensure_reviewer(store: BaseStore, settings: Settings) -> None:
    account = settings.api.reviewer
    if await get_user(store, account.username) is None:
        await create_user(store, account.username, account.password, account.persona)
