"""
Matches: a Home overview plus a tabbed Matches board, riding on Star.status.

Everything below rides on the EXISTING data model — no schema changes:
- A Match with NO Star row     -> "For you" (undecided), ranked by score.
- Star.status == "interested"  -> "Saved".
- Star.status == "applied"     -> "Applied".
- Star.status == "rejected"    -> "Refused".

Routes:
- GET  /dashboard            -> home.html (greeting, stats, recent matches,
                                resume score, activity feed)
- GET  /matches?tab=         -> matches.html (For you / Saved / Applied / Refused)
- POST /matches/refresh      -> re-run the matcher, flash, back to the board
- POST /matches/{id}/star    -> star/unstar toggle (HTMX swaps just the button)
- POST /matches/{id}/status  -> set/clear the pipeline status for a job
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session as SessionType

from app.matching import compute_and_store_matches
from app.models import Job, Match, Resume, Star, User
from app.web.deps import add_flash, get_db, render, require_user

router = APIRouter()

# "refused" is a real Star status but no longer a browsable tab — a × dismissal
# is permanent (the job just leaves the queue; there's no Refused tab to view/restore).
VALID_TABS = ("foryou", "saved", "applied")
# Star.status value behind each decided tab.
_TAB_STATUS = {"saved": "interested", "applied": "applied", "refused": "rejected"}
_ALLOWED_STATUS = frozenset(_TAB_STATUS.values())  # interested | applied | rejected


def _is_recent(created, cutoff) -> bool:
    """True if a match was created after `cutoff` (its 'New' window)."""
    if created is None:
        return False
    if created.tzinfo is None:  # SQLite returns naive UTC datetimes
        created = created.replace(tzinfo=timezone.utc)
    return created >= cutoff


def _new_cutoff() -> datetime:
    """The 'New' window: anything created in the last 24 hours."""
    return datetime.now(timezone.utc) - timedelta(hours=24)


def _as_utc(dt: datetime | None) -> datetime | None:
    """Normalize a (possibly naive-UTC SQLite) datetime to aware UTC."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _rel_time(dt: datetime | None) -> str:
    """Compact 'time ago' label for feed rows: 'just now', '3h ago', '2d ago'."""
    dt = _as_utc(dt)
    if dt is None:
        return ""
    seconds = int((datetime.now(timezone.utc) - dt).total_seconds())
    if seconds < 60:
        return "just now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    if days < 7:
        return f"{days}d ago"
    weeks = days // 7
    if weeks < 5:
        return f"{weeks}w ago"
    return dt.strftime("%b %d")


# Number of avatar tile colors defined in style.css (.hm-av.c0 … .c5).
_AVATAR_COLORS = 6


def _avatar_idx(name: str | None) -> int:
    """Deterministic color slot for a company's avatar tile (stable across
    restarts, unlike hash())."""
    return sum(ord(ch) for ch in (name or "?").lower()) % _AVATAR_COLORS


_SALARY_SYMBOLS = {"USD": "$", "CAD": "CA$", "AUD": "A$", "EUR": "€", "GBP": "£"}


def _salary_label(job: Job) -> str | None:
    """Compact salary range for a board row, e.g. "$140–175k" / "$106k+".

    Uses the ATS salary_min/salary_max when present, falling back to the
    legacy single `salary` column. Returns None (row shows nothing) when the
    job has no plausible annual figure — never renders junk like "$18".
    """
    lo = job.salary_min or job.salary
    hi = job.salary_max
    if not lo or lo < 10_000:
        return None
    cur = (job.salary_currency or "USD").upper()
    sym = _SALARY_SYMBOLS.get(cur)
    prefix = sym if sym else f"{cur} "
    if hi and hi > lo:
        return f"{prefix}{round(lo / 1000)}–{round(hi / 1000)}k"
    if hi == lo:
        return f"{prefix}{round(lo / 1000)}k"  # exact figure, not open-ended
    return f"{prefix}{round(lo / 1000)}k+"


def _has_resume(db: SessionType, user: User) -> bool:
    return (
        db.query(Resume).filter_by(user_id=user.id, kind="resume").first() is not None
    )


def _load(db: SessionType, user: User):
    """Return (pairs, statuses): all (Match, Job) for the user, best-first.

    Ranking: fit score desc, then most-recently-posted first (undated last),
    then higher salary — so among equally-good matches you see the freshest,
    best-paying roles at the top. Plus a {job_id: Star.status} decision map.
    """
    pairs = (
        db.query(Match, Job)
        .join(Job, Match.job_id == Job.id)
        .filter(Match.user_id == user.id)
        .order_by(
            Match.score.desc(),
            Job.posted_date.is_(None),  # undated jobs after dated ones
            Job.posted_date.desc(),     # most recent first
            Job.salary.is_(None),       # salary-less after priced
            Job.salary.desc(),
        )
        .all()
    )
    statuses = {
        s.job_id: s.status for s in db.query(Star).filter_by(user_id=user.id)
    }
    return pairs, statuses


def _row(match: Match, job: Job, status, cutoff: datetime) -> dict:
    """The shape every template iterates over."""
    return {
        "match": match,
        "job": job,
        "status": status,  # None for "For you", else the Star.status string
        "is_new": _is_recent(match.created_at, cutoff),
    }


def _recent_rows(pairs, statuses, cutoff, limit: int = 5) -> list[dict]:
    """The 5 newest matches (by created_at desc) shaped for the home 'Recent
    matches' list: the usual _row dict plus avatar + relative-time fields."""
    floor = datetime.min.replace(tzinfo=timezone.utc)
    newest = sorted(
        pairs, key=lambda p: _as_utc(p[0].created_at) or floor, reverse=True
    )[:limit]
    rows = []
    for match, job in newest:
        row = _row(match, job, statuses.get(job.id), cutoff)
        label = (job.company or job.title or "").strip()
        row["initial"] = label[:1].upper() or "?"
        row["avatar_idx"] = _avatar_idx(job.company or job.title)
        row["ago"] = _rel_time(match.created_at)
        rows.append(row)
    return rows


def _build_activity(db: SessionType, user: User, pairs, limit: int = 6) -> list[dict]:
    """Recent pipeline events for the home Activity feed, derived from existing
    rows (match ingestions + star decisions) — there is no dedicated events
    table yet.

    TODO: replace with a real activity/events table that records status
    TRANSITIONS. Star has no updated_at, so a job moved e.g. saved -> applied
    keeps its original star timestamp here.
    """
    events = []  # (when, icon, color, text)

    # Star decisions: saved / applied (rejections are skipped as noise).
    star_rows = (
        db.query(Star, Job)
        .join(Job, Star.job_id == Job.id)
        .filter(Star.user_id == user.id)
        .all()
    )
    for star, job in star_rows:
        when = _as_utc(star.created_at)
        if when is None:
            continue
        at_co = f" at {job.company}" if job.company else ""
        if star.status == "applied":
            events.append((when, "check", "green", f"Applied to {job.title}{at_co}"))
        elif star.status == "interested":
            events.append((when, "star", "orange", f"Saved {job.title}{at_co}"))

    # Match ingestions, grouped per UTC day so a refresh reads as one event.
    by_day: dict = {}
    for match, _job in pairs:
        created = _as_utc(match.created_at)
        if created is None:
            continue
        day = created.date()
        count, latest = by_day.get(day, (0, created))
        by_day[day] = (count + 1, max(latest, created))
    for _day, (count, latest) in by_day.items():
        plural = "es" if count != 1 else ""
        events.append((latest, "eye", "blue", f"{count} new match{plural} found"))

    events.sort(key=lambda e: e[0], reverse=True)
    return [
        {"icon": icon, "color": color, "text": text, "ago": _rel_time(when)}
        for when, icon, color, text in events[:limit]
    ]


def _build_chart(pairs) -> list[dict]:
    """Bucket Match.created_at into the last 7 days (oldest -> newest).

    Returns 7 dicts {label, count, pct} where pct is the count scaled 0-100
    against the busiest day (floored at 1 so we never divide by zero).
    """
    today = datetime.now(timezone.utc).date()
    days = [today - timedelta(days=i) for i in range(6, -1, -1)]
    counts = {d: 0 for d in days}
    for match, _job in pairs:
        created = match.created_at
        if created is None:
            continue
        if created.tzinfo is None:  # treat naive as UTC, like _is_recent
            created = created.replace(tzinfo=timezone.utc)
        day = created.astimezone(timezone.utc).date()
        if day in counts:
            counts[day] += 1
    peak = max([*counts.values(), 1])
    return [
        {
            "label": d.strftime("%a"),
            "count": counts[d],
            "pct": int(round(counts[d] / peak * 100)),
        }
        for d in days
    ]


@router.get("/dashboard")
def dashboard(
    request: Request,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Home command center: greeting + notification pill, stat cards, the 5
    newest matches, resume score, and an activity feed."""
    pairs, statuses = _load(db, user)
    cutoff = _new_cutoff()

    # Count decided jobs over the user's MATCHES (job has a Star of that status),
    # so these stats line up exactly with the Matches-board tab counts (which list
    # only matched jobs). Counting raw Star rows could drift if a starred job has
    # no match.
    decided = {"interested": 0, "applied": 0, "rejected": 0}
    for (_m, j) in pairs:
        st = statuses.get(j.id)
        if st in decided:
            decided[st] += 1

    # Fit quality — the stat that actually tells the user what to act on.
    # Bands mirror the AI rubric: 80+ strong, 60-79 good, under 60 fair.
    scores = [m.score for (m, _j) in pairs if m.score is not None]
    strong = sum(1 for s in scores if s >= 80)
    good = sum(1 for s in scores if 60 <= s < 80)
    fair = sum(1 for s in scores if s < 60)
    denom = len(scores) or 1
    fit = {
        "strong": strong, "good": good, "fair": fair, "total": len(scores),
        "strong_pct": round(strong / denom * 100),
        "good_pct": round(good / denom * 100),
        "fair_pct": round(fair / denom * 100),
    }

    stats = {
        "new_today": sum(1 for (m, _j) in pairs if _is_recent(m.created_at, cutoff)),
        "total_matches": len(pairs),
        "strong_count": strong,
        "saved_count": decided["interested"],
        "applied_count": decided["applied"],
        "refused_count": decided["rejected"],
    }

    top_pick = None
    for match, job in pairs:
        if job.id not in statuses:  # first undecided = highest-score "For you"
            top_pick = _row(match, job, None, cutoff)
            break

    # Floating header pill: the single most notable thing right now.
    notif = None
    if stats["new_today"]:
        plural = "es" if stats["new_today"] != 1 else ""
        notif = {
            "text": f"{stats['new_today']} fresh match{plural} today",
            "href": "/matches",
        }
    elif top_pick:
        notif = {
            "text": f"{top_pick['match'].score:.0f}% match: {top_pick['job'].title}",
            "href": f"/jobs/{top_pick['job'].id}",
        }

    has_resume = _has_resume(db, user)

    return render(
        request,
        "home.html",
        user=user,
        has_resume=has_resume,
        stats=stats,
        fit=fit,
        best=top_pick,
        notif=notif,
        recent=_recent_rows(pairs, statuses, cutoff),
        activity=_build_activity(db, user, pairs),
    )


@router.get("/matches")
def matches(
    request: Request,
    tab: str = "foryou",
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """The tabbed board. Each tab lists its rows, ranked by score desc."""
    if tab not in VALID_TABS:
        tab = "foryou"

    pairs, statuses = _load(db, user)
    cutoff = _new_cutoff()
    # Star rows keyed by job, for the Applied tab's "Applied 2d ago" meta.
    stars = {s.job_id: s for s in db.query(Star).filter_by(user_id=user.id)}

    buckets: dict[str, list] = {"foryou": [], "saved": [], "applied": [], "refused": []}
    for match, job in pairs:
        status = statuses.get(job.id)
        row = _row(match, job, status, cutoff)
        # Board-row extras (avatar tile, salary, fit pill, applied meta).
        label = (job.company or job.title or "").strip()
        row["initial"] = label[:1].upper() or "?"
        row["avatar_idx"] = _avatar_idx(job.company or job.title)
        row["salary_label"] = _salary_label(job)
        # Fit pill turns green at the design's "Strong fit" threshold (78),
        # compared on the same rounded value the template displays.
        row["fit_green"] = round(match.score or 0) >= 78
        star = stars.get(job.id)
        row["decided_ago"] = _rel_time(star.created_at) if star else ""
        if status is None:
            buckets["foryou"].append(row)
        elif status == "interested":
            buckets["saved"].append(row)
        elif status == "applied":
            buckets["applied"].append(row)
        elif status == "rejected":
            buckets["refused"].append(row)

    counts = {k: len(v) for k, v in buckets.items()}
    new_today = sum(1 for (m, _j) in pairs if _is_recent(m.created_at, cutoff))

    rows = buckets[tab]
    top_pick = None
    if tab == "foryou" and rows:
        # Render the #1 pick as a hero; keep it out of the list below.
        top_pick = rows[0]
        rows = rows[1:]

    return render(
        request,
        "matches.html",
        user=user,
        tab=tab,
        has_resume=_has_resume(db, user),
        rows=rows,
        counts=counts,
        top_pick=top_pick,
        new_today=new_today,
    )


@router.get("/insights")
def insights(
    request: Request,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Read-only analytics: KPI cards + charts, all derived from existing data."""
    pairs, statuses = _load(db, user)
    cutoff = _new_cutoff()

    # Decided counts over MATCHES (same basis as the home/board stats).
    decided = {"interested": 0, "applied": 0, "rejected": 0}
    for (_m, j) in pairs:
        st = statuses.get(j.id)
        if st in decided:
            decided[st] += 1

    scores = [m.score for (m, _j) in pairs if m.score is not None]
    avg_score = int(round(sum(scores) / len(scores))) if scores else 0

    kpis = {
        "total_matches": len(pairs),
        "new_today": sum(1 for (m, _j) in pairs if _is_recent(m.created_at, cutoff)),
        "saved": decided["interested"],
        "applied": decided["applied"],
        "refused": decided["rejected"],
        "avg_score": avg_score,
    }

    # Top 5 companies by match count (skip blank company names).
    company_counts: dict[str, int] = {}
    for (_m, j) in pairs:
        name = (j.company or "").strip()
        if name:
            company_counts[name] = company_counts.get(name, 0) + 1
    ranked = sorted(company_counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))[:5]
    top_companies = [{"name": n, "count": c} for n, c in ranked]

    # Score distribution into four bands: 0-25 / 25-50 / 50-75 / 75-100.
    band_labels = ["0–25", "25–50", "50–75", "75–100"]
    band_counts = [0, 0, 0, 0]
    for s in scores:
        if s < 25:
            band_counts[0] += 1
        elif s < 50:
            band_counts[1] += 1
        elif s < 75:
            band_counts[2] += 1
        else:
            band_counts[3] += 1
    band_max = max([*band_counts, 1])
    score_bands = [
        {
            "label": band_labels[i],
            "count": band_counts[i],
            "pct": int(round(band_counts[i] / band_max * 100)),
        }
        for i in range(4)
    ]

    return render(
        request,
        "insights.html",
        user=user,
        kpis=kpis,
        chart=_build_chart(pairs),
        top_companies=top_companies,
        score_bands=score_bands,
    )


@router.get("/review")
def review(
    request: Request,
    done: int = 0,  # accepted query param (reserved; queue recomputes each load)
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """A focused, one-at-a-time triage stepper over the 'For you' queue."""
    pairs, statuses = _load(db, user)
    cutoff = _new_cutoff()

    # For-you queue: matches with NO Star, already score-desc from _load.
    queue = [
        _row(match, job, None, cutoff)
        for match, job in pairs
        if job.id not in statuses
    ]
    total = len(pairs)
    remaining = len(queue)
    decided = total - remaining  # pairs that already carry a Star
    progress_pct = int(round(decided / total * 100)) if total else 0

    return render(
        request,
        "review.html",
        user=user,
        current=queue[0] if queue else None,
        remaining=remaining,
        decided=decided,
        total=total,
        progress_pct=progress_pct,
    )


@router.post("/matches/refresh")
def refresh_matches(
    request: Request,
    tab: str = Form(""),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    result = compute_and_store_matches(db, user)
    if result.get("skipped_reason"):
        add_flash(request, f"Couldn't match: {result['skipped_reason']}. "
                           "Upload a resume first.", "error")
    else:
        add_flash(
            request,
            f"Matched {result['stored']} job(s) at or above your "
            f"{result['threshold']}% threshold "
            f"({result['gate_passed']} of {result['total_jobs']} passed your filters).",
            "success",
        )
    dest = tab if tab in VALID_TABS else "foryou"
    return RedirectResponse(f"/matches?tab={dest}", status_code=303)


@router.post("/matches/{job_id}/star")
def toggle_star(
    request: Request,
    job_id: int,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    star = db.query(Star).filter_by(user_id=user.id, job_id=job_id).first()
    if star:
        db.delete(star)
        starred = False
    else:
        db.add(Star(user_id=user.id, job_id=job_id))  # defaults to "interested"
        starred = True
    db.commit()

    # HTMX request -> return just the button so it swaps in place.
    if request.headers.get("HX-Request"):
        return render(request, "_star_button.html", user=user,
                      job_id=job_id, starred=starred)
    return RedirectResponse("/matches", status_code=303)


@router.post("/matches/{job_id}/status")
def set_status(
    request: Request,
    job_id: int,
    status: str = Form(...),
    tab: str = Form(""),
    next: str = Form(""),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Move a job through the pipeline by upserting/deleting its Star.

    - status in {interested, applied, rejected} -> create/update the Star.
    - status in {"", "clear"}                   -> delete the Star (back to For you).
    - anything else                             -> ignored, no change.
    """
    status = (status or "").strip().lower()
    star = db.query(Star).filter_by(user_id=user.id, job_id=job_id).first()

    if status in _ALLOWED_STATUS:
        if star:
            if star.status != status:
                star.status = status
                # created_at doubles as "when the CURRENT status was set", so
                # the Applied tab's "Applied 2d ago" and the home activity
                # feed date the transition, not the first decision.
                star.created_at = datetime.now(timezone.utc)
        elif db.get(Job, job_id) is not None:  # never star a nonexistent job
            db.add(Star(user_id=user.id, job_id=job_id, status=status))
        db.commit()
    elif status in ("", "clear"):
        if star:
            db.delete(star)
            db.commit()
    # unknown status -> ignore safely

    # Additive: the quick-review stepper round-trips here, then back to /review
    # to surface the next undecided card. Everything else keeps the board redirect.
    if next == "review":
        return RedirectResponse("/review", status_code=303)
    # The job page's Application-kit "Mark applied" round-trips back to the job.
    if next == "job":
        return RedirectResponse(f"/jobs/{job_id}", status_code=303)
    # HTMX card actions (the matches grid): empty body so hx-swap="outerHTML"
    # on the card removes it in place — no page reload, the grid reflows.
    if request.headers.get("HX-Request"):
        return HTMLResponse("")
    dest = tab if tab in VALID_TABS else "foryou"
    return RedirectResponse(f"/matches?tab={dest}", status_code=303)
