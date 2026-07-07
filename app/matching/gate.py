"""
LAYER ONE — the hard-filter gate.

`passes_filters(job, prefs)` returns (True, None) if the job clears EVERY filter
the user set, or (False, reason) explaining the first filter it failed.

Guiding rules:
  * Blank filter  -> skipped (treated as "any").
  * We drop a job ONLY when it has a KNOWN value that conflicts with a filter.
    If the job's value is unknown (e.g. a remote board doesn't report a country),
    we DON'T silently drop it — we can't prove a violation, so it passes. This
    matches our "never guess work_type" stance from ingestion.

Some preferences (employment_type, seniority) aren't stored as structured columns,
so we infer them from the job's title/description as a best effort.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from app.matching.geo import distance_miles, region_of, state_from
from app.models import Job, Preference


@dataclass
class FilterPrefs:
    """A plain bag of filters (mirrors the Preference table, but decoupled from
    the DB so the CLI can build one from flags too)."""

    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    radius_miles: Optional[int] = None
    work_types: list[str] = field(default_factory=list)
    posted_within_days: Optional[int] = None
    salary_min: Optional[int] = None
    employment_type: Optional[str] = None
    seniority: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    must_have_keywords: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    block_companies: list[str] = field(default_factory=list)
    exclude_staffing: bool = False
    # Search terms derived from the RESUME (parsed target_roles), not typed by
    # the user. The engine fills this in; user keywords add to it (OR), and
    # exclude_keywords carve away from it.
    auto_keywords: list[str] = field(default_factory=list)
    match_threshold: int = 0

    @classmethod
    def from_preference(cls, pref: Optional[Preference]) -> "FilterPrefs":
        if pref is None:
            return cls()
        return cls(
            country=pref.country,
            state=pref.state,
            city=pref.city,
            radius_miles=pref.radius_miles,
            work_types=list(pref.work_types or []),
            posted_within_days=pref.posted_within_days,
            salary_min=pref.salary_min,
            employment_type=pref.employment_type,
            seniority=pref.seniority,
            keywords=list(pref.keywords or []),
            must_have_keywords=list(pref.must_have_keywords or []),
            exclude_keywords=list(pref.exclude_keywords or []),
            block_companies=list(pref.block_companies or []),
            exclude_staffing=bool(pref.exclude_staffing),
            match_threshold=pref.match_threshold or 0,
        )


def passes_filters(
    job: Job, prefs: FilterPrefs, today: Optional[date] = None
) -> tuple[bool, Optional[str]]:
    today = today or date.today()
    text = f"{job.title or ''} {job.description or ''}"

    # --- country (STRICT: only jobs explicitly in the chosen country) -------
    # The user asked to see ONLY their country's jobs, so a set country requires
    # the job to declare a matching country. Name variants are normalized
    # ("USA" == "United States", "UK" == "United Kingdom", etc.).
    # Some sources (Greenhouse/Ashby ATS feeds, remote boards) never set a
    # country even when the location text names one ("San Francisco, CA",
    # "Remote - United States"), so a missing country falls back to inferring
    # it from the location. Only a job whose country stays unknown after that
    # is dropped — same strict stance, without hiding clearly-in-country jobs.
    if prefs.country:
        want = _canon_country(prefs.country)
        if job.country:
            if _canon_country(job.country) != want:
                return False, f"country {job.country} ≠ {prefs.country}"
        elif want not in infer_countries_from_location(job.location):
            return False, f"country unknown/≠ {prefs.country} (location: {job.location or 'n/a'})"

    # --- work type ----------------------------------------------------------
    if prefs.work_types and job.work_type:
        if job.work_type not in prefs.work_types:
            return False, f"work type {job.work_type} not in {prefs.work_types}"

    # --- posted within N days ----------------------------------------------
    # Use the posted date; when a source omits it, fall back to when WE first
    # found the job (fetched_at) — a just-discovered listing is effectively new.
    if prefs.posted_within_days is not None:
        d = job.posted_date
        if d is None and job.fetched_at is not None:
            d = job.fetched_at.date()
        if d is not None and (today - d).days > prefs.posted_within_days:
            return False, f"posted/found {(today - d).days}d ago > {prefs.posted_within_days}d"

    # --- salary minimum -----------------------------------------------------
    if prefs.salary_min is not None and job.salary is not None:
        if job.salary < prefs.salary_min:
            return False, f"salary {job.salary} < {prefs.salary_min}"

    # --- keywords / role titles (job must match at least one) --------------
    # Resume-derived roles (auto_keywords) and the user's own keywords form
    # ONE pool: a job passes by matching ANY of them. Typed keywords therefore
    # BROADEN the automatic resume-driven search, never narrow it.
    # Auto roles are matched against the TITLE only — role phrases like
    # "technical support" appear in the fine print of countless unrelated
    # postings; typed keywords keep their original title+description reach.
    if prefs.keywords or prefs.auto_keywords:
        blob = text.lower()
        title = (job.title or "").lower()
        # Typed keywords match anywhere (title or description).
        hit = any(kw.lower() in blob for kw in prefs.keywords)
        # Resume roles match the TITLE by the full phrase OR any significant
        # word (>=4 chars) — so "Desktop Support Analyst" matches "technical
        # support" via "support" and "IT Specialist / Field Technician" get in.
        # Broader net; the AI scorer then ranks quality so weak fits sink.
        if not hit:
            for role in prefs.auto_keywords:
                rl = role.lower().strip()
                if rl and (rl in title or any(len(w) >= 4 and w in title for w in rl.split())):
                    hit = True
                    break
        if not hit:
            return False, "no keyword/role match"

    # --- must-have keywords (job must mention ALL of them) -----------------
    if prefs.must_have_keywords:
        blob = text.lower()
        for kw in prefs.must_have_keywords:
            k = kw.lower().strip()
            if k and k not in blob:
                return False, f"missing must-have '{kw}'"

    # --- excluded keywords (any hit disqualifies the job) ------------------
    if prefs.exclude_keywords:
        blob = text.lower()
        for kw in prefs.exclude_keywords:
            k = kw.lower().strip()
            if k and k in blob:
                return False, f"excluded keyword '{kw}'"

    # --- blocked companies + staffing/recruiter agencies -------------------
    company = (job.company or "").lower()
    if company and prefs.block_companies:
        for c in prefs.block_companies:
            c = c.lower().strip()
            if c and c in company:
                return False, f"blocked company '{job.company}'"
    if company and prefs.exclude_staffing and _is_staffing(company):
        return False, f"staffing/recruiter agency '{job.company}'"

    # --- employment type (best-effort from text) ---------------------------
    if prefs.employment_type:
        found = infer_employment_type(text)
        if found is not None and found != _canon_employment(prefs.employment_type):
            return False, f"employment type {found} ≠ {prefs.employment_type}"

    # --- seniority (best-effort from the TITLE only) -----------------------
    # Seniority lives in the title ("Senior Data Analyst"). Scanning the whole
    # description would false-positive on verbs like "lead the team".
    if prefs.seniority:
        found = infer_seniority(job.title or "")
        if found is not None and found != _canon_seniority(prefs.seniority):
            return False, f"seniority {found} ≠ {prefs.seniority}"

    # --- location -----------------------------------------------------------
    # Remote jobs (work type says so, or the text reads remote) ALWAYS pass, so
    # location prefs never hide remote roles. Everything else is a commute job:
    #   * State set -> its region must be the chosen state (unknown region drops
    #     too, so nothing out-of-state slips through on a vague location).
    #   * City + mile radius -> must be within that many miles; a location we
    #     can't pin down is dropped (STRICT — no vague far jobs leak in).
    #   * City, no radius -> same state/province as the city (region level).
    if not _is_remote(job):
        want_state = (prefs.state or "").strip().lower() or (
            region_of(prefs.city) if prefs.city else None
        )
        # The city is stored plain now; pair it with the state so it geocodes
        # unambiguously ("St. Charles" + "ny" -> "St. Charles, IL").
        user_loc = prefs.city or ""
        if prefs.city and want_state and region_of(prefs.city) is None:
            user_loc = f"{prefs.city}, {want_state.upper()}"
        if want_state:
            have_state = state_from(job.location or "", prefs.country) or region_of(job.location or "")
            if prefs.radius_miles and prefs.city:
                dist = distance_miles(user_loc, job.location or "", prefs.country)
                if dist is None:
                    return False, f"location '{job.location}' can't be placed within {prefs.radius_miles}mi"
                if dist > prefs.radius_miles:
                    return False, f"{job.location} ~{round(dist)}mi from {prefs.city} (> {prefs.radius_miles}mi)"
            elif have_state and have_state != want_state:
                return False, f"{job.location} not in {want_state.upper()}"
            elif prefs.state and not have_state:
                # An explicit state filter is strict: unplaceable -> drop.
                return False, f"location '{job.location}' not confirmed in {prefs.state.upper()}"

    return True, None


# ---------------------------------------------------------------------------
# Best-effort inference helpers
# ---------------------------------------------------------------------------
_SENIORITY_PATTERNS = [
    ("lead", r"\b(lead|principal|staff|head of|director)\b"),
    ("senior", r"\b(senior|sr\.?|expert)\b"),
    ("junior", r"\b(junior|jr\.?|entry[- ]?level|associate|graduate)\b"),
    ("intern", r"\b(intern|internship|trainee)\b"),
    ("mid", r"\b(mid[- ]?level|intermediate)\b"),
]


def infer_seniority(text: str) -> Optional[str]:
    """Guess intern/junior/mid/senior/lead from text, or None if unclear."""
    low = text.lower()
    for label, pattern in _SENIORITY_PATTERNS:
        if re.search(pattern, low):
            return label
    return None


_EMPLOYMENT_PATTERNS = [
    ("internship", r"\b(internship|intern)\b"),
    ("contract", r"\b(contract|contractor|freelance|temporary|temp)\b"),
    ("part-time", r"\bpart[- ]?time\b"),
    ("full-time", r"\bfull[- ]?time\b"),
]


def infer_employment_type(text: str) -> Optional[str]:
    """Guess full-time/part-time/contract/internship from text, or None."""
    low = text.lower()
    for label, pattern in _EMPLOYMENT_PATTERNS:
        if re.search(pattern, low):
            return label
    return None


def _canon_employment(value: str) -> str:
    v = value.lower().replace(" ", "-")
    return {"fulltime": "full-time", "parttime": "part-time"}.get(v, v)


def _canon_seniority(value: str) -> str:
    return value.lower().strip()


def _norm(text: Optional[str]) -> str:
    return (text or "").strip().lower()


# Map the many ways a country is written (full name, ISO-2, common variants) to a
# single canonical token, so strict country filtering doesn't drop a job just
# because the source said "United States" while the user picked "USA".
_COUNTRY_ALIASES = {
    "us": "us", "usa": "us", "united states": "us",
    "united states of america": "us", "america": "us",
    "uk": "uk", "gb": "uk", "united kingdom": "uk", "great britain": "uk",
    "britain": "uk", "england": "uk",
    "ca": "ca", "canada": "ca",
    "au": "au", "australia": "au",
    "de": "de", "germany": "de", "deutschland": "de",
    "fr": "fr", "france": "fr",
    "in": "in", "india": "in",
    "nl": "nl", "netherlands": "nl", "holland": "nl",
    "it": "it", "italy": "it", "italia": "it",
    "es": "es", "spain": "es", "espana": "es", "españa": "es",
    "pl": "pl", "poland": "pl",
    "br": "br", "brazil": "br", "brasil": "br",
    "sg": "sg", "singapore": "sg",
    "nz": "nz", "new zealand": "nz",
}


def _canon_country(value: Optional[str]) -> str:
    """A canonical country token so name variants compare equal — checks the
    core aliases first, then the wider location-country names, so a free-text
    pick like "Ireland" (CLI --country) meets inference's "ie" tokens."""
    v = _norm(value).replace(".", "").strip()
    return _COUNTRY_ALIASES.get(v) or _LOCATION_COUNTRIES.get(v, v)


# US state names + USPS abbreviations: a location like "Albany, NY" or
# "San Francisco, California" is a US job even if the source omitted a country.
_US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana", "maine",
    "maryland", "massachusetts", "michigan", "minnesota", "mississippi",
    "missouri", "montana", "nebraska", "nevada", "new hampshire", "new jersey",
    "new mexico", "new york", "north carolina", "north dakota", "ohio",
    "oklahoma", "oregon", "pennsylvania", "rhode island", "south carolina",
    "south dakota", "tennessee", "texas", "utah", "vermont", "virginia",
    "washington", "west virginia", "wisconsin", "wyoming",
    "district of columbia", "washington dc", "washington, d.c.",
}
_US_STATE_ABBREVS = {
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi", "id",
    "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi", "mn", "ms",
    "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc", "nd", "oh", "ok",
    "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut", "vt", "va", "wa", "wv",
    "wi", "wy", "dc",
}
# Name signals of staffing / recruiting / consulting agencies (as opposed to
# the actual employer). Substring match on the company name, case-insensitive.
_STAFFING_SIGNALS = (
    "staffing", "recruit", "talent", "consulting", "consultants", "solutions",
    "technologies inc", "systems inc", "resourc", "personnel", "employment",
    "workforce", "placement", "staff aug", "teksystems", "robert half",
    "randstad", "adecco", "kforce", "insight global", "aerotek", "cybercoders",
    "apex systems", "collabera", "judge group", "modis", "experis", "manpower",
    "beacon hill", "system one", "ledgent", "motion recruit", "dice",
)


def _is_staffing(company_lower: str) -> bool:
    return any(sig in company_lower for sig in _STAFFING_SIGNALS)


def _is_remote(job: Job) -> bool:
    """Whether a job is remote — its stored work type or, failing that, remote
    language in its title/description. Remote jobs bypass the location filter."""
    if job.work_type == "Remote":
        return True
    if job.work_type in ("In-person", "Hybrid"):
        return False
    from app.sources.base import infer_work_type

    return infer_work_type(job.title or "", job.description or "") == "Remote"


# Back-compat alias (older callers used state_of); region_of now lives in geo.
state_of = region_of
# Big, unambiguous job-hub cities that often appear with no state/country.
_CITY_COUNTRIES = {
    "san francisco": "us", "new york city": "us", "nyc": "us", "seattle": "us",
    "boston": "us", "chicago": "us", "austin": "us", "los angeles": "us",
    "denver": "us", "atlanta": "us",
    "london": "uk", "manchester": "uk", "edinburgh": "uk",
    "dublin": "ie",
    "hamburg": "de", "frankfurt am main": "de", "frankfurt": "de",
    "cologne": "de", "köln": "de", "düsseldorf": "de", "dusseldorf": "de",
    "stuttgart": "de", "leipzig": "de", "mannheim": "de", "nuremberg": "de",
    "nürnberg": "de", "dresden": "de", "karlsruhe": "de", "bremen": "de",
    "hanover": "de", "hannover": "de", "essen": "de", "dortmund": "de",
    "bonn": "de", "münchen": "de", "muenchen": "de", "würzburg": "de",
    "augsburg": "de", "braunschweig": "de", "magdeburg": "de",
    "heilbronn": "de", "fürth": "de", "aachen": "de", "ulm": "de",
    "rostock": "de", "gilching": "de", "kiel": "de", "kassel": "de",
    "regensburg": "de", "wiesbaden": "de", "münster": "de", "bochum": "de",
    "wuppertal": "de", "bielefeld": "de", "mainz": "de", "freiburg": "de",
    "erfurt": "de", "darmstadt": "de", "potsdam": "de",
    "toronto": "ca", "vancouver": "ca", "montreal": "ca", "ottawa": "ca",
    "sydney": "au", "melbourne": "au",
    "singapore": "sg", "tokyo": "jp", "paris": "fr", "berlin": "de",
    "munich": "de", "amsterdam": "nl", "madrid": "es", "barcelona": "es",
    "são paulo": "br", "sao paulo": "br", "bangalore": "in", "bengaluru": "in",
    "mumbai": "in", "gurugram": "in", "mexico city": "mx", "seoul": "kr",
    "dubai": "ae", "stockholm": "se", "warsaw": "pl", "auckland": "nz",
}
# Canadian provinces, so "London, Ontario" reads as Canada, not the UK city.
_CA_PROVINCES = {
    "ontario", "british columbia", "quebec", "québec", "alberta", "manitoba",
    "saskatchewan", "nova scotia", "new brunswick", "newfoundland",
    "newfoundland and labrador", "prince edward island",
    "on", "bc", "qc", "ab", "mb", "sk", "ns", "nb", "nl", "pe",
}
# Extra country names that show up in ATS location strings but weren't needed
# by the strict column compare (which only ever saw ISO-2 codes / user picks).
_LOCATION_COUNTRIES = {
    "ireland": "ie", "japan": "jp", "south korea": "kr", "korea": "kr",
    "mexico": "mx", "sweden": "se", "belgium": "be", "kenya": "ke",
    "united arab emirates": "ae", "uae": "ae", "portugal": "pt",
    "switzerland": "ch", "austria": "at", "denmark": "dk", "norway": "no",
    "finland": "fi", "czech republic": "cz", "czechia": "cz", "greece": "gr",
    "hungary": "hu", "romania": "ro", "argentina": "ar", "chile": "cl",
    "colombia": "co", "philippines": "ph", "indonesia": "id", "vietnam": "vn",
    "thailand": "th", "malaysia": "my", "israel": "il", "turkey": "tr",
    "egypt": "eg", "nigeria": "ng", "south africa": "za", "china": "cn",
    "hong kong": "hk", "taiwan": "tw", "scotland": "uk", "wales": "uk",
    "northern ireland": "uk", "england": "uk", "the netherlands": "nl",
}

# One exact-match lookup table, built once: SEGMENT -> canonical country.
# Segment-EXACT matching is deliberate — substring scans mislabel real places
# ("New South Wales" is not Wales, "New England" is not England, "Northern
# America" is not the US), so a segment either IS a known name or says nothing.
_SEGMENT_COUNTRY: dict[str, str] = {}
_SEGMENT_COUNTRY.update({s: "us" for s in _US_STATES})
_SEGMENT_COUNTRY.update({s: "us" for s in _US_STATE_ABBREVS})
_SEGMENT_COUNTRY.update({p: "ca" for p in _CA_PROVINCES})
_SEGMENT_COUNTRY.update(_CITY_COUNTRIES)
_SEGMENT_COUNTRY.update(_LOCATION_COUNTRIES)
_SEGMENT_COUNTRY.update(_COUNTRY_ALIASES)
# Two-letter tokens that are BOTH a US state / Canadian province and an ISO
# country code get no entry of their own: they only count when a neighbouring
# segment sets the scene ("San Francisco, CA" vs "IN - Bengaluru", "Amsterdam,
# NL" vs "St. John's, NL"). Removed AFTER the updates above so neither the
# state nor the country reading wins by insertion order.
_AMBIGUOUS_2LETTER = {"ca": "ca", "in": "in", "de": "de", "nl": "nl"}  # token -> ISO
for _amb in _AMBIGUOUS_2LETTER:
    _SEGMENT_COUNTRY.pop(_amb, None)
# Trailing fluff a segment may carry after a known name ("New York City
# Metropolitan Area", "San Francisco Bay Area").
_SEGMENT_SUFFIXES = ("metropolitan area", "metro area", "bay area", "area", "greater area")


def _segment_country(token: str) -> Optional[str]:
    """Country for one location segment, or None. Exact match, or a known
    name followed by a whitelisted suffix ("new york city metropolitan area")."""
    hit = _SEGMENT_COUNTRY.get(token)
    if hit:
        return hit
    for name, canon in _SEGMENT_COUNTRY.items():
        if token.startswith(name + " ") and token[len(name) + 1:] in _SEGMENT_SUFFIXES:
            return canon
    return None


def infer_countries_from_location(location: Optional[str]) -> set[str]:
    """Best-effort canonical country tokens named by a free-text location.

    Handles the multi-office strings ATS boards emit ("San Francisco, CA •
    New York, NY • United States", "Remote - United States") by resolving
    every separator-delimited segment it can place. Returns an empty set when
    nothing is recognizable ("Remote", "Europe", "North America") — the caller
    keeps its strict drop for those.
    """
    if not location:
        return set()
    low = _norm(location).replace("(hq)", " ").replace("(", " ").replace(")", " ")
    low = low.replace(".", "")

    # Split office/city parts on commas and the usual list separators. Dashes
    # only split when SPACED ("Remote - US"): a bare hyphen is part of the
    # name ("Stockton-On-Tees" must not shed an "On" that reads as Ontario).
    segments = [s.strip() for s in re.split(r"[•|;/·,]|\s[–—-]\s", low)]
    segments = [s for s in segments if s]

    found: set[str] = set()
    resolved: list[Optional[str]] = [_segment_country(s) for s in segments]

    def _readings(token: str) -> set[str]:
        """Every country a segment could mean (ambiguous 2-letter codes have
        two: the US/CA region reading and the ISO reading)."""
        out = set()
        if token in _AMBIGUOUS_2LETTER:
            out.add(_AMBIGUOUS_2LETTER[token])
            out.add("us" if token in _US_STATE_ABBREVS else "ca")
        elif token in _SEGMENT_COUNTRY:
            out.add(_SEGMENT_COUNTRY[token])
        return out

    for i, (seg, hit) in enumerate(zip(segments, resolved)):
        if hit:
            # Namesake guard: "Vancouver, WA" / "Dublin, CA" / "London,
            # Ontario" / "Boston, UK" — a city or province reading loses to a
            # state/province/country qualifier that follows it and can't mean
            # the same country. Skipped when the qualifier is itself followed
            # by another city ("Toronto, New York, San Francisco" is a
            # sibling office list, not a qualified "Toronto, New York").
            nxt = segments[i + 1] if i + 1 < len(segments) else None
            nxt2 = segments[i + 2] if i + 2 < len(segments) else None
            qualifier = (
                nxt is not None
                and nxt not in _CITY_COUNTRIES
                and not (nxt2 and nxt2 in _CITY_COUNTRIES)
            )
            if qualifier and seg in _CITY_COUNTRIES:
                nxt_reads = _readings(nxt)
                if nxt_reads and hit not in nxt_reads:
                    continue
            if qualifier and seg in _CA_PROVINCES and _readings(nxt) == {"us"}:
                continue  # "Ontario, California" is the US city, not the province
            found.add(hit)
        elif seg in _AMBIGUOUS_2LETTER:
            # "CA"/"IN"/"DE"/"NL" alone prove nothing; use the neighbours.
            others = {c for j, c in enumerate(resolved) if c and j != i}
            if others == {"us"}:
                found.add("us")            # "San Francisco, CA"
            elif len(others) == 1:
                iso = _AMBIGUOUS_2LETTER[seg]
                if others == {iso}:
                    found.add(iso)         # "IN - Bengaluru", "Berlin, DE"
        else:
            # Free-text segment ("remote in the us", "remote us or uk"): the
            # only safe substring hits are the unambiguous us/usa/uk words.
            for word in re.findall(r"\b(usa|us|uk)\b", seg):
                found.add("us" if word in ("us", "usa") else "uk")
    return found
