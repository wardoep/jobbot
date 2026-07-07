"""
The engine: run the gate, then score the survivors, then (optionally) store.

`evaluate_jobs`  — pure function: jobs + filters + resume -> ranked results.
`compute_and_store_matches` — the pipeline step the scheduler (Phase 5) calls:
                  loads a user's stored resume + preferences, evaluates every job,
                  and writes/updates Match rows for those above the user's threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from sqlalchemy.orm import Session as SessionType

from app.models import Job, Match, Resume, Star, User
from app.matching.gate import FilterPrefs, passes_filters
from app.matching.llm_rescore import rescore_survivors
from app.matching.scorer import Scorer, get_default_scorer


@dataclass
class ScoredJob:
    job: Job
    passed: bool
    reason: Optional[str]  # why it was dropped (None if it passed)
    score: float = 0.0  # 0–100, only meaningful when passed=True
    why: Optional[str] = None  # AI's one-sentence fit explanation (LLM layer)


def evaluate_jobs(
    jobs: list[Job],
    prefs: FilterPrefs,
    resume_text: str,
    scorer: Optional[Scorer] = None,
    today: Optional[date] = None,
) -> tuple[list[ScoredJob], list[ScoredJob]]:
    """Return (ranked_survivors, dropped).

    ranked_survivors are sorted best-first by score; dropped keep their reason.
    """
    scorer = scorer or get_default_scorer()
    today = today or date.today()

    survivors: list[ScoredJob] = []
    dropped: list[ScoredJob] = []
    for job in jobs:
        ok, reason = passes_filters(job, prefs, today)
        if ok:
            survivors.append(ScoredJob(job=job, passed=True, reason=None))
        else:
            dropped.append(ScoredJob(job=job, passed=False, reason=reason))

    # Layer two only runs on what cleared the gate.
    if survivors:
        job_texts = [f"{s.job.title or ''} {s.job.description or ''}" for s in survivors]
        scores = scorer.score(resume_text, job_texts)
        for scored, raw in zip(survivors, scores):
            scored.score = round(raw * 100, 1)
        survivors.sort(key=lambda s: s.score, reverse=True)

    return survivors, dropped


def compute_and_store_matches(
    session: SessionType,
    user: User,
    scorer: Optional[Scorer] = None,
    today: Optional[date] = None,
) -> dict:
    """Evaluate all jobs for one user and persist matches above their threshold.

    Returns a small report dict. Safe to run repeatedly: existing Match rows are
    updated in place (we never create a duplicate, and we don't touch
    notified_at — alerts in Phase 5 own that).
    """
    # Resume text = all of the user's uploaded resumes (not cover letters).
    resume_rows = (
        session.query(Resume).filter_by(user_id=user.id, kind="resume").all()
    )
    resume_text = "\n".join(r.raw_text for r in resume_rows if r.raw_text).strip()
    if not resume_text:
        return {"stored": 0, "skipped_reason": "no resume text on file"}

    prefs = FilterPrefs.from_preference(user.preferences)
    # Resume-driven search: the roles the parser judged this resume qualified
    # for become automatic search terms; the user's typed keywords add to them.
    seen: set[str] = {k.lower() for k in prefs.keywords}
    for r in resume_rows:
        for role in (r.parsed_json or {}).get("target_roles") or []:
            role = str(role).strip()
            if role and role.lower() not in seen:
                seen.add(role.lower())
                prefs.auto_keywords.append(role)

    jobs = session.query(Job).all()
    survivors, _dropped = evaluate_jobs(jobs, prefs, resume_text, scorer, today)

    # Layer three: AI fit scores on the top of the ranking (cached; fail-open —
    # any API problem leaves the TF-IDF scores in place). The candidate's home
    # area (preference city, else where the resume says they're based) lets the
    # scorer cap on-site jobs that are far outside commuting distance.
    home_parts: list[str] = []
    pref_row = user.preferences
    if pref_row and pref_row.city:
        home_parts.append(pref_row.city)
    else:
        for r in resume_rows:
            locs = (r.parsed_json or {}).get("locations") or []
            if locs:
                home_parts.append(str(locs[0]))
                break
    if pref_row and pref_row.country:
        home_parts.append(pref_row.country)
    # The candidate's stated preferences (level, employment type, work style)
    # are part of "does this fit" — salary is deliberately NOT included.
    wants_parts: list[str] = []
    if pref_row:
        if pref_row.seniority:
            wants_parts.append(f"{pref_row.seniority}-level roles")
        if pref_row.employment_type:
            wants_parts.append(pref_row.employment_type)
        if pref_row.work_types:
            wants_parts.append(" or ".join(pref_row.work_types))
    llm_scored = rescore_survivors(
        session, survivors, resume_text,
        home=", ".join(home_parts) or None,
        wants=("Wants " + ", ".join(wants_parts)) if wants_parts else None,
    )

    threshold = prefs.match_threshold or 0
    existing = {m.job_id: m for m in session.query(Match).filter_by(user_id=user.id)}
    starred_ids = {s.job_id for s in session.query(Star.job_id).filter_by(user_id=user.id)}

    survivor_ids: set[int] = set()
    stored = 0
    for scored in survivors:
        if scored.score < threshold:
            continue
        survivor_ids.add(scored.job.id)
        match = existing.get(scored.job.id)
        if match is None:
            session.add(
                Match(
                    user_id=user.id,
                    job_id=scored.job.id,
                    score=scored.score,
                    reason=scored.why,
                )
            )
        else:
            match.score = scored.score  # refresh score; keep notified_at
            if scored.why:
                match.reason = scored.why
        stored += 1

    # Prune matches that no longer qualify (e.g. after tightening a filter like
    # country), so the change takes effect immediately — but NEVER drop a job the
    # user has acted on (saved/applied/refused → it has a Star), so their pipeline
    # is preserved.
    pruned = 0
    for job_id, match in existing.items():
        if job_id not in survivor_ids and job_id not in starred_ids:
            session.delete(match)
            pruned += 1

    session.commit()
    return {
        "stored": stored,
        "pruned": pruned,
        "gate_passed": len(survivors),
        "llm_scored": llm_scored,
        "total_jobs": len(jobs),
        "threshold": threshold,
    }
