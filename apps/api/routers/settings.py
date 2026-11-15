"""Per-user autonomy, budgets, saved searches, memory viewer, marketplace status."""

from fastapi import APIRouter, HTTPException

from agent.memory.store import delete_memory, list_memory
from apps.api.core import PREFS
from apps.api.deps import State, User
from apps.api.schemas import MemoryItem, MemoryOut, SavedSearch, SettingsIn, SettingsOut, StatusOut

router = APIRouter(tags=["settings"])


async def current(state: State, user: User) -> SettingsOut:
    s = await state.user_settings(user)
    searches = s.scout.saved_searches.get(user["persona"], [])
    return SettingsOut(auto_skip_low_fit=s.autonomy.auto_skip_low_fit, max_tokens_per_job=s.budgets.max_tokens_per_job,
                       max_revisions=s.budgets.max_revisions,
                       weekly_connects_budget=s.bidding_rules.weekly_connects_budget,
                       saved_searches=[SavedSearch.model_validate(x) for x in searches])


@router.get("/settings", response_model=SettingsOut)
async def get_settings(state: State, user: User) -> SettingsOut:
    return await current(state, user)


@router.put("/settings", response_model=SettingsOut)
async def put_settings(body: SettingsIn, state: State, user: User) -> SettingsOut:
    prefs = {**await state.prefs(user["username"]), **body.model_dump(exclude_none=True, exclude={"auto_send"})}
    await state.store.aput((PREFS, user["username"]), "settings", prefs)
    return await current(state, user)


@router.get("/settings/memory", response_model=MemoryOut)
async def memory(state: State, user: User) -> MemoryOut:
    return MemoryOut(items=[MemoryItem.model_validate(i) for i in await list_memory(state.store, user["username"])])


@router.delete("/settings/memory/{kind}/{key}", status_code=204)
async def forget(kind: str, key: str, state: State, user: User) -> None:
    if not await delete_memory(state.store, user["username"], kind, key):
        raise HTTPException(404, "no such memory item")


@router.get("/status", response_model=StatusOut)
async def status(state: State, user: User) -> StatusOut:
    """Drives the degraded-mode banner."""
    try:
        layer = await state.layer(user["mcp_user"])
        servers = await layer.server_status()
        # the mcp server can be up while the marketplace behind it is not
        probe = await layer.call("get_connects_balance", {})
        up = servers.get("marketplace") == "up" and probe.get("error") != "marketplace_down"
    except Exception:  # noqa: BLE001
        servers, up = {"marketplace": "down"}, False
    return StatusOut(marketplace="up" if up else "down", servers=servers, degraded=not up)
