"""
Shared web helpers: database access, "who is logged in", and page rendering.

Auth model: after login we store the user's id in a signed session cookie. Each
protected route depends on `require_user` (any logged-in user) or `require_admin`.
If the check fails we raise a small exception that an error handler turns into a
redirect (to /login or the dashboard) — see app/web/main.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session as SessionType

from app.db import Session
from app.models import User

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
STATIC_DIR = Path(__file__).resolve().parent / "static"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _domain_of(url: Optional[str]) -> str:
    """Bare host of a URL ('https://boards.greenhouse.io/x' -> 'boards.greenhouse.io'),
    used to show the source website's favicon when a company logo isn't found.
    Returns '' for blanks/garbage so the template just omits the fallback."""
    from urllib.parse import urlparse

    try:
        host = urlparse((url or "").strip()).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except (ValueError, AttributeError):
        return ""


templates.env.filters["domain_of"] = _domain_of


def asset_version() -> str:
    """Cache-buster for static assets: max mtime of the CSS files. Bumps the
    `?v=` on <link> tags whenever a stylesheet changes, so browsers and the
    Cloudflare edge fetch the new file instead of serving a stale cached copy."""
    try:
        files = ("style.css", "fonts.css")
        return str(int(max((STATIC_DIR / f).stat().st_mtime for f in files)))
    except OSError:
        return "1"


# --- exceptions that the app turns into redirects --------------------------
class NotAuthenticated(Exception):
    """Raised when a logged-out visitor hits a protected page."""


class NotAdmin(Exception):
    """Raised when a normal user hits an admin-only page."""


# --- database session per request ------------------------------------------
def get_db() -> SessionType:
    db = Session()
    try:
        yield db
    finally:
        db.close()


# --- current user ----------------------------------------------------------
def current_user(request: Request, db: SessionType = Depends(get_db)) -> Optional[User]:
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return db.get(User, user_id)


def require_user(user: Optional[User] = Depends(current_user)) -> User:
    if user is None:
        raise NotAuthenticated()
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != "admin":
        raise NotAdmin()
    return user


# --- flash messages (one-shot banners) -------------------------------------
def add_flash(request: Request, message: str, category: str = "info") -> None:
    request.session.setdefault("_flashes", []).append({"m": message, "c": category})


def _pop_flashes(request: Request) -> list[dict]:
    return request.session.pop("_flashes", [])


# --- render a template with the common context ----------------------------
def render(
    request: Request,
    template: str,
    user: Optional[User] = None,
    status_code: int = 200,
    **context,
) -> HTMLResponse:
    ctx = {
        "request": request,
        "user": user,
        "flashes": _pop_flashes(request),
        "theme": request.cookies.get("theme") or "dark",
        "asset_v": asset_version(),
        **context,
    }
    return templates.TemplateResponse(request, template, ctx, status_code=status_code)
