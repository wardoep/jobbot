"""
Offline geocoding for distance-based location matching.

Turns a location string ("Dallas, TX", "St. Charles, IL", "Toronto, ON") into
coordinates using a bundled GeoNames-derived table of ~199k US + Canada
populated places (data/cities.tsv — no network, no API key), so the gate can
keep only jobs within a user's mile radius of their city. Covers small towns
(St. Charles, pop 13k), normalizes name variants ("St."↔"Saint"), and degrades
gracefully: an unknown city yields None and the caller falls back to
state/province-level matching.
"""

from __future__ import annotations

import csv
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

_DATA = Path(__file__).resolve().parent / "data" / "cities.tsv"

# Country name/alias -> ISO code used in the dataset.
_COUNTRY_CC = {
    "usa": "US", "united states": "US", "us": "US", "u.s.": "US", "u.s.a.": "US",
    "canada": "CA", "ca": "CA",
}

# State / province names -> USPS-style abbreviation, so a segment that is
# really the STATE (e.g. "New York" in "St James, New York") is recognized as a
# region and NOT mistaken for a city (New York City).
_REGION_NAME_TO_ABBR = {
    "alabama": "al", "alaska": "ak", "arizona": "az", "arkansas": "ar",
    "california": "ca", "colorado": "co", "connecticut": "ct", "delaware": "de",
    "florida": "fl", "georgia": "ga", "hawaii": "hi", "idaho": "id",
    "illinois": "il", "indiana": "in", "iowa": "ia", "kansas": "ks",
    "kentucky": "ky", "louisiana": "la", "maine": "me", "maryland": "md",
    "massachusetts": "ma", "michigan": "mi", "minnesota": "mn",
    "mississippi": "ms", "missouri": "mo", "montana": "mt", "nebraska": "ne",
    "nevada": "nv", "new hampshire": "nh", "new jersey": "nj",
    "new mexico": "nm", "new york": "ny", "north carolina": "nc",
    "north dakota": "nd", "ohio": "oh", "oklahoma": "ok", "oregon": "or",
    "pennsylvania": "pa", "rhode island": "ri", "south carolina": "sc",
    "south dakota": "sd", "tennessee": "tn", "texas": "tx", "utah": "ut",
    "vermont": "vt", "virginia": "va", "washington": "wa",
    "west virginia": "wv", "wisconsin": "wi", "wyoming": "wy",
    "district of columbia": "dc", "washington dc": "dc", "washington, d.c.": "dc",
    "alberta": "ab", "british columbia": "bc", "manitoba": "mb",
    "new brunswick": "nb", "newfoundland and labrador": "nl", "newfoundland": "nl",
    "nova scotia": "ns", "ontario": "on", "prince edward island": "pe",
    "quebec": "qc", "québec": "qc", "saskatchewan": "sk",
    "northwest territories": "nt", "nunavut": "nu", "yukon": "yt",
}
_REGION_ABBRS = set(_REGION_NAME_TO_ABBR.values())


def region_of(text: str) -> Optional[str]:
    """State/province abbreviation named in a location string, or None. Reads
    comma segments so a trailing 'NY'/'New York' or 'ON'/'Ontario' is caught
    without matching stray words. Handles US states and Canadian provinces."""
    for seg in [s.strip().lower() for s in (text or "").replace("/", ",").split(",")]:
        if seg in _REGION_NAME_TO_ABBR:
            return _REGION_NAME_TO_ABBR[seg]
        if len(seg) == 2 and seg in _REGION_ABBRS:
            return seg
    return None


def _is_region_seg(seg: str) -> bool:
    s = seg.strip().lower()
    return s in _REGION_NAME_TO_ABBR or (len(s) == 2 and s in _REGION_ABBRS)


_CITY_INDEX: Optional[dict] = None


# Colloquial city names whose GeoNames asciiname differs. Applied at QUERY
# time only (the dataset stores the canonical name), so "New York, NY" finds
# the 8.8M-population "New York City" rather than a same-named hamlet.
_ALIASES = {"new york": "new york city", "nyc": "new york city"}


def _normalize(name: str) -> str:
    """Canonicalize a city name so 'St. Charles' and 'Saint James' match, etc.
    The prefix rules MUST stay in sync with the dataset builder; aliases are
    query-time only."""
    n = (name or "").lower().replace(".", "")
    n = re.sub(r"\s+", " ", n).strip()
    n = re.sub(r"^st ", "saint ", n)
    n = re.sub(r"^ft ", "fort ", n)
    n = re.sub(r"^mt ", "mount ", n)
    return _ALIASES.get(n, n)


def _index() -> dict:
    """Lazily load {normalized_city: [(lat, lng, country, admin1, pop), ...]}."""
    global _CITY_INDEX
    if _CITY_INDEX is None:
        idx: dict[str, list] = {}
        try:
            with _DATA.open(encoding="utf-8") as f:
                for nm, a1, cc, lat, lng, pop in csv.reader(f, delimiter="\t"):
                    idx.setdefault(nm, []).append(
                        (float(lat), float(lng), cc, a1, int(pop or 0))
                    )
        except (OSError, ValueError):
            pass  # missing/corrupt data file -> empty index -> radius no-ops
        _CITY_INDEX = idx
    return _CITY_INDEX


def _region_hint(location: str) -> Optional[str]:
    """A 2-letter state/province code trailing the location, e.g. 'NY' from
    'St. Charles, IL' — used to disambiguate same-named cities."""
    for seg in reversed([s.strip() for s in (location or "").replace("/", ",").split(",")]):
        if len(seg) == 2 and seg.isalpha():
            return seg.upper()
    return None


@lru_cache(maxsize=20000)
def locate(location: str, country: Optional[str] = None) -> Optional[tuple[float, float, str]]:
    """(lat, lng, state_abbr) for the best city named ANYWHERE in the location
    string, or None. Tries every comma segment — so "East Case, Baltimore"
    resolves to Baltimore, not the unknown neighborhood — and disambiguates by
    country, a trailing state/province code, then population.
    """
    if not location:
        return None
    cc = _COUNTRY_CC.get((country or "").strip().lower())
    region = _region_hint(location)
    best = None
    for i, seg in enumerate(location.split(",")):
        # Skip a state/province name unless it's the FIRST segment — the city
        # comes first ("New York, NY" -> city New York), while a trailing region
        # ("St James, New York") is the state, not a second city.
        if i > 0 and _is_region_seg(seg):
            continue
        entries = _index().get(_normalize(seg))
        if not entries:
            continue
        pool = [e for e in entries if e[2] == cc] if cc else []
        pool = pool or entries
        if region:
            pool = [e for e in pool if e[3].upper() == region] or pool
        cand = max(pool, key=lambda e: e[4])  # most populous match for this segment
        if best is None or cand[4] > best[4]:  # ... and across segments
            best = cand
    if best is None:
        return None
    return (best[0], best[1], best[3])


def geocode(location: str, country: Optional[str] = None) -> Optional[tuple[float, float]]:
    """(lat, lng) for the location, or None. See locate()."""
    r = locate(location, country)
    return (r[0], r[1]) if r else None


def state_from(location: str, country: Optional[str] = None) -> Optional[str]:
    """Lowercase state/province abbr for the location (via its city), or None."""
    r = locate(location, country)
    return r[2].lower() if r and r[2] else None


_ALL_ENTRIES: Optional[list] = None


def _all_entries() -> list:
    """Flat [(lat, lng, country, admin1, pop, name), ...] for reverse lookup."""
    global _ALL_ENTRIES
    if _ALL_ENTRIES is None:
        flat = []
        for name, entries in _index().items():
            for lat, lng, cc, admin1, pop in entries:
                flat.append((lat, lng, cc, admin1, pop, name))
        _ALL_ENTRIES = flat
    return _ALL_ENTRIES


def nearest_city(lat: float, lng: float) -> Optional[dict]:
    """The closest known populated place to the given coordinates, or None if
    nothing is within ~85 miles (the dataset covers the US + Canada). Powers
    the "Use my location" button: browser coords in, {city, state, country,
    miles} out — the coordinates themselves are never stored.
    """
    nearest = None      # absolute closest (fallback when no populated place)
    nearest_d = None
    best = None         # gravity pick: population vs distance, so the answer
    best_score = 0.0    # is "Toronto", not a downtown micro-neighborhood
    best_d = None
    # cheap bounding box (±1.2° ≈ 80mi) before exact distance math
    for elat, elng, cc, admin1, pop, name in _all_entries():
        if abs(elat - lat) > 1.2 or abs(elng - lng) > 1.6:
            continue
        d = haversine_miles((lat, lng), (elat, elng))
        if nearest_d is None or d < nearest_d:
            nearest, nearest_d = (cc, admin1, name), d
        if d <= 40 and pop > 0:
            score = pop / ((d + 1.0) ** 2)
            if score > best_score:
                best, best_score, best_d = (cc, admin1, name), score, d
    if best is None:
        if nearest is None or nearest_d is None or nearest_d > 85:
            return None
        best, best_d = nearest, nearest_d
    return {
        "city": best[2].title(),
        "state": (best[1] or "").lower(),
        "country": best[0],  # "US" | "CA"
        "miles": round(best_d or 0, 1),
    }


_SORTED_KEYS: Optional[list] = None


def _sorted_keys() -> list:
    global _SORTED_KEYS
    if _SORTED_KEYS is None:
        _SORTED_KEYS = sorted(_index().keys())
    return _SORTED_KEYS


def search_cities(
    query: str,
    country: Optional[str] = None,
    limit: int = 20,
    state: Optional[str] = None,
) -> list[str]:
    """Up to `limit` city suggestions whose name starts with `query`, most
    populous first, from the full bundled dataset. With `state`, results are
    limited to that state/province and returned as PLAIN names (no ", ST");
    without it, they're "City, ST"."""
    import bisect

    q = _normalize(query)
    if len(q) < 2:
        return []
    cc = _COUNTRY_CC.get((country or "").strip().lower())
    st = (state or "").strip().upper() or None
    keys = _sorted_keys()
    idx = _index()
    hits: list[tuple[str, int]] = []
    seen: set[str] = set()
    start = bisect.bisect_left(keys, q)
    for name in keys[start : start + 400]:  # bounded scan over the prefix range
        if not name.startswith(q):
            break
        for lat, lng, ccode, admin1, pop in idx[name]:
            if cc and ccode != cc:
                continue
            if st and admin1.upper() != st:
                continue
            label = name.title() if st else f"{name.title()}, {admin1}"
            if label in seen:
                continue
            seen.add(label)
            hits.append((label, pop))
    hits.sort(key=lambda h: -h[1])
    return [label for label, _ in hits[:limit]]


def haversine_miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    """Great-circle distance in miles between two (lat, lng) points."""
    lat1, lng1 = a
    lat2, lng2 = b
    r = 3958.8  # Earth radius, miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    h = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlam / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def distance_miles(
    loc_a: str, loc_b: str, country: Optional[str] = None
) -> Optional[float]:
    """Miles between two location strings, or None if either can't be geocoded."""
    ga, gb = geocode(loc_a, country), geocode(loc_b, country)
    if ga is None or gb is None:
        return None
    return haversine_miles(ga, gb)
