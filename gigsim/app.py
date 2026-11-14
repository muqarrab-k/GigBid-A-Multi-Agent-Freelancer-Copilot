import sqlite3

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from gigsim import api_admin, api_public
from gigsim.deps import ApiError, Context, error_body
from gigsim.seeding import reset
from gigsim.settings import Settings, load_settings
from gigsim.store import Store


def create_app(settings: Settings | None = None) -> FastAPI:
    """GigSim app; seeds the database on first start."""
    settings = settings or load_settings()
    store = Store(settings.path(settings.storage))
    try:
        store.meta("now")
    except (KeyError, sqlite3.OperationalError):
        reset(store, settings)

    app = FastAPI(title="GigSim", version="1.0.0",
                  description="Simulated freelance marketplace for GigBid. See gigsim/README.md.")
    app.state.ctx = Context(settings, store)

    @app.exception_handler(ApiError)
    def api_error(request: Request, err: ApiError) -> JSONResponse:
        return JSONResponse(error_body(err.code, err.detail, **err.extra), status_code=err.status,
                            headers=err.headers)

    @app.exception_handler(RequestValidationError)
    def validation_error(request: Request, err: RequestValidationError) -> JSONResponse:
        fields = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in err.errors()]
        return JSONResponse(error_body("validation_error", fields), status_code=422)

    app.include_router(api_public.router)
    app.include_router(api_admin.router)
    return app
