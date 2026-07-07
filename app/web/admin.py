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
