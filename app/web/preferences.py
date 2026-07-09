"""
The per-user search preferences form (the hard filters + alert settings).

Every field is optional; blank means "any". On save we write a single Preference
row per user (the table's primary key is user_id, so it's one-to-one).
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, Form, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session as SessionType

from app.models import Preference, User
from app.web.deps import add_flash, get_db, render, require_user

router = APIRouter(prefix="/preferences")

# Choices offered in the dropdowns (kept here so the template stays simple).
COUNTRIES = ["USA", "UK", "Canada", "Australia", "Germany", "France", "India",
             "Netherlands", "Italy", "Spain", "Poland", "Brazil", "Singapore",
             "New Zealand"]
WORK_TYPES = ["Remote", "Hybrid", "In-person"]
# (abbr, label) for the State selector — US states then Canadian provinces.
STATES = [
    ("al", "Alabama"), ("ak", "Alaska"), ("az", "Arizona"), ("ar", "Arkansas"),
    ("ca", "California"), ("co", "Colorado"), ("ct", "Connecticut"), ("de", "Delaware"),
    ("fl", "Florida"), ("ga", "Georgia"), ("hi", "Hawaii"), ("id", "Idaho"),
    ("il", "Illinois"), ("in", "Indiana"), ("ia", "Iowa"), ("ks", "Kansas"),
    ("ky", "Kentucky"), ("la", "Louisiana"), ("me", "Maine"), ("md", "Maryland"),
    ("ma", "Massachusetts"), ("mi", "Michigan"), ("mn", "Minnesota"), ("ms", "Mississippi"),
    ("mo", "Missouri"), ("mt", "Montana"), ("ne", "Nebraska"), ("nv", "Nevada"),
    ("nh", "New Hampshire"), ("nj", "New Jersey"), ("nm", "New Mexico"), ("ny", "New York"),
    ("nc", "North Carolina"), ("nd", "North Dakota"), ("oh", "Ohio"), ("ok", "Oklahoma"),
    ("or", "Oregon"), ("pa", "Pennsylvania"), ("ri", "Rhode Island"), ("sc", "South Carolina"),
    ("sd", "South Dakota"), ("tn", "Tennessee"), ("tx", "Texas"), ("ut", "Utah"),
    ("vt", "Vermont"), ("va", "Virginia"), ("wa", "Washington"), ("wv", "West Virginia"),
    ("wi", "Wisconsin"), ("wy", "Wyoming"), ("dc", "Washington, D.C."),
    ("ab", "Alberta"), ("bc", "British Columbia"), ("mb", "Manitoba"), ("nb", "New Brunswick"),
    ("nl", "Newfoundland & Labrador"), ("ns", "Nova Scotia"), ("on", "Ontario"),
    ("pe", "Prince Edward Island"), ("qc", "Quebec"), ("sk", "Saskatchewan"),
    ("nt", "Northwest Territories"), ("nu", "Nunavut"), ("yt", "Yukon"),
]
EMPLOYMENT_TYPES = ["full-time", "part-time", "contract", "internship"]
RADIUS_PRESETS = [("", "Any distance"), ("10", "10 miles"), ("25", "25 miles"),
                  ("50", "50 miles"), ("100", "100 miles"), ("250", "250 miles")]
SENIORITIES = ["intern", "junior", "mid", "senior", "lead"]
POSTED_WITHIN = [("", "Any time"), ("1", "Today"), ("3", "Last 3 days"),
                 ("7", "Last week"), ("14", "Last 2 weeks"), ("30", "Last month")]
ALERT_CHANNELS = ["email", "dashboard", "slack"]

# Curated keyword-discovery suggestions, grouped by category (the design's
# suggestion panel). These are generic "ideas to add", NOT personalized — the
# personalized row comes from the user's own parsed resume (see _resume_skills).
KEYWORD_CATEGORIES = [
    ("Software Engineering",
     ["Software Engineer", "Backend", "Frontend", "Full-stack", "Python", "JavaScript",
      "TypeScript", "React", "Node.js", "Go", "Java", "Kubernetes", "AWS", "DevOps"]),
    ("Data & AI",
     ["Data Engineer", "Data Scientist", "Data Analyst", "SQL", "Machine Learning",
      "LLM", "PyTorch", "Analytics", "ETL", "Spark", "NLP"]),
    ("Product & Design",
     ["Product Manager", "Product Designer", "UX", "UI", "Figma", "User Research",
      "Design Systems"]),
    ("Marketing & Growth",
     ["Growth", "SEO", "Content Marketing", "Demand Generation", "Lifecycle",
      "Brand", "Performance Marketing"]),
    ("Seniority & Type",
     ["Junior", "Senior", "Staff", "Lead", "Principal", "Manager",
      "Remote", "Contract", "Full-time", "Internship"]),
]
MAX_KEYWORDS = 40


def _resume_skills(db: SessionType, user: User) -> list[str]:
    """The skills from the user's most-recent PARSED resume (parsed_json.skills).

    Real data only — returns [] when the user has no parsed resume yet, so the
    template hides the "Based on your resume" row rather than showing fake chips.
    """
    from app.models import Resume

    doc = (
        db.query(Resume)
        .filter_by(user_id=user.id, kind="resume")
        .filter(Resume.parsed_json.isnot(None))
        .order_by(Resume.uploaded_at.desc())
        .first()
    )
    if not doc or not isinstance(doc.parsed_json, dict):
        return []
    skills = doc.parsed_json.get("skills") or []
    out, seen = [], set()
    for s in skills:
        s = str(s).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    return out[:24]


def _panel_ctx(db: SessionType, user: User, details_open: bool | None = None) -> dict:
    """Context for the keyword panel partial (current keywords + suggestions).

    `details_open` controls whether the "Not sure what to add?" disclosure renders
    open. Default (None): open for a brand-new user with no keywords, collapsed once
    they have some. The add/remove endpoints pass the panel's current open state so a
    chip click never silently collapses the list.
    """
    pref = db.get(Preference, user.id)
    keywords = list(pref.keywords or []) if pref else []
    if details_open is None:
        details_open = not keywords
    # Roles the matcher searches AUTOMATICALLY, straight from the parsed
    # resume (target_roles) — shown read-only so it's clear typed keywords
    # only fine-tune on top of these.
    from app.models import Resume

    auto_roles: list[str] = []
    seen: set[str] = set()
    rows = db.query(Resume).filter_by(user_id=user.id, kind="resume").all()
    for r in rows:
        for role in (r.parsed_json or {}).get("target_roles") or []:
            role = str(role).strip()
            if role and role.lower() not in seen:
                seen.add(role.lower())
                auto_roles.append(role)
    return {
        "keywords": keywords,
        "auto_roles": auto_roles,
        "resume_skills": _resume_skills(db, user),
        "categories": KEYWORD_CATEGORIES,
        "details_open": details_open,
    }


# Location strings that aren't cities — filtered out of the suggestions.
@router.get("")
def preferences_page(
    request: Request,
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    pref = db.get(Preference, user.id)
    # State is a separate field now; city is stored/shown plain (no ", ST").
    # Migrate older prefs that embedded the state in the city string.
    from app.matching.geo import region_of

    sel_state = (pref.state if pref and pref.state else None) or (
        region_of(pref.city) if pref and pref.city else None
    ) or ""
    city_display = (pref.city.split(",")[0].strip() if pref and pref.city else "")
    return render(
        request, "preferences.html", user=user, pref=pref,
        countries=COUNTRIES, states=STATES, work_types_all=WORK_TYPES,
        employment_types=EMPLOYMENT_TYPES, seniorities=SENIORITIES,
        posted_within=POSTED_WITHIN, channels_all=ALERT_CHANNELS,
        radius_presets=RADIUS_PRESETS, sel_state=sel_state, city_display=city_display,
        **_panel_ctx(db, user),
    )


# A broad, field-agnostic keyword/skill vocabulary for the autocomplete on the
# Keywords / Exclude-keywords fields (users can still type anything).
SKILLS_VOCAB = sorted({
    # IT / support
    "help desk", "it support", "desktop support", "technical support",
    "system administrator", "network administrator", "network technician",
    "service desk", "field technician", "it technician", "it specialist",
    "support specialist", "sysadmin", "help desk analyst", "help desk technician",
    "active directory", "office 365", "windows", "linux", "tcp/ip", "vpn",
    "ticketing", "servicenow", "troubleshooting", "hardware", "networking",
    "cybersecurity", "information security", "soc analyst", "cloud", "azure",
    # software / data
    "software engineer", "backend", "frontend", "full-stack", "python",
    "javascript", "typescript", "react", "node.js", "java", "go", "c#", "sql",
    "aws", "kubernetes", "docker", "devops", "data analyst", "data engineer",
    "data scientist", "machine learning", "analytics", "power bi", "tableau",
    "excel", "etl", "business intelligence",
    # business / ops / other fields
    "project manager", "business analyst", "operations", "customer service",
    "account executive", "sales", "marketing", "content", "seo", "recruiter",
    "human resources", "accountant", "bookkeeper", "financial analyst",
    "administrative assistant", "office manager", "paralegal", "legal assistant",
    "registered nurse", "medical assistant", "pharmacist", "caregiver",
    "teacher", "tutor", "warehouse", "logistics", "supply chain", "driver",
    "electrician", "hvac", "mechanic", "welder", "retail", "cashier",
    "receptionist", "graphic designer", "ux designer", "product manager",
    # employment qualifiers people often exclude
    "contract", "unpaid", "commission", "internship", "clearance", "bilingual",
})


@router.get("/skills")
def skill_suggest(q: str = "", user: User = Depends(require_user)):
    """Keyword/skill autocomplete — the curated vocab, prefix-matched."""
    ql = q.strip().lower()
    if len(ql) < 1:
        return JSONResponse([])
    hits = [s for s in SKILLS_VOCAB if s.startswith(ql)]
    hits += [s for s in SKILLS_VOCAB if ql in s and s not in hits]
    return JSONResponse(hits[:15])


@router.get("/companies")
def company_suggest(
    q: str = "", user: User = Depends(require_user), db: SessionType = Depends(get_db)
):
    """Company autocomplete drawn from real employer names in the job pool."""
    ql = q.strip()
    if len(ql) < 2:
        return JSONResponse([])
    rows = db.execute(sa_text(
        """
        SELECT company, count(*) n FROM jobs
        WHERE company IS NOT NULL AND company != '' AND lower(company) LIKE :pat
        GROUP BY company ORDER BY n DESC LIMIT 15
        """
    ), {"pat": ql.lower() + "%"}).fetchall()
    return JSONResponse([r[0] for r in rows])


@router.get("/geolocate")
def geolocate(
    lat: float = 0.0,
    lng: float = 0.0,
    user: User = Depends(require_user),
):
    """Reverse-geocode browser coordinates to {city, state, country} using the
    bundled offline dataset — nothing is stored and nothing leaves the server.
    Powers the "Use my location" button on this page."""
    from app.matching.geo import nearest_city

    if not lat and not lng:
        return JSONResponse({"ok": False, "error": "no coordinates"}, status_code=400)
    hit = nearest_city(lat, lng)
    if hit is None:
        return JSONResponse(
            {"ok": False, "error": "Couldn't place you — the location list covers the US and Canada."}
        )
    return JSONResponse({
        "ok": True,
        "city": hit["city"],
        "state": hit["state"],
        "country": {"US": "USA", "CA": "Canada"}.get(hit["country"], ""),
    })


@router.get("/cities")
def city_suggest(
    q: str = "",
    country: str = "",
    state: str = "",
    user: User = Depends(require_user),
):
    """Live city autocomplete. With a state, returns plain city names limited to
    that state (the state is chosen separately); without one, "City, ST"."""
    from app.matching.geo import search_cities

    return JSONResponse(search_cities(q, country or None, limit=20, state=state or None))


@router.post("")
def save_preferences(
    request: Request,
    background: BackgroundTasks,
    country: str = Form(""),
    state: str = Form(""),
    city: str = Form(""),
    radius_miles: str = Form(""),
    work_types: list[str] = Form([]),
    posted_within_days: str = Form(""),
    keywords: str = Form(""),
    exclude_keywords: str = Form(""),
    block_companies: str = Form(""),
    exclude_staffing: str = Form(""),
    salary_min: str = Form(""),
    employment_type: str = Form(""),
    seniority: str = Form(""),
    match_threshold: str = Form("0"),
    alert_channels: list[str] = Form([]),
    digest_mode: str = Form("digest"),
    slack_webhook: str = Form(""),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    pref = db.get(Preference, user.id)
    if pref is None:
        pref = Preference(user_id=user.id)
        db.add(pref)

    pref.country = country.strip() or None
    pref.state = state.strip().lower() or None
    # City is stored plain (no ", ST"); the separate state disambiguates it.
    # A city with no state selected is meaningless, so it's cleared.
    pref.city = (city.split(",")[0].strip() or None) if pref.state else None
    pref.radius_miles = _int_or_none(radius_miles)
    pref.work_types = [w for w in work_types if w] or None  # single-select dropdown
    pref.posted_within_days = _int_or_none(posted_within_days)
    pref.keywords = _split_keywords(keywords) or None
    # Power filters are Premium-only to EDIT: on a free account the posted
    # fields are ignored and whatever is already stored keeps working (a
    # downgrade never silently changes someone's matching).
    from app.web.deps import is_premium

    if is_premium(user):
        pref.exclude_keywords = _split_keywords(exclude_keywords) or None
        pref.block_companies = _split_keywords(block_companies) or None
        pref.exclude_staffing = bool(exclude_staffing)
        pref.salary_min = _int_or_none(salary_min)
    pref.employment_type = employment_type.strip() or None
    pref.seniority = seniority.strip() or None
    pref.match_threshold = _int_or_none(match_threshold) or 0
    # Alerts dropdown is single-select; dashboard is always on (matches show
    # in-app), email/telegram are the real opt-ins.
    _sel = next((c for c in alert_channels if c), "dashboard")
    pref.alert_channels = {
        "dashboard": ["dashboard"],
        "email": ["email", "dashboard"],
        "telegram": ["telegram", "dashboard"],
        "email+telegram": ["email", "telegram", "dashboard"],
    }.get(_sel, ["dashboard"])
    pref.digest_mode = digest_mode or "digest"
    pref.slack_webhook = slack_webhook.strip() or None

    db.commit()
    # Re-match in the background so the board reflects the new preferences
    # right away — no need to hit "Refresh my matches" separately.
    background.add_task(_rematch_user, user.id)
    add_flash(request, "Preferences saved — updating your matches…", "success")
    return RedirectResponse("/preferences", status_code=303)


def _rematch_user(user_id: int) -> None:
    """Recompute a user's matches (own DB session; safe to run detached)."""
    from app.db import Session as _S
    from app.matching.engine import compute_and_store_matches

    try:
        with _S() as s:
            u = s.get(User, user_id)
            if u:
                compute_and_store_matches(s, u)
    except Exception:  # noqa: BLE001 — a background failure must not surface
        import logging

        logging.getLogger("jobbot.web").exception("rematch after prefs save failed")


def _upsert_pref(db: SessionType, user: User) -> Preference:
    pref = db.get(Preference, user.id)
    if pref is None:
        pref = Preference(user_id=user.id)
        db.add(pref)
    return pref


@router.post("/keywords/add")
def add_keyword(
    request: Request,
    kw: str = Form(""),
    open: str = Form("1"),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Add one keyword to preferences.keywords immediately; return the panel partial."""
    kw = (kw or "").strip()
    if kw:
        pref = _upsert_pref(db, user)
        kws = list(pref.keywords or [])
        if kw.lower() not in {k.lower() for k in kws}:
            kws.append(kw)
        pref.keywords = kws[:MAX_KEYWORDS]
        db.commit()
    return render(request, "_keyword_panel.html", user=user,
                  **_panel_ctx(db, user, details_open=open != "0"))


@router.post("/keywords/remove")
def remove_keyword(
    request: Request,
    kw: str = Form(""),
    open: str = Form("1"),
    user: User = Depends(require_user),
    db: SessionType = Depends(get_db),
):
    """Remove one keyword from preferences.keywords immediately; return the panel."""
    kw = (kw or "").strip().lower()
    pref = db.get(Preference, user.id)
    if pref and pref.keywords:
        pref.keywords = [k for k in pref.keywords if k.lower() != kw] or None
        db.commit()
    return render(request, "_keyword_panel.html", user=user,
                  **_panel_ctx(db, user, details_open=open != "0"))


def _int_or_none(value: str):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(float(value))
    except ValueError:
        return None


def _split_keywords(value: str) -> list[str]:
    return [k.strip() for k in (value or "").split(",") if k.strip()]
