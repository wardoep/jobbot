"""
The application assistant (Phase 6): tailor a resume/cover letter to a job, and
draft answers to application questions — grounded in the user's own resume.

This module is provider-agnostic: it builds the prompts and parses the replies,
but the actual model call goes through an `LLMProvider` (app/llm/), so swapping
OpenAI for another vendor never touches this logic.

It is a DRAFT helper, per the spec: it returns editable suggestions/answers and
NEVER overwrites the user's stored documents, and the prompts forbid inventing
experience the candidate doesn't have.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Optional

from app.llm import LLMError, LLMProvider, get_default_provider
from app.models import Job

# Caps keep prompts (and cost) bounded; anything longer is truncated.
_RESUME_CAP = 6000
_COVER_CAP = 4000
_JOB_CAP = 6000
# The builder reorganizes the WHOLE resume, so it gets a larger slice.
_BUILDER_CAP = 8000


@dataclass
class TailoringSuggestions:
    summary: str
    resume: str
    cover_letter: str
    keywords: list[str]
    model: str


def _job_block(job: Job) -> str:
    parts = [f"Title: {job.title}"]
    if job.company:
        parts.append(f"Company: {job.company}")
    if job.location:
        parts.append(f"Location: {job.location}")
    if job.work_type:
        parts.append(f"Work type: {job.work_type}")
    desc = (job.description or "").strip()[:_JOB_CAP]
    parts.append(f"\nJob description:\n{desc or '(no description provided)'}")
    return "\n".join(parts)


def tailor_application(
    resume_text: str,
    cover_letter_text: str,
    job: Job,
    provider: Optional[LLMProvider] = None,
) -> TailoringSuggestions:
    """Suggest how to tailor the resume + cover letter to one job (editable)."""
    provider = provider or get_default_provider()
    resume_text = (resume_text or "").strip()
    if not resume_text:
        raise LLMError("No resume text on file. Upload a resume first.")

    system = (
        "You are a meticulous, honest career coach. You help a candidate tailor "
        "their resume and cover letter to ONE specific job. Give concrete, "
        "actionable, EDITABLE suggestions the candidate applies themselves — do not "
        "rewrite their whole document, and NEVER invent experience, skills, or "
        "numbers they did not provide. If the job needs something the resume lacks, "
        "say so plainly. Reply with a single JSON object with these string keys: "
        '"summary" (2-3 sentence honest fit assessment), "resume" (a short markdown '
        'list of specific tailoring suggestions), "cover_letter" (suggestions for '
        "the cover letter, or how to start one if none was provided), and "
        '"keywords" (a JSON array of important terms from the job description worth '
        "mirroring honestly)."
    )
    cover = (cover_letter_text or "").strip()[:_COVER_CAP]
    user = (
        f"=== JOB ===\n{_job_block(job)}\n\n"
        f"=== CANDIDATE RESUME ===\n{resume_text[:_RESUME_CAP]}\n\n"
        f"=== CANDIDATE COVER LETTER ===\n{cover or '(none on file)'}\n\n"
        "Produce the JSON described above."
    )

    raw = provider.complete(
        system, user, json_mode=True, max_output_tokens=900, temperature=0.4
    )
    data = _safe_json(raw)
    kws = data.get("keywords") or []
    if isinstance(kws, str):
        kws = [k.strip() for k in kws.split(",") if k.strip()]
    return TailoringSuggestions(
        summary=_as_text(data.get("summary")),
        resume=_as_text(data.get("resume")),
        cover_letter=_as_text(data.get("cover_letter")),
        keywords=[str(k) for k in kws][:20],
        model=provider.model,
    )


def draft_answer(
    resume_text: str,
    job: Job,
    question: str,
    provider: Optional[LLMProvider] = None,
) -> str:
    """Draft a first-person answer to one application question, grounded in the resume."""
    provider = provider or get_default_provider()
    question = (question or "").strip()
    if not question:
        raise LLMError("Please enter the application question first.")
    resume_text = (resume_text or "").strip()
    if not resume_text:
        raise LLMError("No resume text on file. Upload a resume first.")

    system = (
        "You help a job applicant draft an answer to an application question. "
        "Ground the answer ONLY in the candidate's resume and the job context. "
        "Write in the first person, be specific and concise, and NEVER invent "
        "facts, employers, dates, or numbers not supported by the resume. If the "
        "resume doesn't support a strong answer, write the best honest draft and "
        "add one short note at the end about what the candidate should add. This is "
        "a draft the candidate will edit before submitting."
    )
    user = (
        f"=== JOB ===\n{_job_block(job)}\n\n"
        f"=== CANDIDATE RESUME ===\n{resume_text[:_RESUME_CAP]}\n\n"
        f"=== APPLICATION QUESTION ===\n{question}\n\n"
        "Write the draft answer now."
    )
    return provider.complete(
        system, user, max_output_tokens=600, temperature=0.5
    ).strip()


def reformat_resume(
    resume_text: str,
    template: str,
    provider: Optional[LLMProvider] = None,
) -> dict:
    """Reorganize the candidate's OWN resume into clean, structured sections.

    This is an honest REFORMAT, not a rewrite: it restructures the resume the
    candidate already has into a predictable JSON shape the "paper" preview
    renders. It NEVER invents employers, titles, dates, numbers, or skills not
    present in the source. The chosen ``template`` only drives styling later — it
    does not change the content. Coercion is fully defensive so a malformed model
    reply yields an empty-but-safe paper rather than raising.
    """
    provider = provider or get_default_provider()
    resume_text = (resume_text or "").strip()
    if not resume_text:
        raise LLMError("No resume text on file. Upload a resume first.")

    system = (
        "You are an honest, meticulous resume editor. You REORGANIZE a candidate's "
        "EXISTING resume into clean, ATS-friendly sections — you restructure and "
        "lightly tighten what is already there. You NEVER invent employers, job "
        "titles, dates, numbers, metrics, or skills that are not present in the "
        "source text. If a detail is missing, leave it blank rather than guessing. "
        "Reply with a single JSON object with these keys: "
        '"name" (the candidate\'s name from the resume, or ""), '
        '"headline" (their current or target role line, or ""), '
        '"contact" (ONE line joining only the parts present in the resume with '
        '" · ", e.g. "City, ST · email · phone"; "" if none), '
        '"summary" (a 2-3 sentence professional summary drawn ONLY from the resume), '
        '"sections" (a JSON array, in this order WHEN the source has the content: '
        "Experience, Projects, Skills, Education, Certifications — omit any "
        "section with no source content). Each section is "
        '{"heading": str, "entries": [ {"role": str, "org": str, "dates": str, '
        '"bullets": [str, ...]} ]}. For a Skills section, use a SINGLE entry whose '
        '"bullets" is the list of skills and whose "role", "org" and "dates" are "".'
    )
    user = (
        f"=== CANDIDATE RESUME ===\n{resume_text[:_BUILDER_CAP]}\n\n"
        "Reorganize this resume into the JSON object described above. Use only "
        "information present above; do not add anything new."
    )

    raw = provider.complete(
        system, user, json_mode=True, max_output_tokens=1200, temperature=0.3
    )
    paper = coerce_paper(_safe_json(raw))
    paper["model"] = provider.model
    return paper


def improve_resume(
    resume_text: str,
    instructions: list[str],
    provider: Optional[LLMProvider] = None,
) -> dict:
    """The resume builder's rewrite step: apply the fixes the user ticked (from
    their resume grade) plus any instructions they typed themselves — honestly.

    Returns ``{"paper": <same shape as reformat_resume>, "changes": [...],
    "model": str}``. ``changes`` is the log the builder shows ("what changed &
    why"): each item is ``{"area", "what", "why", "needs_you"}`` where
    ``needs_you`` marks an edit that left a [bracketed placeholder] only the
    candidate can fill in (a real metric, a date). With no instructions it does
    a clean reorganization and still logs what it touched. Same honesty rules
    as the rest of this module: never invents facts; defensive parsing.
    """
    provider = provider or get_default_provider()
    resume_text = (resume_text or "").strip()
    if not resume_text:
        raise LLMError("No resume text on file. Upload a resume first.")

    todo = [str(i).strip()[:300] for i in (instructions or []) if str(i).strip()][:12]
    todo_block = "\n".join(f"{n}. {t}" for n, t in enumerate(todo, 1)) or (
        "(none — do a clean, honest reorganization with light tightening, "
        "and log what you changed)"
    )

    system = (
        "You are an honest, meticulous resume editor. You IMPROVE a candidate's "
        "EXISTING resume: apply each numbered instruction, plus obvious cleanup "
        "(standard section headings, consistent formatting, tighter wording). "
        "HARD RULES: NEVER invent employers, job titles, dates, numbers, metrics, "
        "tools, or skills that are not in the source resume. Where an instruction "
        "needs a fact only the candidate knows (e.g. 'add metrics'), rewrite the "
        "line with a short [bracketed placeholder] such as [X%] or [team size] "
        'and mark that change "needs_you": true. If an instruction cannot be '
        "done honestly from the source text, skip it and say so in the change "
        "log. Reply with ONE JSON object with these keys:\n"
        '"name" (from the resume, or ""), '
        '"headline" (their role line, or ""), '
        '"contact" (ONE line joining only the parts present, with " · "; "" if none), '
        '"summary" (2-3 sentence professional summary, facts from the resume only), '
        '"sections" (JSON array in this order WHEN the source has content: '
        "Experience, Projects, Skills, Education, Certifications; each section is "
        '{"heading": str, "entries": [{"role": str, "org": str, "dates": str, '
        '"bullets": [str, ...]}]}; for Skills use ONE entry whose "bullets" is '
        'the skill list and whose "role", "org" and "dates" are ""), and\n'
        '"changes" (3-10 items, most important first, covering EVERY meaningful '
        'edit you made: {"area": short location like "Summary" or "Experience — '
        '<company>", "what": the edit in one plain sentence, "why": how it '
        'helps in one short sentence, "needs_you": true only if you left a '
        "[placeholder] there}). The change log must be honest — never claim an "
        "edit you did not make."
    )
    user = (
        f"=== INSTRUCTIONS TO APPLY ===\n{todo_block}\n\n"
        f"=== CANDIDATE RESUME ===\n{resume_text[:_BUILDER_CAP]}\n\n"
        "Rewrite the resume per the instructions and return the JSON object."
    )
    raw = provider.complete(
        system, user, json_mode=True, max_output_tokens=1700, temperature=0.3
    )
    data = _safe_json(raw)
    return {
        "paper": coerce_paper(data),
        "changes": _coerce_changes(data.get("changes")),
        "model": provider.model,
    }


def paper_to_text(paper: dict) -> str:
    """Flatten a builder paper back into plain resume text — what gets graded
    and what a saved copy stores as its ``raw_text``."""
    paper = paper or {}
    lines: list[str] = []
    for key in ("name", "headline", "contact"):
        if paper.get(key):
            lines.append(str(paper[key]))
    if paper.get("summary"):
        lines += ["", "SUMMARY", str(paper["summary"])]
    for sec in paper.get("sections") or []:
        heading = str(sec.get("heading") or "").strip()
        lines += ["", heading.upper() or "SECTION"]
        for e in sec.get("entries") or []:
            head = " · ".join(
                str(e.get(k) or "").strip()
                for k in ("role", "org", "dates")
                if str(e.get(k) or "").strip()
            )
            if head:
                lines.append(head)
            lines += [f"- {b}" for b in (e.get("bullets") or [])]
    return "\n".join(lines).strip()


def tailor_resume_structured(
    resume_text: str,
    job: Job,
    provider: Optional[LLMProvider] = None,
) -> dict:
    """The Application Kit's tailored resume: the candidate's OWN resume in the
    same structured shape as ``reformat_resume`` (name/headline/contact/summary/
    sections), but reordered and re-emphasized for ONE specific job — the most
    relevant experience and skills first, the summary rewritten to mirror the
    posting's honest terminology. NEVER invents employers, dates, numbers, or
    skills not in the source. Renders in the builder's paper styles and exports
    to PDF/DOCX unchanged.
    """
    provider = provider or get_default_provider()
    resume_text = (resume_text or "").strip()
    if not resume_text:
        raise LLMError("No resume text on file. Upload a resume first.")

    system = (
        "You are an honest, meticulous resume editor. You TAILOR a candidate's "
        "EXISTING resume to one specific job: reorder sections and bullets so "
        "the most relevant material leads, tighten wording, and rewrite ONLY "
        "the summary/headline to speak to this job using terms that honestly "
        "describe what is already in the resume. You NEVER invent employers, "
        "job titles, dates, numbers, metrics, or skills that are not present "
        "in the source. If a detail is missing, leave it blank. "
        "Reply with a single JSON object with these keys: "
        '"name" (from the resume, or ""), '
        '"headline" (a role line aimed at THIS job, drawn from real experience), '
        '"contact" (ONE line joining only the parts present, with " · "; "" if none), '
        '"summary" (2-3 sentences tailored to this job, facts from the resume only), '
        '"sections" (JSON array; most job-relevant sections and bullets FIRST). '
        'Each section is {"heading": str, "entries": [{"role": str, "org": str, '
        '"dates": str, "bullets": [str, ...]}]}. For a Skills section use a '
        'SINGLE entry whose "bullets" is the skills list (most relevant first) '
        'and whose "role", "org" and "dates" are "".'
    )
    user = (
        f"=== JOB ===\n{_job_block(job)}\n\n"
        f"=== CANDIDATE RESUME ===\n{resume_text[:_BUILDER_CAP]}\n\n"
        "Tailor the resume to this job as the JSON object described. Use only "
        "information present in the resume; do not add anything new."
    )
    raw = provider.complete(
        system, user, json_mode=True, max_output_tokens=1400, temperature=0.3
    )
    paper = coerce_paper(_safe_json(raw))
    paper["model"] = provider.model
    return paper


# The five portal questions every kit drafts, in display order.
KIT_QUESTIONS = [
    "Why do you want to work here?",
    "What are your greatest strengths?",
    "When can you start?",
    "What are your salary expectations?",
    "Are you authorized to work in this country?",
]


def build_application_kit(
    resume_text: str,
    job: Job,
    provider: Optional[LLMProvider] = None,
) -> dict:
    """Generate the Application Kit prose: a tailored professional summary, a
    complete ready-to-send cover letter, and answers to the five standard
    portal questions — all grounded in the candidate's real resume.

    Honesty rules: never invent experience; anything the candidate must
    confirm themselves (start date, authorization status, exact salary) is
    written with [bracketed placeholders] so nothing false gets submitted.
    """
    provider = provider or get_default_provider()
    resume_text = (resume_text or "").strip()
    if not resume_text:
        raise LLMError("No resume text on file. Upload a resume first.")

    company = (job.company or "the company").strip()
    system = (
        "You are an honest career coach writing FIRST-PERSON application "
        "materials for a candidate, grounded ONLY in their resume and the job "
        "posting. Plain, confident, specific language — no clichés, no "
        "invented experience, numbers, or credentials. Where a fact only the "
        "candidate knows is needed (start date, work-authorization status, a "
        "specific salary number), write a [bracketed placeholder] they can "
        "fill in, phrased so the surrounding sentence still reads naturally. "
        "Reply with a single JSON object:\n"
        '"summary": 2-3 sentence professional summary tailored to this job '
        "(suitable for the top of an application or LinkedIn note),\n"
        '"cover_letter": a COMPLETE letter — greeting ("Dear Hiring Manager," '
        "unless the posting names someone), 3 short paragraphs (why them, why "
        "me with concrete resume evidence, close with availability), and a "
        'sign-off with the candidate\'s name from the resume,\n'
        '"answers": array of EXACTLY 5 objects {"q": str, "a": str} answering, '
        "in order: (1) why do you want to work at this company — reference "
        "something real about the job posting; (2) greatest strengths — tied "
        "to resume evidence; (3) when can you start — short, with a "
        "[start-date placeholder]; (4) salary expectations — a reasonable "
        "range for this role and level phrased flexibly"
        + (f", informed by the posting's listed pay of ${job.salary:,}" if job.salary else "")
        + "; (5) work authorization — one sentence with a [confirm your "
        "authorization] placeholder. Each answer 1-4 sentences, first person."
    )
    user = (
        f"=== JOB ===\n{_job_block(job)}\n\n"
        f"=== CANDIDATE RESUME ===\n{resume_text[:_RESUME_CAP]}\n\n"
        f"Write the JSON application kit for applying to {company} now."
    )
    raw = provider.complete(
        system, user, json_mode=True, max_output_tokens=1400, temperature=0.4
    )
    data = _safe_json(raw)

    answers: list[dict] = []
    raw_answers = data.get("answers") if isinstance(data.get("answers"), list) else []
    for i, q in enumerate(KIT_QUESTIONS):
        item = raw_answers[i] if i < len(raw_answers) and isinstance(raw_answers[i], dict) else {}
        answers.append({
            "q": _as_text(item.get("q")) or q,
            "a": _as_text(item.get("a")),
        })

    return {
        "summary": _as_text(data.get("summary")),
        "cover_letter": _as_text(data.get("cover_letter")),
        "answers": answers,
        "model": provider.model,
    }


_RESUME_PARSE_CAP = 12000  # resumes are short; cap keeps prompt + cost bounded


def parse_resume(resume_text: str, provider: Optional[LLMProvider] = None) -> dict:
    """Extract a STRUCTURED PROFILE from a resume into the shape stored in
    `resumes.parsed_json`. Resume-derived FACTS only (skills, titles held,
    seniority, years of experience, locations, domains) — NEVER preferences.

    Fully defensive: a malformed model reply yields safe empty defaults, never an
    exception (besides LLMError when there's no resume text / no provider).
    """
    provider = provider or get_default_provider()
    text = (resume_text or "").strip()
    if not text:
        raise LLMError("No resume text to parse. Upload a resume first.")

    system = (
        "You extract a STRUCTURED PROFILE from a candidate's resume. Use ONLY facts "
        "stated or directly evidenced in the resume. NEVER invent anything, and NEVER "
        "infer the candidate's preferences or desired roles — this captures what they "
        "HAVE done, not what they WANT. If a field isn't supported by the resume, use "
        "an empty list or null. Reply with a single JSON object with EXACTLY these keys:\n"
        '- "skills": string[] — concrete technical and professional skills/tools used.\n'
        '- "job_titles": string[] — job titles the person has actually held.\n'
        '- "seniority": string|null — overall seniority evidenced, one of: '
        "intern, junior, mid, senior, lead, manager, director, executive.\n"
        '- "years_experience": number|null — total years of professional experience '
        "(estimate from employment dates; null if unclear).\n"
        '- "locations": string[] — locations tied to the resume (where they have '
        "worked, studied, or are based) — NOT desired/target locations.\n"
        '- "domains": string[] — industries/domains they have worked in '
        "(e.g. fintech, healthcare, e-commerce, devtools).\n"
        '- "target_roles": string[] — 5-10 SHORT, common job-board search titles '
        "this resume is genuinely qualified for TODAY, judged strictly from its "
        "evidence and seniority (e.g. a junior IT resume → \"IT support\", "
        '"help desk", "desktop support" — not "CISO"). Use generic lowercase '
        "titles a job post would contain, not aspirations."
    )
    user = f"=== RESUME ===\n{text[:_RESUME_PARSE_CAP]}\n\nReturn the JSON profile now."
    raw = provider.complete(
        system, user, json_mode=True, max_output_tokens=900, temperature=0.1
    )
    data = _safe_json(raw)

    def _strlist(value) -> list[str]:
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()][:50]
        if isinstance(value, str) and value.strip():
            return [s.strip() for s in value.split(",") if s.strip()]
        return []

    yrs = data.get("years_experience")
    try:
        yrs = float(yrs) if yrs is not None and str(yrs).strip() != "" else None
        if yrs is not None and float(yrs).is_integer():
            yrs = int(yrs)
    except (ValueError, TypeError):
        yrs = None

    sen = data.get("seniority")
    sen = str(sen).strip().lower() if sen and str(sen).strip() else None

    return {
        "skills": _strlist(data.get("skills")),
        "job_titles": _strlist(data.get("job_titles")),
        "seniority": sen,
        "years_experience": yrs,
        "locations": _strlist(data.get("locations")),
        "domains": _strlist(data.get("domains")),
        "target_roles": _strlist(data.get("target_roles"))[:10],
        "model": provider.model,
    }


# The four grade categories, fixed so the UI meters always line up. Keys are
# stable identifiers; labels are what the page shows.
GRADE_CATEGORIES = [
    ("impact", "Impact & metrics"),
    ("ats", "ATS & keywords"),
    ("structure", "Structure & format"),
    ("clarity", "Length & clarity"),
]


def grade_resume(
    resume_text: str,
    target_roles: Optional[list[str]] = None,
    provider: Optional[LLMProvider] = None,
) -> dict:
    """Score a resume 0-100 with a four-category breakdown and concrete,
    prioritized fixes — the data behind the Resumes page "Resume score" card.

    Categories (each 0-25): impact & metrics, ATS & keywords (scored against
    the roles JobBot targets for this user), structure & format, length &
    clarity. Suggestions carry a priority — "fix" (biggest gaps), "improve"
    (worthwhile polish), "good" (something already done well) — and an
    estimated point gain. Defensive like parse_resume: a malformed reply
    yields clamped/safe defaults, never an exception (besides LLMError for
    missing text/provider).
    """
    provider = provider or get_default_provider()
    text = (resume_text or "").strip()
    if not text:
        raise LLMError("No resume text to grade. Upload a resume first.")
    roles = ", ".join(str(r) for r in (target_roles or []) if str(r).strip())

    system = (
        "You are a strict, honest resume coach. Grade the resume for the job "
        "market it targets. Score each category 0-25 (integers; the four sum "
        "to the overall 0-100):\n"
        '- "impact": achievements are QUANTIFIED (numbers, %, $, scale) and '
        "outcome-focused, not duty lists.\n"
        '- "ats": contains the skills/terms employers and parsers look for in '
        "the TARGET ROLES given; standard section headings; no critical "
        "missing keywords.\n"
        '- "structure": clean sections, consistent formatting, parseable '
        "layout (single column, no tables/graphics), sensible ordering.\n"
        '- "clarity": right length for experience level, tight bullets, no '
        "filler; summary is short and specific.\n"
        "Be calibrated: 20-25 = genuinely strong, 13-19 = decent with real "
        "gaps, <13 = weak. Most real resumes land 55-80 overall.\n"
        "Reply with ONE JSON object:\n"
        '{"impact": n, "ats": n, "structure": n, "clarity": n,\n'
        ' "headline": "<=8 words, e.g. \'Strong — a few quick wins left\'",\n'
        ' "suggestions": [3-5 items, ordered most valuable first:\n'
        '   {"priority": "fix"|"improve"|"good", "title": "<=9 words, '
        'imperative", "detail": "1-2 specific sentences quoting or citing the '
        'resume", "where": "a short quote (<=12 words) copied EXACTLY, '
        "word-for-word, from the resume text that this points at; \"\" when it "
        'is about something missing or the document overall", '
        '"points": <estimated overall points gained by doing it; 0 '
        'for "good" items>}\n'
        " ] — include exactly ONE \"good\" item LAST acknowledging what the "
        "resume already does well.}"
    )
    roles_line = roles or "(none parsed yet — judge keywords for the resume's own field)"
    user = (
        f"=== TARGET ROLES (what JobBot matches this person with) ===\n"
        f"{roles_line}\n\n"
        f"=== RESUME ===\n{text[:_BUILDER_CAP]}\n\n"
        "Return the JSON grade now."
    )
    raw = provider.complete(
        system, user, json_mode=True, max_output_tokens=900, temperature=0.2
    )
    grade = coerce_grade(_safe_json(raw))
    grade["model"] = provider.model
    return grade


def coerce_grade(data) -> dict:
    """Defensively shape a resume grade — a fresh model reply (flat category
    keys) or a stored/round-tripped grade_json (nested "categories") — into the
    exact dict the Resume-score card renders. Clamps every number."""
    if not isinstance(data, dict):
        data = {}
    src = data.get("categories") if isinstance(data.get("categories"), dict) else data

    def _cat(key: str) -> int:
        try:
            return max(0, min(25, int(src.get(key))))
        except (TypeError, ValueError):
            return 0

    cats = {key: _cat(key) for key, _label in GRADE_CATEGORIES}

    suggestions: list[dict] = []
    for s in data.get("suggestions") or []:
        if not isinstance(s, dict):
            continue
        pr = str(s.get("priority") or "").strip().lower()
        if pr not in ("fix", "improve", "good"):
            pr = "improve"
        try:
            pts = max(0, min(20, int(s.get("points") or 0)))
        except (TypeError, ValueError):
            pts = 0
        title = _as_text(s.get("title"))
        if not title:
            continue
        suggestions.append(
            {"priority": pr, "title": title, "detail": _as_text(s.get("detail")),
             "where": _as_text(s.get("where"))[:160],
             "points": 0 if pr == "good" else pts}
        )

    return {
        "overall": sum(cats.values()),
        "categories": cats,
        "headline": _as_text(data.get("headline"))[:80] or "Graded",
        "suggestions": suggestions[:6],
        "model": _as_text(data.get("model"))[:80],
    }


def _one_line(value) -> str:
    """Coerce a field meant to be a single line (a list joins with ' · ')."""
    if isinstance(value, list):
        return " · ".join(str(v).strip() for v in value if str(v).strip())
    return str(value or "").strip()


def coerce_paper(data) -> dict:
    """Defensively shape paper JSON — a model reply, or builder state that
    round-tripped through the browser — into exactly what _resume_paper.html
    renders. Length caps keep tampered/degenerate payloads harmless."""
    if not isinstance(data, dict):
        data = {}
    return {
        "name": _as_text(data.get("name"))[:120],
        "headline": _as_text(data.get("headline"))[:200],
        "contact": _one_line(data.get("contact"))[:300],
        "summary": _as_text(data.get("summary"))[:2000],
        "sections": _coerce_sections(data.get("sections")),
    }


def _coerce_changes(value) -> list[dict]:
    """Defensively shape the builder's change log ("what changed & why")."""
    if not isinstance(value, list):
        return []
    changes: list[dict] = []
    for ch in value:
        if isinstance(ch, dict):
            what = _as_text(ch.get("what"))[:400]
            if not what:
                continue
            changes.append({
                "area": _as_text(ch.get("area"))[:80],
                "what": what,
                "why": _as_text(ch.get("why"))[:400],
                "needs_you": bool(ch.get("needs_you")),
            })
        else:  # tolerate a bare string as a change with no area/why
            what = _as_text(ch)[:400]
            if what:
                changes.append({"area": "", "what": what, "why": "", "needs_you": False})
    return changes[:12]


def _coerce_sections(value) -> list[dict]:
    """Defensively shape the model's ``sections`` into a safe list of dicts."""
    if not isinstance(value, list):
        return []
    sections: list[dict] = []
    for sec in value:
        if not isinstance(sec, dict):
            continue
        heading = _as_text(sec.get("heading"))
        entries = _coerce_entries(sec.get("entries"))
        if not heading and not entries:
            continue
        sections.append({"heading": heading, "entries": entries})
    return sections


def _coerce_entries(value) -> list[dict]:
    """Defensively shape a section's ``entries`` into a safe list of dicts."""
    if not isinstance(value, list):
        return []
    entries: list[dict] = []
    for ent in value:
        if not isinstance(ent, dict):
            text = _as_text(ent)  # tolerate a bare string as a single bullet
            if text:
                entries.append({"role": "", "org": "", "dates": "", "bullets": [text]})
            continue
        bullets = ent.get("bullets")
        if isinstance(bullets, str):
            bullets = [bullets]
        if not isinstance(bullets, list):
            bullets = []
        bullets = [str(b).strip() for b in bullets if str(b).strip()]
        entry = {
            "role": _as_text(ent.get("role")),
            "org": _as_text(ent.get("org")),
            "dates": _as_text(ent.get("dates")),
            "bullets": bullets,
        }
        if entry["role"] or entry["org"] or entry["dates"] or entry["bullets"]:
            entries.append(entry)
    return entries


def _as_text(value) -> str:
    """Coerce a model field to display text — a list becomes markdown bullets."""
    if isinstance(value, list):
        return "\n".join(f"- {str(item).strip()}" for item in value if str(item).strip())
    return str(value or "").strip()


def _safe_json(raw: str) -> dict:
    """Parse the model's JSON reply; tolerate stray text or code fences."""
    raw = (raw or "").strip()
    try:
        obj = json.loads(raw)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end > start:
            try:
                obj = json.loads(raw[start : end + 1])
                return obj if isinstance(obj, dict) else {}
            except json.JSONDecodeError:
                pass
    # Last resort: show the raw text as the resume suggestion rather than failing.
    return {"summary": "", "resume": raw, "cover_letter": "", "keywords": []}
