"""
Application Kit: a per-job, ready-to-use application package.

One click on a job page generates — grounded in the user's real resume —
  * a TAILORED RESUME (structured; downloadable as PDF and Word),
  * a complete COVER LETTER (PDF / copy),
  * drafted answers to the five standard portal questions,
all stored in `application_kits` so viewing and downloading never re-spends
AI calls. Regenerating overwrites in place. Generation costs 2 AI calls and
counts against the monthly AI budget (JOBBOT_LLM_MONTHLY_CAP).

Nothing is ever submitted anywhere: the kit produces files and text the user
pastes into the real application themselves.
"""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse, Response

from app.assist import LLMError, build_application_kit, tailor_resume_structured
from app.models import ApplicationKit, User
from app.web.deps import add_flash, get_db, render, require_user
from sqlalchemy.orm import Session as SessionType

logger = logging.getLogger("jobbot.web.kit")

router = APIRouter()

_DEJAVU = Path("/usr/share/fonts/truetype/dejavu")


# --------------------------------------------------------------- generation
@router.post("/jobs/{job_id}/kit")
def generate_kit(
    request: Request,
    job_id: int,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """HTMX: build (or rebuild) the kit and return the kit fragment."""
    from app.llm_budget import try_spend
    from app.web.assist import _job_for_user, _resume_text

    job = _job_for_user(db, user, job_id)
    if job is None:
        return render(request, "_kit.html", user=user,
                      kit_error="That job isn't in your matches.")
    resume_text = _resume_text(db, user)
    if not resume_text:
        return render(request, "_kit.html", user=user,
                      kit_error="Upload a resume first on the Resumes page.")
    if not try_spend(db, 2):  # two model calls per kit
        return render(request, "_kit.html", user=user,
                      kit_error="This month's AI budget is used up — the kit "
                                "can't be generated until it resets on the 1st.")

    try:
        content = build_application_kit(resume_text, job)
        content["resume"] = tailor_resume_structured(resume_text, job)
    except LLMError as exc:
        return render(request, "_kit.html", user=user, kit_error=str(exc))

    row = (
        db.query(ApplicationKit)
        .filter_by(user_id=user.id, job_id=job.id)
        .first()
    )
    if row is None:
        row = ApplicationKit(user_id=user.id, job_id=job.id)
        db.add(row)
    row.content = content
    db.commit()
    logger.info("built application kit for user %s job %s", user.id, job.id)
    return render(request, "_kit.html", user=user, job=job, kit=content, kit_row=row)


# ---------------------------------------------------------------- downloads
_ARTIFACTS = {
    "resume.pdf": ("resume", "pdf"),
    "resume.docx": ("resume", "docx"),
    "cover-letter.pdf": ("letter", "pdf"),
    "cover-letter.docx": ("letter", "docx"),
}
_MEDIA = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


@router.get("/jobs/{job_id}/kit/{fname}")
def download_artifact(
    request: Request,
    job_id: int,
    fname: str,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    art = _ARTIFACTS.get(fname)
    row = (
        db.query(ApplicationKit)
        .filter_by(user_id=user.id, job_id=job_id)
        .first()
    )
    if art is None or row is None or not row.content:
        add_flash(request, "Generate the application kit first.", "error")
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)

    kind, ext = art
    content = row.content
    resume = content.get("resume") or {}
    name = resume.get("name") or "resume"
    if kind == "resume":
        blob = _resume_pdf(resume) if ext == "pdf" else _resume_docx(resume)
        base = f"{name} - tailored resume"
    else:
        letter = content.get("cover_letter") or ""
        blob = _letter_pdf(letter) if ext == "pdf" else _letter_docx(letter)
        base = f"{name} - cover letter"

    safe = re.sub(r"[^A-Za-z0-9 ._-]+", "", base).strip() or "document"
    return Response(
        content=blob,
        media_type=_MEDIA[ext],
        headers={"Content-Disposition": f'attachment; filename="{safe}.{ext}"'},
    )


# ------------------------------------------------------------- file builders
def _resume_docx(data: dict) -> bytes:
    """The tailored structured resume as a clean, ATS-safe Word document."""
    import docx
    from docx.shared import Pt, RGBColor

    d = docx.Document()
    style = d.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)

    def para(text, *, size=10.5, bold=False, color=None, space_after=4):
        p = d.add_paragraph()
        run = p.add_run(text)
        run.bold = bold
        run.font.size = Pt(size)
        if color:
            run.font.color.rgb = RGBColor(*color)
        p.paragraph_format.space_after = Pt(space_after)
        return p

    if data.get("name"):
        para(data["name"], size=19, bold=True, space_after=1)
    if data.get("headline"):
        para(data["headline"], size=11, color=(70, 80, 105), space_after=1)
    if data.get("contact"):
        para(data["contact"], size=9.5, color=(110, 120, 140), space_after=8)
    if data.get("summary"):
        para("SUMMARY", size=10.5, bold=True, space_after=2)
        para(data["summary"], space_after=8)

    for sec in data.get("sections") or []:
        para((sec.get("heading") or "").upper(), size=10.5, bold=True, space_after=2)
        for ent in sec.get("entries") or []:
            head = " — ".join(x for x in [ent.get("role"), ent.get("org")] if x)
            line = " · ".join(x for x in [head, ent.get("dates")] if x)
            if line:
                para(line, bold=True, space_after=1)
            for b in ent.get("bullets") or []:
                p = d.add_paragraph(b, style="List Bullet")
                p.paragraph_format.space_after = Pt(1)
        d.add_paragraph().paragraph_format.space_after = Pt(2)

    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _letter_docx(text: str) -> bytes:
    import docx
    from docx.shared import Pt

    d = docx.Document()
    d.styles["Normal"].font.name = "Calibri"
    d.styles["Normal"].font.size = Pt(11)
    for part in (text or "").split("\n"):
        p = d.add_paragraph(part)
        p.paragraph_format.space_after = Pt(6 if part.strip() else 0)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def _pdf_doc():
    """A5-margin A4 PDF with full-unicode DejaVu fonts registered."""
    from fpdf import FPDF

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_margins(17, 16, 17)
    pdf.add_font("dj", "", str(_DEJAVU / "DejaVuSans.ttf"))
    pdf.add_font("dj", "B", str(_DEJAVU / "DejaVuSans-Bold.ttf"))
    pdf.add_page()
    return pdf


def _resume_pdf(data: dict) -> bytes:
    pdf = _pdf_doc()
    w = pdf.w - pdf.l_margin - pdf.r_margin

    if data.get("name"):
        pdf.set_font("dj", "B", 17)
        pdf.set_text_color(20, 24, 40)
        pdf.multi_cell(w, 7.5, data["name"])
    if data.get("headline"):
        pdf.set_font("dj", "", 10.5)
        pdf.set_text_color(80, 90, 115)
        pdf.multi_cell(w, 5.4, data["headline"])
    if data.get("contact"):
        pdf.set_font("dj", "", 8.8)
        pdf.set_text_color(120, 128, 145)
        pdf.multi_cell(w, 4.8, data["contact"])
    pdf.ln(1.5)
    pdf.set_draw_color(190, 196, 210)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(3)

    def heading(txt):
        pdf.set_font("dj", "B", 10.2)
        pdf.set_text_color(60, 66, 96)
        pdf.multi_cell(w, 5.6, txt.upper())
        pdf.ln(0.5)

    if data.get("summary"):
        heading("Summary")
        pdf.set_font("dj", "", 9.6)
        pdf.set_text_color(45, 52, 70)
        pdf.multi_cell(w, 5.0, data["summary"])
        pdf.ln(2.5)

    for sec in data.get("sections") or []:
        heading(sec.get("heading") or "")
        for ent in sec.get("entries") or []:
            head = " — ".join(x for x in [ent.get("role"), ent.get("org")] if x)
            if head:
                pdf.set_font("dj", "B", 9.8)
                pdf.set_text_color(30, 36, 58)
                pdf.multi_cell(w, 5.2, head)
            if ent.get("dates"):
                pdf.set_font("dj", "", 8.6)
                pdf.set_text_color(125, 132, 150)
                pdf.multi_cell(w, 4.6, ent["dates"])
            pdf.set_font("dj", "", 9.4)
            pdf.set_text_color(45, 52, 70)
            for b in ent.get("bullets") or []:
                pdf.set_x(pdf.l_margin + 3)
                pdf.multi_cell(w - 3, 4.9, f"•  {b}")
            pdf.ln(1.2)
        pdf.ln(1.4)

    return bytes(pdf.output())


def _letter_pdf(text: str) -> bytes:
    pdf = _pdf_doc()
    w = pdf.w - pdf.l_margin - pdf.r_margin
    pdf.set_font("dj", "", 10.6)
    pdf.set_text_color(35, 42, 62)
    for part in (text or "").split("\n"):
        if part.strip():
            pdf.multi_cell(w, 5.6, part)
        else:
            pdf.ln(3.4)
    return bytes(pdf.output())
