"""Shared helpers for the ATS adapters (Greenhouse / Lever / Ashby):
HTML -> Markdown, salary parsing, date + remote-type normalization.

Kept dependency-light: `markdownify` for HTML->MD, regex for salary. None of these
raise on bad input — they return safe defaults so one weird posting never breaks a run.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Optional

from markdownify import markdownify as _md

from app.sources.base import FetchedJob
from app.sources.http_util import strip_html

_BLANKS = re.compile(r"\n{3,}")


def to_markdown(raw: Optional[str]) -> str:
    """Convert an HTML (or HTML-escaped) job description to clean Markdown.

    Greenhouse returns its `content` HTML-ENTITY-ESCAPED (e.g. `&lt;p&gt;`), while
    Lever/Ashby return real HTML — `html.unescape` first makes both work.
    """
    if not raw:
        return ""
    try:
        unescaped = html.unescape(raw)
        md = _md(unescaped, heading_style="ATX", strip=["script", "style"])
        return _BLANKS.sub("\n\n", md).strip()
    except Exception:
        # Never let a malformed description abort ingestion — fall back to text.
        return strip_html(raw)


def to_plain(raw: Optional[str]) -> str:
    """Plain-text version of a description (for the legacy `description` column)."""
    if not raw:
        return ""
    return strip_html(html.unescape(raw))


# ---------------------------------------------------------------------------
# Salary parsing
# ---------------------------------------------------------------------------
_CUR_SYMBOL = {"$": "USD", "€": "EUR", "£": "GBP"}
_CUR_CODES = {"USD", "EUR", "GBP", "CAD", "AUD", "SGD", "INR"}
# e.g. "$120,000 - $160,000", "120k–160k", "USD 120000 to 150000"
_RANGE = re.compile(
    r"(?P<sym1>[$€£])?\s?(?P<code1>USD|EUR|GBP|CAD|AUD|SGD|INR)?\s?"
    r"(?P<a>\d{2,3}(?:,\d{3})?(?:\.\d+)?\s?[kK]?)"
    r"\s?(?:-|–|—|to)\s?"
    r"(?P<sym2>[$€£])?\s?(?P<b>\d{2,3}(?:,\d{3})?(?:\.\d+)?\s?[kK]?)",
)


def _to_amount(s: str) -> Optional[int]:
    s = s.strip().replace(",", "").replace(" ", "")
    mult = 1
    if s[-1:] in ("k", "K"):
        mult, s = 1000, s[:-1]
    try:
        val = int(float(s) * mult)
    except ValueError:
        return None
    return val


def parse_salary_text(text: Optional[str]) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """Best-effort (min, max, currency) from free text. Returns (None,None,None)
    if nothing plausible (annual 10k..5M) is found."""
    if not text:
        return (None, None, None)
    for m in _RANGE.finditer(text):
        a, b = _to_amount(m.group("a")), _to_amount(m.group("b"))
        if a is None or b is None:
            continue
        lo, hi = sorted((a, b))
        if lo < 10_000 or hi > 5_000_000 or lo == hi:
            continue  # implausible / hourly / not a real range
        sym = m.group("sym1") or m.group("sym2")
        cur = m.group("code1") or _CUR_SYMBOL.get(sym or "", None) or "USD"
        return (lo, hi, cur)
    return (None, None, None)


def salary_from_components(comp: object) -> tuple[Optional[int], Optional[int], Optional[str]]:
    """Pull (min,max,currency) from Ashby/Lever structured comp objects if present."""
    try:
        # Ashby: compensation.compensationTiers[].components[] with minValue/maxValue/currencyCode,
        # or a compensationTierSummary string. Lever: salaryRange {min,max,currency}.
        if isinstance(comp, dict):
            if "min" in comp and "max" in comp:  # Lever salaryRange
                lo, hi = comp.get("min"), comp.get("max")
                if lo and hi:
                    return (int(lo), int(hi), comp.get("currency") or "USD")
            summary = comp.get("compensationTierSummary") or comp.get("summary")
            if isinstance(summary, str):
                lo, hi, cur = parse_salary_text(summary)
                if lo:
                    return (lo, hi, cur)
            for tier in (comp.get("compensationTiers") or []):
                for c in (tier.get("components") or []):
                    lo, hi = c.get("minValue"), c.get("maxValue")
                    if lo and hi and int(hi) >= 10_000:
                        return (int(lo), int(hi), c.get("currencyCode") or "USD")
    except Exception:
        pass
    return (None, None, None)


# ---------------------------------------------------------------------------
# Dates + remote type
# ---------------------------------------------------------------------------
def parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def parse_epoch_ms(value) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


# spec remote_type -> legacy work_type (used by the existing UI + matching gate)
_WORKTYPE = {"remote": "Remote", "hybrid": "Hybrid", "onsite": "In-person"}


def remote_to_worktype(remote_type: Optional[str]) -> Optional[str]:
    return _WORKTYPE.get((remote_type or "").lower()) if remote_type else None


def normalize_remote(workplace_type: Optional[str], is_remote: Optional[bool],
                     *texts: Optional[str]) -> Optional[str]:
    """Return spec remote_type (remote|hybrid|onsite) from explicit flags or text."""
    wt = (workplace_type or "").strip().lower()
    if wt in ("remote", "hybrid"):
        return wt
    if wt in ("onsite", "on-site", "in office", "in-office"):
        return "onsite"
    if is_remote is True:
        return "remote"
    blob = " ".join(t.lower() for t in texts if t)
    if "hybrid" in blob:
        return "hybrid"
    if any(h in blob for h in ("remote", "work from home", "wfh", "anywhere", "distributed")):
        return "remote"
    if is_remote is False:
        return "onsite"
    return None


def build_job(
    *, source: str, external_id, title: Optional[str], company: Optional[str],
    location: Optional[str], url: Optional[str], posted_at: Optional[datetime],
    remote_type: Optional[str], salary: tuple, ats_provider: str, ats_id: str,
    html: Optional[str] = None, plain: Optional[str] = None,
    country: Optional[str] = None,
) -> FetchedJob:
    """Map one ATS posting into a FetchedJob, filling BOTH the spec fields and the
    legacy columns the existing UI/matching read."""
    md = to_markdown(html) if html else (plain or "")
    text = (plain or to_plain(html)) if (plain or html) else ""
    smin, smax, scur = salary
    return FetchedJob(
        source=source,
        external_id=str(external_id),
        title=(title or "").strip(),
        company=company,
        country=country,
        location=location,
        work_type=remote_to_worktype(remote_type),   # legacy
        salary=smin,                                  # legacy (= min)
        posted_date=(posted_at.date() if posted_at else None),  # legacy
        url=url,
        description=text,                             # legacy plain text
        salary_min=smin, salary_max=smax, salary_currency=scur,
        description_md=md,
        posted_at=posted_at,
        remote_type=remote_type,
        ats_provider=ats_provider,
        ats_id=ats_id,
    )
