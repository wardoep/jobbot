"""
LAYER THREE (optional) — AI fit scoring on top of the TF-IDF ranking.

TF-IDF cosine is a word-overlap statistic: it ranks well but its absolute
numbers read low (a great real-world fit lands around 30-50). This module
re-scores the TOP of the TF-IDF ranking with the LLM (same provider Phase 6
uses for tailoring), which reads the resume against each job and returns an
honest 0-100 fit plus a one-sentence why-line for the UI.

Design constraints:
- Engine calls it AFTER the TF-IDF sort; only the top `TOP_K` survivors get
  LLM calls, so cost stays bounded no matter how many jobs pass the gate.
- Every (resume, job) verdict is cached in the `llm_scores` table keyed by
  content hashes — unchanged pairs are free on every later cycle; a new
  resume or an edited job description re-scores automatically.
- Fail-open: any LLM/API problem leaves the TF-IDF scores in place, so
  matching never breaks because the AI is down.

Disable with JOBBOT_LLM_SCORING=0 in the environment/.env.
"""

from __future__ import annotations

import hashlib
import json
import logging

from sqlalchemy.orm import Session as SessionType

from app.config import settings
from app.models import LlmScore

log = logging.getLogger("jobbot.matching.llm")

# How many of the best TF-IDF survivors get true AI scoring per user per run.
TOP_K = settings.llm_top_k
# Jobs per API call (the batch shares one prompt to keep cost/latency down).
_BATCH = 8
# Prompt caps, mirroring app/assist.py.
_RESUME_CAP = 6000
_JOB_CAP = 3500

# Bump when the prompt's judging standard changes: it's folded into the cache
# key, so every cached verdict re-scores under the new standard.
_PROMPT_VERSION = "v3-level-fit"

_SYSTEM = (
    "You are a blunt, honest, STRICT technical recruiter. You will get ONE "
    "candidate resume and a numbered list of jobs. For EACH job, judge how "
    "well the candidate fits it on a 0-100 scale:\n"
    "  85-100 exceptional fit (meets EVERY stated requirement including years "
    "of experience — rare; a candidate below the asked experience level "
    "cannot score here)\n"
    "  70-84  strong fit (meets the core requirements with only minor gaps)\n"
    "  50-69  partial fit (right field, but real gaps in requirements, "
    "experience, or specific tools)\n"
    "  30-49  weak fit (wrong seniority or mostly missing skills)\n"
    "  0-29   poor fit (different field)\n"
    "DIFFERENTIATE: the jobs in a batch are competing for rank — score the "
    "candidate's fit for each independently and precisely, using the full "
    "0-100 granularity (e.g. 58, 63, 71). Do NOT snap to round numbers or "
    "give several jobs the same score unless their requirements are truly "
    "interchangeable. Weigh each job's specific demands (years required, "
    "tools named, certifications, shift/clearance requirements).\n"
    "LEVEL ALIGNMENT — fit means the job suits WHO THIS CANDIDATE IS TODAY: "
    "an entry-level/junior posting that asks for what the candidate already "
    "has is an EXCELLENT fit — score it 85+ and never subtract points for "
    "'limited experience' when the job doesn't require more. Judge only "
    "against requirements the posting actually states; missing stated "
    "requirements subtract heavily, absent ones subtract nothing. Salary "
    "must never influence the score.\n"
    "PREFERENCES: the candidate's stated preferences are given in the "
    "request. A job that conflicts with them (e.g. a senior role when they "
    "want junior, contract when they want full-time) fits worse — subtract "
    "accordingly and say so in the why-line.\n"
    "Judge resume evidence vs job requirements — ignore salary. LOCATION "
    "RULE: for REMOTE jobs ignore location entirely; for ON-SITE or HYBRID "
    "jobs, if the posting's location is clearly beyond a reasonable commute "
    "(~50 miles) of the candidate's home area, cap the score at 25 and name "
    "the location gap in the why-line. If the job's location or the home "
    "area is unknown, do not penalize. "
    "Be calibrated: most real matches are partial, not exceptional. "
    'Reply with a single JSON object {"scores": [{"i": <job number>, '
    '"score": <0-100 integer>, "why": "<ONE short sentence naming the '
    "candidate's matching strengths and the biggest gap, written to the "
    'candidate as \'you/your\'>"}, ...]} covering every job exactly once.'
)


def enabled() -> bool:
    return settings.llm_scoring_enabled


def _sha(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()


def _job_text(job) -> str:
    parts = [f"Title: {job.title or '(untitled)'}"]
    if job.company:
        parts.append(f"Company: {job.company}")
    loc = ", ".join(x for x in [job.location, job.country] if x)
    parts.append(f"Location: {loc or 'unknown'} ({job.work_type or 'work type unknown'})")
    desc = (job.description or "").strip()[:_JOB_CAP]
    parts.append(f"Description: {desc or '(none)'}")
    return "\n".join(parts)


def _score_batch(
    provider, resume_text: str, batch: list, home: str | None, wants: str | None
) -> dict[int, tuple[float, str]]:
    """One API call for up to _BATCH jobs -> {list index: (score, why)}."""
    numbered = "\n\n".join(
        f"=== JOB {i + 1} ===\n{_job_text(s.job)}" for i, s in enumerate(batch)
    )
    user = (
        f"=== CANDIDATE HOME AREA ===\n{home or 'unknown'}\n\n"
        f"=== CANDIDATE PREFERENCES ===\n{wants or '(none stated)'}\n\n"
        f"=== CANDIDATE RESUME ===\n{resume_text[:_RESUME_CAP]}\n\n"
        f"{numbered}\n\n"
        f"Score all {len(batch)} jobs as the JSON described."
    )
    raw = provider.complete(
        _SYSTEM, user, json_mode=True, max_output_tokens=220 * len(batch), temperature=0.0
    )
    data = json.loads(raw)
    out: dict[int, tuple[float, str]] = {}
    for row in data.get("scores", []):
        try:
            idx = int(row["i"]) - 1
            score = max(0.0, min(100.0, float(row["score"])))
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= idx < len(batch):
            out[idx] = (score, str(row.get("why") or "").strip()[:300])
    return out


def rescore_survivors(
    session: SessionType,
    survivors: list,
    resume_text: str,
    home: str | None = None,
    wants: str | None = None,
) -> int:
    """Replace TF-IDF scores with AI fit scores on the top TOP_K survivors.

    Mutates each ScoredJob's .score (0-100) and .why in place, then re-sorts
    the rescored head best-first. Returns how many jobs got an LLM score (from
    cache or fresh); 0 means nothing changed (disabled, empty, or API failure).
    """
    if not enabled() or not survivors:
        return 0

    head = survivors[:TOP_K]
    # home, preferences and the prompt version are part of the verdict, so
    # they're part of the cache key — changing any re-judges everything once.
    resume_hash = _sha(
        f"{resume_text}\nHOME:{home or ''}\nWANTS:{wants or ''}\nPROMPT:{_PROMPT_VERSION}"
    )

    cached = {
        row.job_id: row
        for row in session.query(LlmScore)
        .filter(LlmScore.resume_hash == resume_hash)
        .filter(LlmScore.job_id.in_([s.job.id for s in head]))
        .all()
    }

    misses = []
    for s in head:
        hit = cached.get(s.job.id)
        if hit is not None and hit.job_hash == _sha(_job_text(s.job)):
            s.score = hit.score
            s.why = hit.reason or None
        else:
            misses.append(s)

    scored = len(head) - len(misses)
    if misses:
        try:
            from app.llm import get_default_provider

            provider = get_default_provider()
        except Exception as exc:  # no API key configured, etc.
            log.warning("LLM scoring unavailable (%s); keeping TF-IDF scores", exc)
            return 0

        from app.llm_budget import month_usage, try_spend

        for start in range(0, len(misses), _BATCH):
            batch = misses[start : start + _BATCH]
            if not try_spend(session, 1):
                used, cap = month_usage(session)
                log.warning(
                    "monthly LLM cap reached (%d/%d calls) — %d job(s) keep "
                    "TF-IDF scores until next month or a higher "
                    "JOBBOT_LLM_MONTHLY_CAP",
                    used, cap, len(misses) - start,
                )
                break
            try:
                verdicts = _score_batch(provider, resume_text, batch, home, wants)
            except Exception as exc:
                # Fail-open: this batch keeps its TF-IDF scores; try the next.
                log.warning("LLM scoring batch failed (%s); keeping TF-IDF scores", exc)
                continue
            for idx, (score, why) in verdicts.items():
                s = batch[idx]
                s.score = round(score, 1)
                s.why = why or None
                # Upsert by (resume_hash, job_id): refresh a stale row in place.
                row = cached.get(s.job.id)
                if row is None:
                    row = LlmScore(job_id=s.job.id, resume_hash=resume_hash)
                    session.add(row)
                    cached[s.job.id] = row
                row.job_hash = _sha(_job_text(s.job))
                row.score = s.score
                row.reason = why
                row.model = provider.model
                scored += 1
        session.commit()

    # Keep best-first order now that the head is on the new scale.
    survivors.sort(key=lambda s: s.score, reverse=True)
    return scored
