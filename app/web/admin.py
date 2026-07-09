"""
Admin-only pages: invite new users and see who's been invited.

Creating an invite makes a one-time token. The admin copies the resulting
/register?token=... link and sends it to the person out-of-band (email, chat).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as SessionType

from app.models import Invite, User
from app.web.deps import add_flash, get_db, render, require_admin

router = APIRouter(prefix="/admin")


@router.get("")
def admin_home(
    request: Request,
    admin: User = Depends(require_admin),
    db: SessionType = Depends(get_db),
):
    invites = db.query(Invite).order_by(Invite.created_at.desc()).all()
    users = db.query(User).order_by(User.created_at.desc()).all()
    base = str(request.base_url).rstrip("/")

    # This month's metered API usage (JSearch job searches + AI match scoring),
    # so the admin can watch the free-tier quotas at a glance.
    from app.config import settings
    from app.llm_budget import month_usage
    from app.source_budget import usage as source_usage

    js_used = source_usage(db, "jsearch")
    js_cap = settings.jsearch_monthly_cap
    llm_used, llm_cap = month_usage(db)
    meters = [
        {
            "name": "JSearch job searches",
            "sub": "LinkedIn · Indeed · Glassdoor · ZipRecruiter",
            "used": js_used, "cap": js_cap,
            "pct": round(js_used / js_cap * 100) if js_cap else 0,
        },
        {
            "name": "AI scoring & grading",
            "sub": "OpenAI calls that score job fit and grade resumes",
            "used": llm_used, "cap": llm_cap,
            "pct": round(llm_used / llm_cap * 100) if llm_cap else 0,
        },
    ]
    return render(
        request, "admin.html", user=admin,
        invites=invites, users=users, base_url=base, meters=meters,
    )


@router.post("/plan/{user_id}")
def toggle_plan(
    request: Request,
    user_id: int,
    admin: User = Depends(require_admin),
    db: SessionType = Depends(get_db),
):
    """Flip an account between free and premium. While tiers are in testing
    there's no billing — an admin grant is a comp with no expiry. A future
    payment system will set plan/premium_until itself on purchase."""
    target = db.get(User, user_id)
    if target is None:
        add_flash(request, "That account doesn't exist.", "error")
        return RedirectResponse("/admin", status_code=303)
    if target.plan == "premium":
        target.plan = "free"
        target.premium_until = None
        msg = f"{target.email} is now on the free plan."
    else:
        target.plan = "premium"
        target.premium_until = None  # comped: no expiry until billing exists
        msg = f"{target.email} now has Premium. ✦"
    db.commit()
    add_flash(request, msg, "success")
    return RedirectResponse("/admin#accounts", status_code=303)


@router.post("/role/{user_id}")
def toggle_role(
    request: Request,
    user_id: int,
    admin: User = Depends(require_admin),
    db: SessionType = Depends(get_db),
):
    """Promote a user to admin or demote an admin back to user. Two guards
    keep the site administrable: you can't change your own role, and the last
    remaining admin can't be demoted."""
    target = db.get(User, user_id)
    if target is None:
        add_flash(request, "That account doesn't exist.", "error")
        return RedirectResponse("/admin", status_code=303)
    if target.id == admin.id:
        add_flash(request, "You can't change your own role.", "error")
        return RedirectResponse("/admin#accounts", status_code=303)
    if target.role == "admin":
        admins = db.query(User).filter_by(role="admin").count()
        if admins <= 1:
            add_flash(request, "There must always be at least one admin.", "error")
            return RedirectResponse("/admin#accounts", status_code=303)
        target.role = "user"
        msg = f"{target.email} is no longer an admin."
    else:
        target.role = "admin"
        msg = f"{target.email} is now an admin."
    db.commit()
    add_flash(request, msg, "success")
    return RedirectResponse("/admin#accounts", status_code=303)


@router.post("/invite")
def create_invite(
    request: Request,
    email: str = Form(""),
    admin: User = Depends(require_admin),
    db: SessionType = Depends(get_db),
):
    token = secrets.token_urlsafe(24)
    invite = Invite(
        token=token,
        email=(email.strip().lower() or None),
        created_by_id=admin.id,
    )
    db.add(invite)
    db.commit()
    add_flash(request, "Invite created — copy the link below and send it.", "success")
    return RedirectResponse("/admin", status_code=303)
