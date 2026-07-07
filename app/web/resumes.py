"""
Upload, list, and delete resumes and cover letters.

On upload we extract plain text (for matching) and also keep the original file on
disk under uploads/<user_id>/ (private, git-ignored). Users only ever see their own
documents — every query is scoped to the logged-in user's id.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session as SessionType

from app.assist import parse_resume, reformat_resume
from app.config import PROJECT_ROOT, settings
from app.llm import LLMError
from app.models import Resume, User
from app.resume_parse import SUPPORTED_EXTENSIONS, extract_text
from app.web.deps import add_flash, get_db, render, require_user

logger = logging.getLogger("jobbot.web.resumes")

router = APIRouter(prefix="/resumes")

UPLOAD_DIR = PROJECT_ROOT / "uploads"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB is plenty for a resume


def _parse_resume_bg(doc_id: int) -> None:
    """Background task: parse a freshly-uploaded resume into `parsed_json`,
    then GRADE it into `grade_json` (the Resume-score card).

    Runs AFTER the upload response so the user isn't blocked on the model
    calls. Best-effort: a failure just leaves the column NULL. Only resumes
    (not cover letters) are parsed/graded. Grading counts against the monthly
    AI budget so public signups can't run up the bill.
    """
    from app.db import Session

    session = Session()
    try:
        doc = session.get(Resume, doc_id)
        if doc is None or doc.kind != "resume" or not (doc.raw_text or "").strip():
            return
        try:
            doc.parsed_json = parse_resume(doc.raw_text)
            session.commit()
            logger.info("parsed resume %s into parsed_json", doc_id)
        except LLMError as exc:
            logger.warning("resume %s parse failed: %s", doc_id, exc)
        _grade_doc(session, doc)
    finally:
        session.close()


def _grade_doc(session, doc: Resume) -> bool:
    """Grade one resume into grade_json (budget-capped, best-effort)."""
    from app.assist import grade_resume
    from app.llm_budget import try_spend

    if not (doc.raw_text or "").strip():
        return False
    if not try_spend(session, 1):
        logger.warning("resume %s not graded — monthly AI budget exhausted", doc.id)
        return False
    try:
        roles = (doc.parsed_json or {}).get("target_roles") or []
        doc.grade_json = grade_resume(doc.raw_text, roles)
        session.commit()
        logger.info("graded resume %s: %s/100", doc.id, doc.grade_json.get("overall"))
        return True
    except LLMError as exc:
        logger.warning("resume %s grade failed: %s", doc.id, exc)
        return False


def _grade_resume_bg(doc_id: int) -> None:
    """Background task: (re)grade an existing resume on demand."""
    from app.db import Session

    session = Session()
    try:
        doc = session.get(Resume, doc_id)
        if doc is not None and doc.kind == "resume":
            _grade_doc(session, doc)
    finally:
        session.close()

# The resume-builder templates: a key (posted by the radio), a label and a tiny
# style blurb. The key also drives the "paper" styling in _resume_paper.html.
BUILDER_TEMPLATES = [
    {"key": "modern", "label": "Modern", "blurb": "Accent header · single column"},
    {"key": "classic", "label": "Classic", "blurb": "ATS-safe · clean lines"},
    {"key": "twocol", "label": "Two-column", "blurb": "Sidebar + main"},
    {"key": "minimal", "label": "Minimal", "blurb": "Lots of whitespace"},
]
_BUILDER_KEYS = {t["key"] for t in BUILDER_TEMPLATES}


@router.get("")
def resumes_page(
    request: Request,
    score: int = 0,  # ?score=<doc id> switches which resume's grade shows
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    docs = (
        db.query(Resume).filter_by(user_id=user.id)
        .order_by(Resume.uploaded_at.desc()).all()
    )
    # "What the AI sees" panel: the newest resume + what the parser extracted
    # from it (parsed_json fills in a few seconds after upload, in the
    # background — the template shows a "still reading" note until then).
    ai_doc = next((d for d in docs if d.kind == "resume"), None)

    # Resume-score card: pick the resume whose grade to show (tab pills switch
    # via ?score=<id>); quick_wins = points on the table from non-"good" fixes.
    resumes_only = [d for d in docs if d.kind == "resume"]
    score_doc = next((d for d in resumes_only if d.id == score), None) or ai_doc
    grade = score_doc.grade_json if score_doc else None
    quick_wins = sum(
        s.get("points") or 0
        for s in (grade or {}).get("suggestions", [])
        if s.get("priority") != "good"
    )
    return render(request, "resumes.html", user=user, docs=docs,
                  ai_doc=ai_doc, ai_parsed=(ai_doc.parsed_json if ai_doc else None),
                  score_docs=resumes_only, score_doc=score_doc,
                  grade=grade, quick_wins=quick_wins,
                  supported=", ".join(SUPPORTED_EXTENSIONS))


@router.post("/upload")
async def upload(
    request: Request,
    background: BackgroundTasks,
    kind: str = Form(...),  # "resume" or "cover_letter"
    file: UploadFile = File(...),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    if kind not in ("resume", "cover_letter"):
        add_flash(request, "Pick whether this is a resume or a cover letter.", "error")
        return RedirectResponse("/resumes", status_code=303)

    filename = file.filename or "upload"
    if not filename.lower().endswith(SUPPORTED_EXTENSIONS):
        add_flash(request, f"Unsupported file type. Allowed: "
                           f"{', '.join(SUPPORTED_EXTENSIONS)}", "error")
        return RedirectResponse("/resumes", status_code=303)

    data = await file.read()
    if len(data) > MAX_BYTES:
        add_flash(request, "That file is larger than 5 MB.", "error")
        return RedirectResponse("/resumes", status_code=303)

    text = extract_text(filename, data)
    if not text.strip():
        add_flash(
            request,
            "We couldn't read any text from that file. If it's a scanned PDF, try "
            "a text-based PDF or a .docx/.txt export.",
            "error",
        )
        return RedirectResponse("/resumes", status_code=303)

    doc = Resume(user_id=user.id, kind=kind, filename=filename, raw_text=text)
    db.add(doc)
    db.flush()  # get doc.id for the saved-file name

    # Keep the original file privately (best effort; the text is what matching uses).
    try:
        user_dir = UPLOAD_DIR / str(user.id)
        user_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", filename)
        (user_dir / f"{doc.id}_{safe}").write_bytes(data)
    except OSError:
        pass  # the DB copy of the text is the source of truth

    db.commit()

    # Parse the resume into a structured profile (parsed_json) after responding,
    # so the upload itself stays fast. Resumes only; needs the LLM configured.
    if kind == "resume" and settings.llm_configured:
        background.add_task(_parse_resume_bg, doc.id)

    words = len(text.split())
    add_flash(request, f"Uploaded {filename} ({words} words extracted).", "success")
    return RedirectResponse("/resumes", status_code=303)


@router.post("/{doc_id}/grade")
def grade_doc_route(
    request: Request,
    doc_id: int,
    background: BackgroundTasks,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Kick off (re)grading for one of the user's resumes, in the background."""
    doc = db.query(Resume).filter_by(id=doc_id, user_id=user.id, kind="resume").first()
    if doc is None:
        add_flash(request, "That resume wasn't found.", "error")
        return RedirectResponse("/resumes", status_code=303)
    background.add_task(_grade_resume_bg, doc.id)
    add_flash(request, "Grading your resume — this takes a few seconds. Refresh to see the score.", "success")
    return RedirectResponse(f"/resumes?score={doc.id}", status_code=303)


@router.post("/{doc_id}/delete")
def delete_doc(
    request: Request,
    doc_id: int,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    doc = db.query(Resume).filter_by(id=doc_id, user_id=user.id).first()
    if doc is None:
        add_flash(request, "That document doesn't exist.", "error")
        return RedirectResponse("/resumes", status_code=303)
    # remove any stored original files for this doc
    try:
        for f in (UPLOAD_DIR / str(user.id)).glob(f"{doc.id}_*"):
            f.unlink()
    except OSError:
        pass
    db.delete(doc)
    db.commit()
    add_flash(request, "Document deleted.", "success")
    return RedirectResponse("/resumes", status_code=303)


def _resume_text(db: SessionType, user: User) -> str:
    """All of the user's resume (kind='resume') text, joined non-empty."""
    rows = db.query(Resume).filter_by(user_id=user.id, kind="resume").all()
    return "\n".join(r.raw_text for r in rows if r.raw_text).strip()


@router.get("/builder")
def builder_page(
    request: Request,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """The resume-builder page: pick a template, reformat your own resume."""
    return render(
        request, "resume_builder.html", user=user,
        has_resume=bool(_resume_text(db, user)),
        llm_ready=settings.llm_configured,
        templates=BUILDER_TEMPLATES,
        selected="modern",
    )


@router.post("/builder/run")
def builder_run(
    request: Request,
    template: str = Form("modern"),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """HTMX endpoint: reformat the user's resume and return the paper fragment."""
    if template not in _BUILDER_KEYS:
        template = "modern"
    try:
        paper = reformat_resume(_resume_text(db, user), template)
    except LLMError as exc:
        return render(request, "_resume_paper.html", user=user, error=str(exc))
    # NB: render()'s 2nd positional param is itself named `template` (the template
    # FILENAME), so the chosen style key must be passed under a different name.
    return render(request, "_resume_paper.html", user=user, paper=paper, tpl=template)
