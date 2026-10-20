"""The FastAPI application: the backend's single entry point.

Run from backend/ (--reload-dir app: watch only our code, not the 1,000+ files in .venv):
    uv run uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000

Interactive API documentation (generated from the code): http://127.0.0.1:8000/docs
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import categories, recipes
from app.config import load_settings
from app.db import make_engine, make_session_factory
from app.errors import error_response, install_error_handlers
from app.seed import create_tables, seed_new_database

log = logging.getLogger("uvicorn.error")  # uvicorn shows this logger's INFO lines in the terminal


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Runs once at start-up (before `yield`) and once at shutdown (after it)."""
    settings = load_settings()
    database_path = settings.database_path
    is_new = not database_path.exists()
    engine = make_engine(database_path, echo=settings.sql_echo)
    create_tables(engine)
    app.state.session_factory = make_session_factory(engine)
    if is_new:
        seed_new_database(app.state.session_factory)
        log.info("Created a new recipes database with the starter categories and sample recipes: %s", database_path)
    else:
        log.info("Using the recipes database at %s", database_path)
    yield
    engine.dispose()


app = FastAPI(
    title="Recipe Notebook API",
    version="0.3.0",
    description="Local backend of the recipe notebook. All endpoints live under /api. "
    "Recipes and categories are stored in a local SQLite file.",
    lifespan=lifespan,
    # "/api/recipes/" is a 404, not a redirect: a redirect would send the browser past the
    # Vite proxy to the backend's own address.
    redirect_slashes=False,
    redoc_url=None,  # one documentation page (/docs) is enough
)

# Pages allowed to change data: the notebook (Vite dev server) and this server's own /docs.
ALLOWED_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8000", "http://127.0.0.1:8000"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def reject_changes_from_other_sites(request: Request, call_next):
    # Browsers send an Origin header with requests that change data. Without this check,
    # any website you visit could submit a form to http://127.0.0.1:8000 and edit your recipes.
    origin = request.headers.get("origin")
    if request.method not in SAFE_METHODS and origin is not None and origin not in ALLOWED_ORIGINS:
        return error_response(403, "forbidden_origin", "Changes are only accepted from the notebook page.")
    return await call_next(request)


# Answer only requests addressed to this computer by name. A web page that tricks the
# browser into sending requests here under another host name (DNS rebinding) gets a 400.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
install_error_handlers(app)
app.include_router(recipes.router)
app.include_router(categories.router)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    """Lets the frontend (and you) check that the backend is running."""
    return {"status": "ok"}
