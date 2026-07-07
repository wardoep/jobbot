"""
Passwordless login, logout, and invite-based registration.

Login is a server-rendered three-step stepper (no password field on the web):
  1. email  — the visitor types their email and we email them a 6-digit code.
  2. code   — they type the code; if their account has SMS 2FA on we send a second
              code by text and show the SMS step, otherwise they're logged in.
  3. sms    — (only when enabled) they type the texted code to finish.
`login.html` renders one section based on the ``step`` context var ("email" |
"code" | "sms"); the email is carried between steps via a hidden field.

Registration is invite-only and also passwordless: the one-time invite link is the
proof of identity, so the new user just confirms their email (+ optional display
name) and we create the account. The ``password_hash`` column is NOT nullable, so
we store a random, unusable value there (the account can only be reached via the
emailed-code flow, never a password).

Security notes:
- Codes are bcrypt-hashed, expiry- and attempt-capped (see login_codes.py).
- The plaintext code is NEVER flashed, logged, or placed in the HTML here.
- request-code is anti-enumeration: it ALWAYS advances to the code step and never
  reveals whether an email has an account.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as SessionType

from app.alerts.email import send_email
from app.alerts.sms import send_sms
from app.models import Invite, LoginCode, User
from app.security import hash_password
from app.web.deps import add_flash, current_user, get_db, render
from app.web.login_codes import (
    CODE_TTL_MINUTES,
    issue_code,
    recently_issued,
    verify_code,
)
from app.web.ratelimit import (
    clear_failed_logins,
    login_blocked,
    minutes_until_unblocked,
    record_failed_login,
)

router = APIRouter()

# How many sign-in codes a single email may be SENT per rolling 24h. Caps the
# resend path so a real victim can never be email-bombed unboundedly, even from
# rotating IPs that each stay under the per-IP limiter.
MAX_CODES_PER_DAY = 10


# --- step 1: enter email ----------------------------------------------------
@router.get("/login")
def login_page(request: Request, mode: str = "signup", user=Depends(current_user)):
    if user:
        return RedirectResponse("/dashboard", status_code=303)
    # The card toggles between "sign up" (new — the default landing) and "log in".
    mode = "login" if mode == "login" else "signup"
    return render(request, "login.html", user=None, step="email", mode=mode)


@router.post("/login/request-code")
def login_request_code(
    request: Request,
    background: BackgroundTasks,
    email: str = Form(...),
    db: SessionType = Depends(get_db),
):
    # Brute-force guard at the IP level (says nothing about email existence).
    if login_blocked(request):
        mins = minutes_until_unblocked(request)
        add_flash(
            request,
            f"Too many attempts. Please wait about {mins} minute(s) and try again.",
            "error",
        )
        return render(
            request, "login.html", user=None, step="email", email=email,
            status_code=429,
        )

    # Every request-code attempt counts toward the IP limiter (not just verify
    # failures), so the limiter actually throttles this endpoint — closing both
    # the enumeration timing-probe loop and parallel email-bombing sweeps.
    record_failed_login(request)

    addr = email.strip().lower()
    # Anti-enumeration: ALWAYS advance to the code step, regardless of whether the
    # account exists. We only actually mint + email a code when the account exists,
    # we're past the resend cooldown, AND the email is under its daily cap — but the
    # response looks identical either way, so an attacker can't probe which emails
    # are registered.
    account = db.query(User).filter_by(email=addr).first() if addr else None
    # Per-email daily issuance cap: a single victim can never be mailed more than
    # MAX_CODES_PER_DAY codes in a rolling 24h, regardless of IP rotation.
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    sent_today = (
        db.query(LoginCode)
        .filter(
            LoginCode.email == addr,
            LoginCode.purpose == "login",
            LoginCode.created_at >= day_ago,
        )
        .count()
        if addr
        else 0
    )

    if (
        account is not None
        and sent_today < MAX_CODES_PER_DAY
        and not recently_issued(db, addr, "login")
    ):
        code = issue_code(db, addr, "login")
        # Schedule the (slow, 0.5-2s) SMTP send to run AFTER the response is sent,
        # so the wall-clock time of this endpoint never betrays that the account
        # exists. The response returns before SMTP is touched.
        background.add_task(
            send_email,
            account.email,
            "Your JobBot sign-in code",
            f"Your JobBot sign-in code is {code}.\n\n"
            f"It expires in {CODE_TTL_MINUTES} minutes. "
            "If you didn't request this, you can safely ignore this email.",
        )
    else:
        # Equalize the bcrypt cost: issue_code() hashes the code (~100ms), so the
        # no-op path does a throwaway hash too. Both branches now take ~constant
        # time, leaving no timing oracle for the existence of an account.
        hash_password(secrets.token_urlsafe(16))

    return render(request, "login.html", user=None, step="code", email=addr)


# --- step 2: enter the emailed code -----------------------------------------
@router.post("/login/verify-code")
def login_verify_code(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    db: SessionType = Depends(get_db),
):
    if login_blocked(request):
        mins = minutes_until_unblocked(request)
        add_flash(
            request,
            f"Too many attempts. Please wait about {mins} minute(s) and try again.",
            "error",
        )
        return render(
            request, "login.html", user=None, step="code", email=email,
            status_code=429,
        )

    addr = email.strip().lower()
    if verify_code(db, addr, "login", code):
        account = db.query(User).filter_by(email=addr).first()
        if account is None:
            # Code matched but the account is gone (deleted mid-flow) — fail safe.
            record_failed_login(request)
            add_flash(request, "That code didn't work. Please try again.", "error")
            return render(
                request, "login.html", user=None, step="code", email=addr,
                status_code=401,
            )

        # Optional second factor (dormant until a user opts in — Phase 6 UI).
        if account.sms_2fa_enabled and account.phone:
            sms_code = issue_code(db, addr, "sms")
            send_sms(
                account.phone,
                f"Your JobBot verification code is {sms_code}. "
                f"It expires in {CODE_TTL_MINUTES} minutes.",
            )
            request.session["pending_2fa_uid"] = account.id
            request.session["pending_2fa_at"] = datetime.now(timezone.utc).isoformat()
            return render(request, "login.html", user=None, step="sms", email=addr)

        # No second factor — log them in.
        clear_failed_logins(request)
        request.session["user_id"] = account.id
        add_flash(
            request,
            f"Welcome back, {account.display_name or account.email}.",
            "success",
        )
        return RedirectResponse("/dashboard", status_code=303)

    record_failed_login(request)
    add_flash(request, "That code is incorrect or expired. Please try again.", "error")
    return render(
        request, "login.html", user=None, step="code", email=addr, status_code=401
    )


# --- step 3: enter the texted code (only when SMS 2FA is enabled) ------------
@router.post("/login/verify-sms")
def login_verify_sms(
    request: Request,
    code: str = Form(...),
    db: SessionType = Depends(get_db),
):
    uid = request.session.get("pending_2fa_uid")
    started = request.session.get("pending_2fa_at")
    if not uid or not started:
        add_flash(request, "Your sign-in session expired. Please start again.", "error")
        return RedirectResponse("/login", status_code=303)

    # The pending-2FA window must be fresh (matches the code TTL).
    try:
        started_at = datetime.fromisoformat(started)
    except (TypeError, ValueError):
        started_at = None
    expired = (
        started_at is None
        or datetime.now(timezone.utc) - started_at > timedelta(minutes=CODE_TTL_MINUTES)
    )
    if expired:
        request.session.pop("pending_2fa_uid", None)
        request.session.pop("pending_2fa_at", None)
        add_flash(request, "Your sign-in session expired. Please start again.", "error")
        return RedirectResponse("/login", status_code=303)

    account = db.get(User, uid)
    if account is None:
        request.session.pop("pending_2fa_uid", None)
        request.session.pop("pending_2fa_at", None)
        add_flash(request, "Your sign-in session expired. Please start again.", "error")
        return RedirectResponse("/login", status_code=303)

    if login_blocked(request):
        mins = minutes_until_unblocked(request)
        add_flash(
            request,
            f"Too many attempts. Please wait about {mins} minute(s) and try again.",
            "error",
        )
        return render(
            request, "login.html", user=None, step="sms", email=account.email,
            status_code=429,
        )

    if verify_code(db, account.email, "sms", code):
        clear_failed_logins(request)
        request.session["user_id"] = account.id
        request.session.pop("pending_2fa_uid", None)
        request.session.pop("pending_2fa_at", None)
        add_flash(
            request,
            f"Welcome back, {account.display_name or account.email}.",
            "success",
        )
        return RedirectResponse("/dashboard", status_code=303)

    record_failed_login(request)
    add_flash(request, "That code is incorrect or expired. Please try again.", "error")
    return render(
        request, "login.html", user=None, step="sms", email=account.email,
        status_code=401,
    )


# --- public sign-up: create an account, proven by an emailed code -----------
# Same passwordless mechanism as login, but the account is created ONLY after the
# code is verified (so the email is proven) and the role is always "user".
@router.post("/signup/request-code")
def signup_request_code(
    request: Request,
    background: BackgroundTasks,
    email: str = Form(...),
    name: str = Form(""),
    db: SessionType = Depends(get_db),
):
    if login_blocked(request):
        mins = minutes_until_unblocked(request)
        add_flash(
            request,
            f"Too many attempts. Please wait about {mins} minute(s) and try again.",
            "error",
        )
        return render(request, "login.html", user=None, step="email", mode="signup",
                      email=email, status_code=429)

    # Every attempt counts toward the IP limiter, bounding mass/automated signups.
    record_failed_login(request)

    addr = email.strip().lower()
    if not addr:
        add_flash(request, "Enter your email to sign up.", "error")
        return render(request, "login.html", user=None, step="email", mode="signup",
                      email=email, status_code=400)

    # Already registered → there's nothing to create; send them to log in instead.
    if db.query(User).filter_by(email=addr).first():
        add_flash(request, "That email already has an account — please log in.", "info")
        return render(request, "login.html", user=None, step="email", mode="login",
                      email=addr)

    # Remember the (optional) name for when the code is verified; survive resends.
    if name.strip():
        request.session["signup_name"] = name.strip()
    request.session["signup_email"] = addr

    # Per-email daily cap + resend cooldown (mirrors login) to curb abuse/spam.
    day_ago = datetime.now(timezone.utc) - timedelta(days=1)
    sent_today = (
        db.query(LoginCode)
        .filter(LoginCode.email == addr, LoginCode.purpose == "signup",
                LoginCode.created_at >= day_ago)
        .count()
    )
    if sent_today < MAX_CODES_PER_DAY and not recently_issued(db, addr, "signup"):
        code = issue_code(db, addr, "signup")
        background.add_task(
            send_email, addr, "Confirm your JobBot sign-up",
            f"Welcome to JobBot! Your sign-up code is {code}.\n\n"
            f"It expires in {CODE_TTL_MINUTES} minutes. "
            "If you didn't request this, you can safely ignore this email.",
        )
    return render(request, "login.html", user=None, step="code", mode="signup", email=addr)


@router.post("/signup/verify-code")
def signup_verify_code(
    request: Request,
    email: str = Form(...),
    code: str = Form(...),
    db: SessionType = Depends(get_db),
):
    if login_blocked(request):
        mins = minutes_until_unblocked(request)
        add_flash(
            request,
            f"Too many attempts. Please wait about {mins} minute(s) and try again.",
            "error",
        )
        return render(request, "login.html", user=None, step="code", mode="signup",
                      email=email, status_code=429)

    addr = email.strip().lower()
    if verify_code(db, addr, "signup", code):
        account = db.query(User).filter_by(email=addr).first()
        if account is None:
            name = (request.session.get("signup_name") or "").strip() or None
            account = User(
                email=addr,
                password_hash=hash_password(secrets.token_urlsafe(32)),
                display_name=name,
                role="user",  # public signup can NEVER mint an admin
            )
            db.add(account)
            db.flush()
            db.commit()
        clear_failed_logins(request)
        request.session.pop("signup_name", None)
        request.session.pop("signup_email", None)
        request.session["user_id"] = account.id
        add_flash(request, "Welcome to JobBot — your account is ready!", "success")
        return RedirectResponse("/dashboard", status_code=303)

    record_failed_login(request)
    add_flash(request, "That code is incorrect or expired. Please try again.", "error")
    return render(request, "login.html", user=None, step="code", mode="signup",
                  email=addr, status_code=401)


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)


# --- passwordless, invite-only registration ---------------------------------
@router.get("/register")
def register_page(request: Request, token: str = "", db: SessionType = Depends(get_db)):
    invite = _valid_invite(db, token)
    if invite is None:
        return render(request, "register.html", user=None, token=token, invalid=True)
    return render(
        request, "register.html", user=None, token=token,
        invite_email=invite.email or "", invalid=False,
    )


@router.post("/register")
def register_submit(
    request: Request,
    token: str = Form(...),
    email: str = Form(...),
    display_name: str = Form(""),
    db: SessionType = Depends(get_db),
):
    invite = _valid_invite(db, token)
    if invite is None:
        add_flash(request, "That invite link is invalid or already used.", "error")
        return render(request, "register.html", user=None, token=token, invalid=True,
                      status_code=400)

    email = email.strip().lower()
    # If the invite was issued for a specific email, enforce it.
    if invite.email and invite.email.strip().lower() != email:
        add_flash(request, f"This invite is for {invite.email}.", "error")
        return render(request, "register.html", user=None, token=token,
                      invite_email=invite.email, invalid=False, status_code=400)
    if db.query(User).filter_by(email=email).first():
        add_flash(request, "An account with that email already exists.", "error")
        return render(request, "register.html", user=None, token=token,
                      invite_email=invite.email or email, invalid=False,
                      status_code=400)

    # Passwordless: the invite link was the proof of identity. We must still store
    # something in the NOT-NULL password_hash, so we use a random unusable secret —
    # the account is only ever reachable via the emailed-code login flow.
    account = User(
        email=email,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        display_name=display_name.strip() or None,
        role="user",
    )
    db.add(account)
    db.flush()  # get account.id
    invite.used_by_id = account.id
    invite.used_at = datetime.now(timezone.utc)
    db.commit()

    request.session["user_id"] = account.id
    add_flash(request, "Account created — welcome to JobBot!", "success")
    return RedirectResponse("/dashboard", status_code=303)


def _valid_invite(db: SessionType, token: str) -> Invite | None:
    if not token:
        return None
    invite = db.query(Invite).filter_by(token=token.strip()).first()
    if invite is None or invite.is_used:
        return None
    return invite
