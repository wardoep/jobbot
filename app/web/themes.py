"""
Themes: the /themes gallery, the theme STUDIO (build-your-own looks), and the
generated per-user stylesheet.

How a custom theme works, end to end:
  - The studio stores ONLY six knobs per theme (accent/accent2/bg hex colors,
    display font key, background-animation style + strength) in `user_themes`.
  - Applying one sets the cookie to "custom:<id>". base.html then renders
    data-theme="custom" (which inherits the whole dark token block in
    style.css) plus a <link> to /themes/custom.css?id=<id>.
  - That route emits a tiny stylesheet that derives every other color from the
    knobs with CSS color-mix() — no color math in Python, and a knob tweak
    never needs a data migration.
  - Free accounts can open the studio and play with the live preview, but
    saving/applying is Premium (the enticement pattern used app-wide).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Request
from fastapi import Form
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session as SessionType

from app.models import User, UserTheme
from app.web.deps import (
    THEME_FONTS,
    THEMES,
    add_flash,
    get_db,
    is_premium,
    render,
    require_user,
)

router = APIRouter(prefix="/themes")

MAX_CUSTOM = 10
FX_STYLES = ("drift", "glow", "off")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# Opening the studio with no starting point begins from Aurora's knobs — a
# colorful base makes "drag a slider, see it move" land immediately.
_DEFAULT_BASE = "aurora"


def _preset_knobs(key: str) -> dict | None:
    for t in THEMES:
        if t["key"] == key:
            return dict(t.get("knobs") or {}) or None
    return None


def _clean_settings(accent: str, accent2: str, bg: str, font: str,
                    fx: str, fx_strength: str) -> dict | None:
    """Validate + normalize the studio knobs. None = something didn't parse
    (only possible by bypassing the form's own pickers, so the message can
    stay terse)."""
    accent, accent2, bg = accent.strip(), accent2.strip(), bg.strip()
    if not (_HEX.match(accent) and _HEX.match(accent2) and _HEX.match(bg)):
        return None
    if font not in THEME_FONTS or fx not in FX_STYLES:
        return None
    try:
        strength = min(3, max(1, int(fx_strength)))
    except (TypeError, ValueError):
        strength = 2
    return {"accent": accent.lower(), "accent2": accent2.lower(),
            "bg": bg.lower(), "font": font, "fx": fx, "fx_strength": strength}


# ------------------------------------------------------------- the gallery
@router.get("")
def themes_page(
    request: Request,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Preset gallery + the user's own studio themes. Everyone sees every
    preview (they're live and animated — that's the sales pitch); applying a
    Premium look is checked in /theme, saving in the studio POST."""
    mine = (db.query(UserTheme).filter_by(user_id=user.id)
            .order_by(UserTheme.updated_at.desc()).all())
    return render(request, "themes.html", user=user, themes=THEMES, mine=mine)


# ------------------------------------------------------------- the studio
@router.get("/studio")
def studio(
    request: Request,
    base: str = "",
    id: int = 0,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """The customization screen. ?base=<preset> starts from a built-in look
    ("edit a preset"); ?id=<n> reopens one of the user's saved themes; bare
    opens with a friendly default. Everything previews live in the browser."""
    theme_row = None
    name = ""
    knobs = None
    if id:
        theme_row = db.query(UserTheme).filter_by(id=id, user_id=user.id).first()
        if theme_row is None:
            add_flash(request, "That theme wasn't found.", "error")
            return RedirectResponse("/themes", status_code=303)
        name = theme_row.name
        knobs = dict(theme_row.settings or {})
    elif base:
        knobs = _preset_knobs(base)
        preset = next((t for t in THEMES if t["key"] == base), None)
        if preset is not None and knobs:
            name = f"My {preset['label']}"
    if not knobs:
        knobs = _preset_knobs(_DEFAULT_BASE)
    return render(
        request, "themes_studio.html", user=user,
        knobs=knobs, name=name, theme_id=theme_row.id if theme_row else 0,
        fonts=THEME_FONTS,
        presets=[t for t in THEMES if t.get("knobs")],
    )


@router.post("/studio")
def studio_save(
    request: Request,
    name: str = Form(""),
    accent: str = Form(""),
    accent2: str = Form(""),
    bg: str = Form(""),
    font: str = Form("inter"),
    fx: str = Form("drift"),
    fx_strength: str = Form("2"),
    theme_id: int = Form(0),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Create or update a custom theme, then apply it. Premium-only — free
    accounts play with the live preview but land on the buy screen here."""
    if not is_premium(user):
        add_flash(request, "Saving a custom theme is part of Premium.", "info")
        return RedirectResponse("/premium", status_code=303)

    settings_ = _clean_settings(accent, accent2, bg, font, fx, fx_strength)
    if settings_ is None:
        add_flash(request, "Those colors didn't parse — use the pickers.", "error")
        return RedirectResponse("/themes/studio", status_code=303)
    name = name.strip()[:60] or "My theme"

    if theme_id:
        row = db.query(UserTheme).filter_by(id=theme_id, user_id=user.id).first()
        if row is None:
            add_flash(request, "That theme wasn't found.", "error")
            return RedirectResponse("/themes", status_code=303)
        row.name, row.settings = name, settings_
        msg = f"“{name}” updated — and it's on."
    else:
        if db.query(UserTheme).filter_by(user_id=user.id).count() >= MAX_CUSTOM:
            add_flash(request, f"You've hit the limit of {MAX_CUSTOM} custom themes — "
                               "delete one to make room.", "error")
            return RedirectResponse("/themes", status_code=303)
        row = UserTheme(user_id=user.id, name=name, settings=settings_)
        db.add(row)
        msg = f"“{name}” saved — and it's on. ✦"
    db.commit()

    add_flash(request, msg, "success")
    response = RedirectResponse("/themes", status_code=303)
    response.set_cookie("theme", f"custom:{row.id}", max_age=31536000,
                        path="/", samesite="lax")
    return response


@router.post("/{theme_id}/delete")
def delete_theme(
    request: Request,
    theme_id: int,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    row = db.query(UserTheme).filter_by(id=theme_id, user_id=user.id).first()
    if row is None:
        add_flash(request, "That theme wasn't found.", "error")
        return RedirectResponse("/themes", status_code=303)
    db.delete(row)
    db.commit()
    add_flash(request, f"“{row.name}” deleted.", "success")
    response = RedirectResponse("/themes", status_code=303)
    if request.cookies.get("theme") == f"custom:{theme_id}":
        # it was the active look — fall back to the standard dark
        response.set_cookie("theme", "dark", max_age=31536000,
                            path="/", samesite="lax")
    return response


# ----------------------------------------------------- generated stylesheet
def _mix(a: str, pct: int, b: str, space: str = "oklab") -> str:
    return f"color-mix(in {space}, {a} {pct}%, {b})"


def _theme_css(row: UserTheme) -> str:
    """Derive the full token set from the six knobs. color-mix() keeps all the
    color math in the browser and always relative to the user's picks."""
    s = row.settings or {}
    accent = s.get("accent", "#6366f1")
    accent2 = s.get("accent2", "#22d3ee")
    bg = s.get("bg", "#0a1426")
    font = THEME_FONTS.get(s.get("font", "inter"), THEME_FONTS["inter"])
    fx = s.get("fx", "drift")
    strength = min(3, max(1, int(s.get("fx_strength", 2) or 2)))
    op = {1: 22, 2: 35, 3: 50}[strength]

    link = _mix(accent, 60, "white")
    info_bg = _mix(accent, 22, bg)
    info_bd = _mix(accent, 40, bg)
    lines = [
        ':root[data-theme="custom"] {',
        f"  --font-display:{font};",
        f"  --blue:{accent}; --navy:{accent}; --cyan:{accent2};",
        f"  --brand-d:{_mix(accent, 85, 'black')};",
        f"  --link:{link};",
        f"  --page:{bg};",
        f"  --surface:{_mix(bg, 94, 'white')};",
        f"  --inset:{_mix(bg, 97, 'white')};",
        f"  --track:{_mix(bg, 82, 'white')};",
        f"  --border:{_mix(bg, 82, 'white')}; --border-input:{_mix(bg, 82, 'white')};",
        f"  --info:{_mix(accent, 55, 'white')}; --info-bg:{info_bg}; --info-bd:{info_bd};",
        f"  --flash-info-bg:{info_bg}; --flash-info-fg:{_mix(accent, 55, 'white')}; --flash-info-bd:{info_bd};",
        f"  --ghost-bg:{_mix(accent, 20, 'transparent', 'srgb')};",
        f"  --ghost-fg:{_mix(accent, 55, 'white')};",
        f"  --focus:{_mix(accent, 28, 'transparent', 'srgb')};",
        f"  --sidebar:{_mix(bg, 96, 'black')};",
        f"  --sidebar-active:{_mix(accent, 20, 'transparent', 'srgb')};",
        f"  --sidebar-link:{link};",
        f"  --hero-glow:{_mix(accent, 45, 'transparent', 'srgb')};",
        f"  --hero-from:{_mix(bg, 86, accent)};",
        f"  --hero-to:{_mix(accent, 55, 'black')};",
        f"  --fx-c1:{_mix(accent, op, 'transparent', 'srgb')};",
        f"  --fx-c2:{_mix(accent2, op, 'transparent', 'srgb')};",
        f"  --fx-c3:{_mix(accent, max(12, op - 12), 'transparent', 'srgb')};",
        "}",
    ]
    if fx == "off":
        lines.append('[data-theme="custom"] .jb-fx { display:none; }')
    elif fx == "glow":
        lines.append('[data-theme="custom"] .jb-fx i { animation-name: jbbreathe; }')
    return "\n".join(lines) + "\n"


@router.get("/custom.css")
def custom_css(
    id: int = 0,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """The stylesheet for ONE of the requesting user's own themes. Foreign or
    deleted ids 404, which leaves the page on the plain dark base — that's the
    whole failure mode. no-store so studio edits show up instantly."""
    row = db.query(UserTheme).filter_by(id=id, user_id=user.id).first()
    if row is None or not is_premium(user):
        return Response(status_code=404)
    return Response(_theme_css(row), media_type="text/css",
                    headers={"Cache-Control": "no-store"})
