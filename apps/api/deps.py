"""Request dependencies: app state and the signed-in user."""

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer

from apps.api.auth import get_user, read_token
from apps.api.core import AppState

bearer = OAuth2PasswordBearer(tokenUrl="/auth/token")


def app_state(request: Request) -> AppState:
    state: AppState = request.app.state.gigbid
    return state


async def current_user(token: Annotated[str, Depends(bearer)],
                       state: Annotated[AppState, Depends(app_state)]) -> dict[str, Any]:
    username = read_token(token, state.settings)
    user = await get_user(state.store, username) if username else None
    if user is None:
        raise HTTPException(401, "invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    return user


State = Annotated[AppState, Depends(app_state)]
User = Annotated[dict[str, Any], Depends(current_user)]
