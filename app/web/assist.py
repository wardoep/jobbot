"""
Phase 6 — the per-job assistant: tailor your resume/cover letter to a job and
draft answers to its application questions (OpenAI under the hood, via app/llm).

Access is scoped to jobs the user can actually see: they must have a match or a
star for the job. Everything here is a DRAFT helper — tailoring suggestions are
shown editable and never written back to the stored resume; drafted answers are
saved as ApplicationAnswer rows the user can freely edit or delete.
"""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as SessionType

from app.assist import draft_answer, tailor_application
from app.config import settings
from app.llm import LLMError
from app.models import ApplicationAnswer, Job, Match, Preference, Resume, Star, User
from app.web.deps import add_flash, get_db, render, require_user

router = APIRouter()


def _job_for_user(db: SessionType, user: User, job_id: int) -> Optional[Job]:
    """Return the job only if this user has a match or star for it (else None)."""
    job = db.get(Job, job_id)
    if job is None:
        return None
    seen = (
        db.query(Match.id).filter_by(user_id=user.id, job_id=job_id).first()
        or db.query(Star.id).filter_by(user_id=user.id, job_id=job_id).first()
    )
    return job if seen else None


def _resume_text(db: SessionType, user: User) -> str:
    rows = db.query(Resume).filter_by(user_id=user.id, kind="resume").all()
    return "\n".join(r.raw_text for r in rows if r.raw_text).strip()


def _cover_text(db: SessionType, user: User) -> str:
    rows = db.query(Resume).filter_by(user_id=user.id, kind="cover_letter").all()
    return "\n".join(r.raw_text for r in rows if r.raw_text).strip()


def _mentions(haystack_lc: str, term_lc: str) -> bool:
    """Whole-word/phrase, case-insensitive match (both args already lowercased).

    Uses non-word lookarounds instead of substring `in` so short keywords don't
    false-match (e.g. "go" must not match inside "category"). Tolerates terms
    ending/starting with symbols like "c++"/".net" where ``\\b`` would fail.
    """
    if not term_lc:
        return False
    return re.search(r"(?<!\w)" + re.escape(term_lc) + r"(?!\w)", haystack_lc) is not None


def match_breakdown(resume_text, keywords, job: Job, cap: int = 12) -> dict:
    """Real have/missing keyword overlap for the job page's "How you match" panel.

    For each non-empty preference keyword we check, case-insensitively, whether it
    appears in the job (title + description) and in the user's resume text:
      - present in BOTH the job and the resume -> "have"
      - present in the job but NOT the resume  -> "missing"
      - not present in the job at all          -> skipped
    Order is preserved, duplicates are dropped, and each list is capped at ``cap``.
    Returns ``{"have": [...], "missing": [...]}`` (both empty when there's nothing
    to show, e.g. no keywords set).
    """
    have: list[str] = []
    missing: list[str] = []
    if not keywords:
        return {"have": have, "missing": missing}

    job_text = f"{job.title or ''} {job.description or ''}".lower()
    resume_lc = (resume_text or "").lower()
    seen: set[str] = set()
    for kw in keywords:
        if not isinstance(kw, str):
            continue
        term = kw.strip()
        if not term:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        if not _mentions(job_text, key):  # keyword the job doesn't mention -> skip
            continue
        if _mentions(resume_lc, key):
            if len(have) < cap:
                have.append(term)
        elif len(missing) < cap:
            missing.append(term)
    return {"have": have, "missing": missing}


@router.get("/jobs/{job_id}")
def job_detail(
    request: Request,
    job_id: int,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    job = _job_for_user(db, user, job_id)
    if job is None:
        add_flash(request, "That job isn't in your matches.", "error")
        return RedirectResponse("/dashboard", status_code=303)

    match = db.query(Match).filter_by(user_id=user.id, job_id=job_id).first()
    starred = (
        db.query(Star.id).filter_by(user_id=user.id, job_id=job_id).first() is not None
    )
    answers = (
        db.query(ApplicationAnswer)
        .filter_by(user_id=user.id, job_id=job_id)
        .order_by(ApplicationAnswer.updated_at.desc())
        .all()
    )
    # ADDITIVE (Phase 4): real have/missing keyword overlap for "How you match".
    resume_text = _resume_text(db, user)
    pref = db.get(Preference, user.id)
    breakdown = match_breakdown(resume_text, pref.keywords if pref else None, job)
    # Application kit (if one was generated for this job) — renders inline.
    from app.models import ApplicationKit

    kit_row = (
        db.query(ApplicationKit).filter_by(user_id=user.id, job_id=job_id).first()
    )
    return render(
        request, "job_detail.html", user=user, job=job, match=match,
        starred=starred, answers=answers,
        has_resume=bool(resume_text),
        llm_ready=settings.llm_configured, model=settings.openai_model,
        breakdown=breakdown,
        kit=(kit_row.content if kit_row else None), kit_row=kit_row,
    )


@router.post("/jobs/{job_id}/tailor")
def tailor(
    request: Request,
    job_id: int,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """HTMX endpoint: return the tailoring suggestions as a fragment."""
    job = _job_for_user(db, user, job_id)
    if job is None:
        return render(request, "_tailoring.html", user=user,
                      error="That job isn't in your matches.")
    try:
        suggestions = tailor_application(
            _resume_text(db, user), _cover_text(db, user), job
        )
    except LLMError as exc:
        return render(request, "_tailoring.html", user=user, error=str(exc))
    return render(request, "_tailoring.html", user=user, s=suggestions)


@router.post("/jobs/{job_id}/answers")
def create_answer(
    request: Request,
    job_id: int,
    question: str = Form(""),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    job = _job_for_user(db, user, job_id)
    if job is None:
        add_flash(request, "That job isn't in your matches.", "error")
        return RedirectResponse("/dashboard", status_code=303)
    try:
        draft = draft_answer(_resume_text(db, user), job, question)
    except LLMError as exc:
        add_flash(request, str(exc), "error")
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)

    db.add(ApplicationAnswer(
        user_id=user.id, job_id=job_id, question=question.strip(),
        draft_answer=draft, final_answer=draft,
    ))
    db.commit()
    add_flash(request, "Drafted an answer — edit it below and save.", "success")
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


@router.post("/answers/{answer_id}")
def save_answer(
    request: Request,
    answer_id: int,
    final_answer: str = Form(""),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    ans = db.query(ApplicationAnswer).filter_by(id=answer_id, user_id=user.id).first()
    if ans is None:
        add_flash(request, "That answer doesn't exist.", "error")
        return RedirectResponse("/dashboard", status_code=303)
    ans.final_answer = final_answer
    db.commit()
    add_flash(request, "Saved your edited answer.", "success")
    return RedirectResponse(f"/jobs/{ans.job_id}", status_code=303)


@router.post("/answers/{answer_id}/delete")
def delete_answer(
    request: Request,
    answer_id: int,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    ans = db.query(ApplicationAnswer).filter_by(id=answer_id, user_id=user.id).first()
    if ans is None:
        add_flash(request, "That answer doesn't exist.", "error")
        return RedirectResponse("/dashboard", status_code=303)
    job_id = ans.job_id
    db.delete(ans)
    db.commit()
    add_flash(request, "Answer deleted.", "success")
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)
