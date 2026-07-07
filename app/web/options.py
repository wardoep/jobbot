"""
The Options / account-settings page and its actions.

Everything here is for the *logged-in user's own* account: editing their display
name, switching the theme (handled by /theme in main.py), turning on SMS two-factor
authentication, and the danger-zone "delete my account".

SMS 2FA enrollment proves the user actually controls the phone number BEFORE we
trust it as a second factor: /2fa/start stashes the typed number in the session and
texts a 6-digit code (reusing the same short-lived, hashed, attempt-capped codes as
passwordless login, with purpose "sms"); /2fa/verify only writes user.phone and flips
sms_2fa_enabled on once the user types that code back correctly. The number is never
saved until it's been verified, so a typo or someone else's number can't lock anyone
out or enable 2FA on an address they don't own.
"""

from __future__ import annotations

import os
import secrets
import shutil

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response
from sqlalchemy.orm import Session as SessionType

from app.alerts.sms import send_sms
from app.config import PROJECT_ROOT
from app.models import Preference, User
from app.web.deps import add_flash, get_db, render, require_user
from app.web.login_codes import issue_code, recently_issued, verify_code
from app.web.ratelimit import record_sms_send, sms_send_blocked

router = APIRouter(prefix="/options")

# Session key holding the not-yet-verified phone number during 2FA enrollment.
ENROLL_KEY = "enroll_phone"

# --- Avatar upload/serving --------------------------------------------------
# Original bytes live privately under uploads/<user_id>/ (same place as resume
# originals); only the logged-in owner can fetch their own image via GET
# /options/avatar. We never mount this directory publicly.
UPLOAD_DIR = PROJECT_ROOT / "uploads"
AVATAR_MAX_BYTES = 2 * 1024 * 1024  # 2 MB

# Allowed image extensions -> (served Content-Type, magic-byte signature check).
# We verify the actual bytes, not just the extension/Content-Type header, and we
# deliberately do NOT accept SVG (it can carry script). No re-encoding is done, so
# the served Content-Type below is always an image type and we add nosniff so a
# browser can never treat the file as HTML.
AVATAR_TYPES = {
    ".png": ("image/png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    ".jpg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    ".jpeg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    ".webp": ("image/webp", lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP"),
    ".gif": ("image/gif", lambda b: b[:6] in (b"GIF87a", b"GIF89a")),
}


@router.get("")
def options_page(
    request: Request,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Render the settings page, with whatever 2FA enrollment step we're on."""
    from app.config import settings

    pending_phone = request.session.get(ENROLL_KEY)
    pref = db.get(Preference, user.id)
    email_alerts = bool(pref and pref.alert_channels and "email" in pref.alert_channels)
    # Telegram link flow: hand the template a ready deep-link. A link token is
    # minted lazily the first time an unconnected user views this page.
    tg_username = settings.telegram_bot_username.strip()
    tg_ready = bool(settings.telegram_bot_token.strip() and tg_username)
    if tg_ready and not user.telegram_chat_id and not user.telegram_link_token:
        import secrets

        user.telegram_link_token = secrets.token_hex(6)
        db.commit()
    return render(
        request,
        "options.html",
        user=user,
        sms_enabled=user.sms_2fa_enabled,
        phone=user.phone or "",
        pending_phone=pending_phone,
        awaiting_code=bool(pending_phone),
        email_alerts=email_alerts,
        tg_ready=tg_ready,
        tg_username=tg_username,
        tg_link=(
            f"https://t.me/{tg_username}?start={user.telegram_link_token}"
            if tg_ready and user.telegram_link_token else ""
        ),
    )


@router.post("/notifications")
def update_notifications(
    request: Request,
    email_alerts: str = Form(""),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Turn email job-alerts on/off (off by default). Only flips the 'email'
    channel; dashboard/slack stay as configured on the Preferences page. Login
    codes are transactional and unaffected by this."""
    pref = db.get(Preference, user.id)
    if pref is None:
        pref = Preference(user_id=user.id)
        db.add(pref)
    channels = [c for c in (pref.alert_channels or []) if c != "email"]
    want_email = email_alerts.strip().lower() == "on"
    if want_email:
        channels.append("email")
    pref.alert_channels = channels or None
    db.commit()
    add_flash(request, "Email alerts turned " + ("on." if want_email else "off."), "success")
    return RedirectResponse("/options", status_code=303)


@router.post("/telegram/verify")
def telegram_verify(
    request: Request,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Finish the Telegram link: find the user's '/start <token>' message in
    the bot's recent updates and store their private chat id."""
    from app.alerts.telegram import get_updates

    token = (user.telegram_link_token or "").strip()
    if not token:
        add_flash(request, "Open Options again to start the Telegram link.", "error")
        return RedirectResponse("/options", status_code=303)

    chat_id = None
    for u in get_updates():
        msg = u.get("message") or u.get("edited_message") or {}
        text = (msg.get("text") or "").strip()
        if text == f"/start {token}" and msg.get("chat", {}).get("id"):
            chat_id = str(msg["chat"]["id"])
    if chat_id is None:
        add_flash(
            request,
            "Didn't see your message yet — tap the link, press Start in "
            "Telegram, then try Verify again.",
            "error",
        )
        return RedirectResponse("/options", status_code=303)

    user.telegram_chat_id = chat_id
    user.telegram_link_token = None
    db.commit()
    # Confirm in the chat itself so the user sees it worked end-to-end.
    from app.alerts.telegram import send_telegram

    send_telegram(chat_id, "✅ Connected! JobBot will send your job alerts here.")
    add_flash(request, "Telegram connected — alerts can now reach you there.", "success")
    return RedirectResponse("/options", status_code=303)


@router.post("/telegram/disconnect")
def telegram_disconnect(
    request: Request,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    user.telegram_chat_id = None
    user.telegram_link_token = None
    db.commit()
    add_flash(request, "Telegram disconnected.", "success")
    return RedirectResponse("/options", status_code=303)


@router.post("/profile")
def update_profile(
    request: Request,
    display_name: str = Form(""),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Save the user's friendly display name (blank clears it)."""
    user.display_name = display_name.strip() or None
    db.commit()
    add_flash(request, "Profile updated.", "success")
    return RedirectResponse("/options", status_code=303)


@router.get("/avatar")
def get_avatar(user: User = Depends(require_user)):
    """Serve the logged-in user's OWN avatar image (never anyone else's).

    Auth-gated so uploads stay private; the stored name is one we generated, but
    we still resolve it and confirm it sits inside the user's own upload dir
    before serving, so a tampered value can't escape the directory.
    """
    if not user.avatar_filename:
        return Response(status_code=404)
    base = (UPLOAD_DIR / str(user.id)).resolve()
    path = (base / user.avatar_filename).resolve()
    if base not in path.parents or not path.is_file():
        return Response(status_code=404)
    ctype = AVATAR_TYPES.get(path.suffix.lower(), ("application/octet-stream", None))[0]
    return FileResponse(
        path,
        media_type=ctype,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=300",
        },
    )


@router.post("/avatar")
async def upload_avatar(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Upload or replace the user's profile picture. Validates extension, real
    image signature and size before storing; the previous file is removed."""
    ext = os.path.splitext((file.filename or "").lower())[1]
    if ext not in AVATAR_TYPES:
        add_flash(request, "Please choose a PNG, JPG, GIF or WebP image.", "error")
        return RedirectResponse("/options", status_code=303)

    # Reject on the reported size first, so an oversized upload isn't read fully
    # into memory; the post-read length check below is the authoritative backstop.
    if file.size is not None and file.size > AVATAR_MAX_BYTES:
        add_flash(request, "That image is larger than 2 MB. Please pick a smaller one.", "error")
        return RedirectResponse("/options", status_code=303)

    data = await file.read()
    if not data:
        add_flash(request, "That file was empty.", "error")
        return RedirectResponse("/options", status_code=303)
    if len(data) > AVATAR_MAX_BYTES:
        add_flash(request, "That image is larger than 2 MB. Please pick a smaller one.", "error")
        return RedirectResponse("/options", status_code=303)

    _ctype, is_valid = AVATAR_TYPES[ext]
    if not is_valid(data):
        add_flash(request, "That file doesn't look like a real image.", "error")
        return RedirectResponse("/options", status_code=303)

    # Random token = unguessable name AND a changing URL so the browser fetches the
    # new picture instead of a cached one. Normalise .jpeg -> .jpg for tidiness.
    stored_ext = ".jpg" if ext == ".jpeg" else ext
    new_name = f"avatar_{secrets.token_hex(8)}{stored_ext}"
    user_dir = UPLOAD_DIR / str(user.id)
    try:
        user_dir.mkdir(parents=True, exist_ok=True)
        (user_dir / new_name).write_bytes(data)
    except OSError:
        add_flash(request, "Sorry — we couldn't save that image. Please try again.", "error")
        return RedirectResponse("/options", status_code=303)

    old = user.avatar_filename
    user.avatar_filename = new_name
    db.commit()
    if old and old != new_name:
        try:
            (user_dir / old).unlink()
        except OSError:
            pass  # best-effort cleanup; the DB now points at the new file

    add_flash(request, "Profile picture updated.", "success")
    return RedirectResponse("/options", status_code=303)


@router.post("/avatar/remove")
def remove_avatar(
    request: Request,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Remove the user's profile picture (revert to the initials fallback)."""
    old = user.avatar_filename
    user.avatar_filename = None
    db.commit()
    if old:
        try:
            (UPLOAD_DIR / str(user.id) / old).unlink()
        except OSError:
            pass
    add_flash(request, "Profile picture removed.", "success")
    return RedirectResponse("/options", status_code=303)


@router.post("/2fa/start")
def start_2fa(
    request: Request,
    phone: str = Form(""),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Begin SMS-2FA enrollment: stash the phone and text a verification code."""
    phone = phone.strip()
    if not phone:
        add_flash(request, "Enter a phone number first.", "error")
        return RedirectResponse("/options", status_code=303)

    # Resend cooldown: one code per (email, "sms") every RESEND_COOLDOWN_SECONDS,
    # mirroring the login flow's guard so this endpoint can't be looped.
    if recently_issued(db, user.email, "sms"):
        add_flash(
            request,
            "We just sent a code — please wait a moment before requesting another.",
            "error",
        )
        return RedirectResponse("/options", status_code=303)

    # Hard per-IP cap on verification-SMS sends. The recipient number is supplied
    # by the user, so without this an authenticated account could spray texts at
    # any victim number / run up a Twilio bill. This also bounds the unvalidated-
    # recipient risk to a handful of messages per hour.
    if sms_send_blocked(request):
        add_flash(
            request,
            "Too many verification texts requested. Please try again later.",
            "error",
        )
        return RedirectResponse("/options", status_code=303)

    # Hold the number aside until it's verified — we don't trust it yet.
    request.session[ENROLL_KEY] = phone
    code = issue_code(db, user.email, "sms")
    record_sms_send(request)
    send_sms(
        phone,
        f"Your JobBot verification code is {code}. It expires in 10 minutes.",
    )
    add_flash(request, f"We sent a code to {phone}.", "info")
    return RedirectResponse("/options", status_code=303)


@router.post("/2fa/verify")
def verify_2fa(
    request: Request,
    code: str = Form(""),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Finish enrollment: only on a correct code do we trust + store the phone."""
    pending = request.session.get(ENROLL_KEY)
    if not pending:
        add_flash(request, "Start two-factor setup first.", "error")
        return RedirectResponse("/options", status_code=303)

    if verify_code(db, user.email, "sms", code):
        # Proven ownership of the number — safe to enable 2FA against it now.
        user.phone = pending
        user.sms_2fa_enabled = True
        request.session.pop(ENROLL_KEY, None)
        db.commit()
        add_flash(request, "Two-factor is on.", "success")
    else:
        add_flash(request, "That code didn't match. Try again.", "error")
    return RedirectResponse("/options", status_code=303)


@router.post("/2fa/disable")
def disable_2fa(
    request: Request,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Turn off the SMS second factor (the stored phone is left in place, harmless)."""
    user.sms_2fa_enabled = False
    db.commit()
    add_flash(request, "Two-factor turned off.", "success")
    return RedirectResponse("/options", status_code=303)


@router.post("/2fa/cancel")
def cancel_2fa(request: Request, user: User = Depends(require_user)):
    """Abandon an in-progress enrollment (drop the unverified phone)."""
    request.session.pop(ENROLL_KEY, None)
    return RedirectResponse("/options", status_code=303)


@router.post("/delete-account")
def delete_account(
    request: Request,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Permanently delete the logged-in user's own row (cascades to their data)."""
    # require_user only ever returns the session's own user, so this can only
    # ever delete the caller's account — never anyone else's.
    uid = user.id
    db.delete(user)
    db.commit()
    request.session.clear()
    # The DB cascade only removes rows; also delete this user's private uploads
    # (avatar + resume originals) from disk so "permanently remove your data" is
    # true on disk too. Best-effort — a filesystem hiccup must not 500 the delete.
    shutil.rmtree(UPLOAD_DIR / str(uid), ignore_errors=True)
    add_flash(request, "Your account has been deleted.", "info")
    return RedirectResponse("/", status_code=303)
