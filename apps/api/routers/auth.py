"""Login, registration and the current user."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm

from apps.api.auth import check_password, create_user, get_user, make_token
from apps.api.deps import State, User
from apps.api.schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


async def login_user(state: State, username: str, password: str) -> TokenOut:
    user = await get_user(state.store, username)
    if user is None or not check_password(password, user["password_hash"]):
        raise HTTPException(401, "wrong username or password")
    token, seconds = make_token(username, state.settings)
    return TokenOut(access_token=token, expires_in=seconds)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, state: State) -> TokenOut:
    return await login_user(state, body.username, body.password)


@router.post("/token", response_model=TokenOut, include_in_schema=False)
async def token(form: Annotated[OAuth2PasswordRequestForm, Depends()], state: State) -> TokenOut:
    # swagger "authorize" button
    return await login_user(state, form.username, form.password)


@router.post("/register", response_model=UserOut, status_code=201)
async def register(body: RegisterIn, state: State) -> UserOut:
    if await get_user(state.store, body.username):
        raise HTTPException(409, "username taken")
    user = await create_user(state.store, body.username, body.password, body.persona)
    return UserOut(username=user["username"], persona=user["persona"])


@router.get("/me", response_model=UserOut)
async def me(user: User) -> UserOut:
    return UserOut(username=user["username"], persona=user["persona"])
