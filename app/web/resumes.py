"""
Upload, list, and delete resumes and cover letters.

On upload we extract plain text (for matching) and also keep the original file on
disk under uploads/<user_id>/ (private, git-ignored). Users only ever see their own
documents — every query is scoped to the logged-in user's id.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as SessionType

from app.assist import (
    coerce_grade,
    coerce_paper,
    grade_resume,
    improve_resume,
    paper_to_text,
    parse_resume,
)
from app.config import PROJECT_ROOT, settings
from app.llm import LLMError
from app.models import Resume, User
from app.resume_parse import SUPPORTED_EXTENSIONS, extract_text
from app.web.deps import add_flash, get_db, render, require_user

logger = logging.getLogger("jobbot.web.resumes")

router = APIRouter(prefix="/resumes")

UPLOAD_DIR = PROJECT_ROOT / "uploads"
MAX_BYTES = 5 * 1024 * 1024  # 5 MB is plenty for a resume


def _parse_resume_bg(doc_id: int, regrade: bool = True) -> None:
    """Background task: parse a freshly-uploaded resume into `parsed_json`,
    then GRADE it into `grade_json` (the Resume-score card).

    Runs AFTER the upload response so the user isn't blocked on the model
    calls. Best-effort: a failure just leaves the column NULL. Only resumes
    (not cover letters) are parsed/graded. Grading counts against the monthly
    AI budget so public signups can't run up the bill. Builder saves arrive
    already graded, so they pass ``regrade=False`` to keep their score.
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
        if regrade:
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


def _int(value, default: int = 0) -> int:
    """Parse an int off a form/query value without ever raising."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---- "Your resume today": pin the graded fixes onto the raw resume text ----
# Recognized section headings (canonical key -> line prefixes). A line counts as
# a heading only when it's short, standalone, and starts with an alias — so job
# titles like "IT Support Volunteer · Hospital · 2023" never match.
_SECTION_ALIASES = [
    ("summary", ("summary", "objective", "profile", "about me")),
    ("experience", ("experience", "employment", "work history", "career history",
                    "professional experience", "work experience", "relevant experience")),
    ("projects", ("projects", "personal projects")),
    ("skills", ("skills", "technical skills", "core competencies", "competencies",
                "technologies", "areas of expertise")),
    ("education", ("education", "academic")),
    ("certifications", ("certifications", "certificates", "licenses")),
    ("volunteer", ("volunteer",)),
]
# Which resume section a suggestion is ABOUT, guessed from its wording. Scanned
# in order; a rule maps to the first of its keys that exists in the resume.
_TOPIC_RULES = [
    (re.compile(r"summar|objectiv|profile", re.I), ("summary",)),
    (re.compile(r"certif|licen", re.I), ("certifications", "education")),
    (re.compile(r"educat|degree|gpa", re.I), ("education",)),
    (re.compile(r"skill|keyword|terminolog|technolog|tool", re.I), ("skills", "experience")),
    (re.compile(r"project", re.I), ("projects",)),
    (re.compile(r"experien|achiev|quantif|metric|impact|bullet|accomplish|role|job",
                re.I), ("experience",)),
    (re.compile(r"volunteer", re.I), ("volunteer", "experience")),
]
_ADD_VERBS = re.compile(r"\b(add|include|missing|create|list)\b", re.I)


def _canon_heading(line: str) -> str | None:
    """The section key if this raw-text line is a section heading, else None."""
    s = line.strip().rstrip(":").strip()
    if not s or len(s) > 48 or len(s.split()) > 5 or s.endswith((".", ",", ";")):
        return None
    low = re.sub(r"[^a-z& ]+", " ", s.lower()).strip()
    if not low:
        return None
    for key, aliases in _SECTION_ALIASES:
        if any(low == a or low.startswith((a + " ", a + "&")) for a in aliases):
            if s == s.upper() or s.istitle() or len(s.split()) <= 3:
                return key
    return None


def _split_resume_sections(raw: str) -> list[dict]:
    """Split raw resume text into [{key, heading, text}] blocks; the first block
    (no heading) is the name/contact preamble."""
    secs: list[dict] = [{"key": "", "heading": "", "lines": []}]
    for line in raw.splitlines():
        key = _canon_heading(line)
        if key:
            secs.append({"key": key, "heading": line.strip(), "lines": []})
        else:
            secs[-1]["lines"].append(line)
    out = []
    for s in secs:
        text = "\n".join(s["lines"]).strip("\n")
        if s["heading"] or text.strip():
            out.append({"key": s["key"], "heading": s["heading"], "text": text})
    return out


def _mark_parts(text: str, hits: list[tuple]) -> list[dict]:
    """Split section text into plain/highlighted parts from (start, end, item)
    hits, skipping overlaps — the template renders marks safely escaped."""
    parts: list[dict] = []
    pos = 0
    for a, b, item in sorted(hits, key=lambda h: h[0]):
        if a < pos:
            continue
        if a > pos:
            parts.append({"mark": None, "text": text[pos:a]})
        parts.append({"mark": item, "text": text[a:b]})
        pos = b
    if pos < len(text) or not parts:
        parts.append({"mark": None, "text": text[pos:]})
    return parts


def _annotate_resume(raw_text: str, suggestions: list[dict]) -> dict:
    """Build the "Your resume today" view: the resume split into sections, with
    each graded suggestion pinned as best we can — an exact-quote highlight
    (when the grade stored a `where` quote), a box around the section it's
    about, a dashed "add this" box when the section doesn't exist, or a
    whole-document banner. Numbering (1..N) matches the step-1 fix list."""
    text = (raw_text or "")[:25000]
    sections = _split_resume_sections(text)
    first_idx: dict[str, int] = {}
    for idx, sec in enumerate(sections):
        if sec["key"] and sec["key"] not in first_idx:
            first_idx[sec["key"]] = idx

    quote_hits: dict[int, list] = {i: [] for i in range(len(sections))}
    sec_marks: dict[int, list] = {i: [] for i in range(len(sections))}
    doc_marks: list[dict] = []
    adds: list[dict] = []

    for num, s in enumerate(suggestions, 1):
        item = {
            "num": num,
            "priority": "fix" if s.get("priority") == "fix" else "improve",
            "title": str(s.get("title") or ""),
            "detail": str(s.get("detail") or ""),
            "points": s.get("points") or 0,
        }
        placed = False
        # 1) exact quote from the grade, if it still matches the text
        quote = str(s.get("where") or "").strip()
        if len(quote) >= 8:
            for idx, sec in enumerate(sections):
                i = sec["text"].lower().find(quote.lower())
                if i >= 0:
                    quote_hits[idx].append((i, i + len(quote), item))
                    sec_marks[idx].append(item)
                    placed = True
                    break
        # 2) the section its wording is about; 3) "add X" with no section = add box
        if not placed:
            blob = f"{item['title']} {item['detail']}"
            for pat, keys in _TOPIC_RULES:
                if pat.search(blob):
                    for k in keys:
                        if k in first_idx:
                            sec_marks[first_idx[k]].append(item)
                            placed = True
                            break
                    if not placed and _ADD_VERBS.search(blob):
                        adds.append(item)
                        placed = True
                    break
        if not placed:  # 4) about the document overall (structure, length, ...)
            doc_marks.append(item)

    out_sections = [
        {"heading": sec["heading"], "marks": sec_marks[idx],
         "parts": _mark_parts(sec["text"], quote_hits[idx])}
        for idx, sec in enumerate(sections)
    ]
    return {
        "sections": out_sections,
        "doc_marks": doc_marks,
        "adds": adds,
        "any": bool(doc_marks or adds or any(sec_marks.values())),
    }


def _paper_from_json(raw: str) -> dict | None:
    """Parse + sanitize the paper JSON the builder round-trips through the
    browser (hidden field). None when it's missing, malformed, or empty."""
    raw = (raw or "").strip()
    if not raw or len(raw) > 200_000:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    paper = coerce_paper(data)
    if not (paper["name"] or paper["summary"] or paper["sections"]):
        return None
    return paper


@router.get("/builder")
def builder_page(
    request: Request,
    doc: int = 0,  # ?doc=<id> picks which resume to improve
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """The resume-builder page: tick the graded fixes to apply, add your own
    instructions, pick a look — then run, review every change + the new score,
    and (only if you choose) save the result as a new document."""
    docs = (
        db.query(Resume).filter_by(user_id=user.id, kind="resume")
        .order_by(Resume.uploaded_at.desc()).all()
    )
    target = (
        next((d for d in docs if d.id == doc), None)
        or next((d for d in docs if d.grade_json), None)
        or (docs[0] if docs else None)
    )
    # The score card's non-"good" suggestions become pre-ticked checkboxes; the
    # checkbox value is the fix text itself, so the list can refresh after runs.
    suggestions = []
    if target is not None and target.grade_json:
        suggestions = [
            s for s in (target.grade_json.get("suggestions") or [])
            if isinstance(s, dict) and s.get("priority") != "good"
        ]
    # "Your resume today": the current text with the numbered fixes pinned on.
    annotations = None
    if target is not None and (target.raw_text or "").strip():
        annotations = _annotate_resume(target.raw_text, suggestions)
    return render(
        request, "resume_builder.html", user=user,
        llm_ready=settings.llm_configured,
        docs=docs, target=target, fix_suggestions=suggestions,
        annotations=annotations,
        before=(target.grade_json or {}).get("overall") if target else None,
        templates=BUILDER_TEMPLATES,
        selected="modern",
    )


@router.post("/builder/run")
def builder_run(
    request: Request,
    template: str = Form("modern"),
    doc_id: str = Form("0"),
    fixes: list[str] = Form([]),    # the ticked fix texts (from the step-1 list)
    custom: list[str] = Form([]),   # the user's own typed instructions
    paper_json: str = Form(""),     # present after the first run: iterate on it
    after_json: str = Form(""),     # the current version's grade, if any
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """HTMX: improve the resume (selected fixes + custom instructions), re-grade
    the result, and return the result fragment — before/after score, the change
    log, and the styled paper preview — plus an out-of-band refresh of the
    step-1 fix list with what's STILL worth fixing. Runs are iterative: the
    first starts from the uploaded resume, later ones keep polishing the
    improved version. Nothing is stored here."""
    from app.llm_budget import try_spend

    if template not in _BUILDER_KEYS:
        template = "modern"
    doc = (
        db.query(Resume)
        .filter_by(id=_int(doc_id), user_id=user.id, kind="resume").first()
        or db.query(Resume).filter_by(user_id=user.id, kind="resume")
        .order_by(Resume.uploaded_at.desc()).first()
    )

    # What this run starts from: the last run's paper (keep polishing), else the
    # uploaded resume. "Before" is the score of whatever we start from.
    base_paper = _paper_from_json(paper_json)
    if base_paper is not None:
        base_text = paper_to_text(base_paper)
        before = None
        if after_json.strip():
            try:
                prior = coerce_grade(json.loads(after_json[:100_000]))
                before = prior["overall"] or None
            except json.JSONDecodeError:
                pass
        if before is None and doc is not None:
            before = (doc.grade_json or {}).get("overall")
    else:
        if doc is None or not (doc.raw_text or "").strip():
            return render(request, "_builder_result.html", user=user,
                          run_error="Upload a resume first on the Resumes page.")
        base_text = doc.raw_text
        before = (doc.grade_json or {}).get("overall")

    instructions: list[str] = []
    for f in fixes[:10]:
        f = str(f or "").strip()[:400]
        if f:
            instructions.append(f)
    for c in custom[:8]:
        c = str(c or "").strip()[:300]
        if c:
            instructions.append(c)

    if not try_spend(db, 2):  # one rewrite call + one re-grade call
        return render(request, "_builder_result.html", user=user,
                      run_error="This month's AI budget is used up — the builder "
                                "can't run until it resets on the 1st.")

    try:
        result = improve_resume(base_text, instructions)
    except LLMError as exc:
        return render(request, "_builder_result.html", user=user, run_error=str(exc))
    paper = result["paper"]
    if not (paper["name"] or paper["summary"] or paper["sections"]):
        return render(request, "_builder_result.html", user=user,
                      run_error="The AI couldn't restructure your resume this "
                                "time — please run it again.")

    after = None
    try:
        roles = ((doc.parsed_json if doc else None) or {}).get("target_roles") or []
        after = grade_resume(paper_to_text(paper), roles)
    except LLMError as exc:
        logger.warning("builder re-grade failed for user %s: %s", user.id, exc)

    # The refreshed step-1 list: what the NEW grade still flags (skip "good").
    new_suggestions = None
    if after is not None:
        new_suggestions = [
            s for s in after.get("suggestions") or []
            if isinstance(s, dict) and s.get("priority") != "good"
        ]

    # NB: render()'s 2nd positional param is itself named `template` (the template
    # FILENAME), so the chosen style key must be passed under a different name.
    return render(
        request, "_builder_result.html", user=user,
        paper=paper, tpl=template, changes=result["changes"],
        before=before, after=after,
        refresh_fixes=new_suggestions is not None,
        new_suggestions=new_suggestions or [],
        paper_json=json.dumps(paper, ensure_ascii=False),
        after_json=json.dumps(after, ensure_ascii=False) if after else "",
    )


@router.post("/builder/restyle")
def builder_restyle(
    request: Request,
    template: str = Form("modern"),
    paper_json: str = Form(""),
    user: User = Depends(require_user),
):
    """HTMX: re-render the last run's paper in a different look — template
    styling is pure rendering, so switching is instant and costs no AI call."""
    if template not in _BUILDER_KEYS:
        template = "modern"
    paper = _paper_from_json(paper_json)
    if paper is None:
        return render(request, "_resume_paper.html", user=user,
                      error="Run the builder first, then switch looks.")
    return render(request, "_resume_paper.html", user=user, paper=paper, tpl=template)


@router.post("/builder/save")
def builder_save(
    request: Request,
    background: BackgroundTasks,
    doc_id: str = Form("0"),
    paper_json: str = Form(""),
    after_json: str = Form(""),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Save a builder result as a NEW resume document (the original upload is
    never touched). The run's fresh grade is stored with it, so the Resume-score
    card shows the new score immediately."""
    paper = _paper_from_json(paper_json)
    text = paper_to_text(paper) if paper else ""
    if not text.strip():
        return HTMLResponse('<span class="bld-savemsg">Nothing to save yet — '
                            "run the builder first.</span>")

    grade = None
    if after_json.strip():
        try:
            grade = coerce_grade(json.loads(after_json[:100_000]))
            if not grade["overall"]:
                grade = None
        except json.JSONDecodeError:
            grade = None

    orig = (
        db.query(Resume)
        .filter_by(id=_int(doc_id), user_id=user.id, kind="resume").first()
    )
    stem = orig.filename.rsplit(".", 1)[0].strip() if orig else "Resume"
    filename = f"{stem or 'Resume'} (improved).txt"

    new_doc = Resume(user_id=user.id, kind="resume", filename=filename,
                     raw_text=text, grade_json=grade)
    db.add(new_doc)
    db.commit()
    # Parse in the background so matching reads the new version; skip regrading
    # when the run's grade came along (it's already stored).
    if settings.llm_configured:
        background.add_task(_parse_resume_bg, new_doc.id, grade is None)

    add_flash(request,
              f"Saved “{filename}” to your documents"
              + (f" — scored {grade['overall']}/100." if grade else "."),
              "success")
    return HTMLResponse("", headers={"HX-Redirect": f"/resumes?score={new_doc.id}"})
