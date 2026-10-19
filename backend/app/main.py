"""The FastAPI application: the backend's single entry point.

Run from backend/ (--reload-dir app: watch only our code, not the 1,000+ files in .venv):
    uv run uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000

Interactive API documentation (generated from the code): http://127.0.0.1:8000/docs
"""

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api import recipes
from app.errors import install_error_handlers

app = FastAPI(
    title="Recipe Notebook API",
    version="0.2.0",
    description="Local backend of the recipe notebook. All endpoints live under /api. "
    "Milestone 2: recipes are the built-in samples; nothing is saved yet.",
    # "/api/recipes/" is a 404, not a redirect: a redirect would send the browser past the
    # Vite proxy to the backend's own address.
    redirect_slashes=False,
    redoc_url=None,  # one documentation page (/docs) is enough
)

# Answer only requests addressed to this computer by name. A web page that tricks the
# browser into sending requests here under another host name (DNS rebinding) gets a 400.
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
install_error_handlers(app)
app.include_router(recipes.router)


@app.get("/api/health", tags=["health"])
def health() -> dict[str, str]:
    """Lets the frontend (and you) check that the backend is running."""
    return {"status": "ok"}
