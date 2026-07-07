"""
The FastAPI application object: middleware, routers, and friendly error pages.

Run it with:
    uvicorn app.web.main:app --reload
(or `python manage.py serve`, which does the same thing.)
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Query, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.web.deps import (
    NotAdmin,
    NotAuthenticated,
    TEMPLATES_DIR,
    add_flash,
    render,
)
from app.web import admin, assist, auth, dashboard, kit, options, preferences, resumes

logger = logging.getLogger("jobbot.web")

app = FastAPI(title="JobBot")

# Signed-cookie sessions. SECRET_KEY must be set in production; we warn if not.
_secret = settings.secret_key or "dev-insecure-change-me"
if not settings.secret_key:
    logger.warning("SECRET_KEY is blank — using an insecure dev key. Set it in .env.")
# https_only marks the session cookie "Secure" so the browser only ever sends it
# over HTTPS (the public site is HTTPS via Cloudflare). Trade-off: the login cookie
# won't work over a plain http://localhost tunnel anymore — use https://jobbot.example.com.
app.add_middleware(
    SessionMiddleware, secret_key=_secret, same_site="lax", https_only=True
)

# Static files (CSS).
app.mount(
    "/static",
    StaticFiles(directory=str(TEMPLATES_DIR.parent / "static")),
    name="static",
)

# Routers.
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(resumes.router)
app.include_router(preferences.router)
app.include_router(admin.router)
app.include_router(assist.router)
app.include_router(kit.router)
app.include_router(options.router)


@app.get("/")
def root(request: Request):
    # Logged-in visitors go straight to their dashboard; everyone else sees the
    # logged-out splash (the splash's CTA links to /login).
    if request.session.get("user_id"):
        return RedirectResponse("/dashboard", status_code=303)
    return render(request, "splash.html", user=None)


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/theme")
def set_theme(request: Request, value: str | None = Query(default=None, alias="set")):
    """Persist the light/dark preference in a cookie, then bounce back."""
    current = request.cookies.get("theme") or "dark"
    if value in ("light", "dark"):
        theme = value
    else:
        theme = "light" if current == "dark" else "dark"
    response = RedirectResponse(
        request.headers.get("referer") or "/dashboard", status_code=303
    )
    response.set_cookie(
        "theme", theme, max_age=31536000, path="/", samesite="lax"
    )
    return response


# --- turn auth failures into friendly redirects ----------------------------
@app.exception_handler(NotAuthenticated)
async def _not_authenticated(request: Request, exc: NotAuthenticated):
    add_flash(request, "Please log in to continue.", "info")
    return RedirectResponse("/login", status_code=303)


@app.exception_handler(NotAdmin)
async def _not_admin(request: Request, exc: NotAdmin):
    add_flash(request, "That page is for admins only.", "error")
    return RedirectResponse("/dashboard", status_code=303)
