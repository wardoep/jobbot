"""
JobBot — Stage 2 demo: the matching pipeline, runnable with zero installs.

This is a TINY, readable version of the real engine. It shows the TWO-LAYER model:
  1) HARD FILTERS (gate)  -> a job must pass ALL filters the user set; blank = "any"
  2) SOFT SCORE (ranking) -> survivors are ranked by how well they match the resume

The real product will pull these jobs live from APIs/scrapers; here we use a
handful of hand-made sample jobs so you can watch the logic work.
"""

import math
import re
from collections import Counter
from datetime import date, timedelta

TODAY = date(2026, 6, 18)

# --------------------------------------------------------------------------
# 1. SAMPLE DATA (in the real app these come from job sources + a user profile)
# --------------------------------------------------------------------------

# A user's resume (just text — exactly what we'd extract from their uploaded file)
RESUME = """
Data analyst with 4 years experience. Skilled in SQL, Python, Excel,
Tableau and Power BI. Built dashboards, cleaned data pipelines, and
reported KPIs for finance teams. Bachelor's in Statistics.
"""

# The user's preferences = the HARD FILTERS. Anything set to None means "any".
PREFS = {
    "country": "USA",            # only USA jobs
    "work_types": ["Remote", "Hybrid"],  # no fully in-person
    "posted_within_days": 7,     # last week only
    "city": "Albany",            # used only for in-person/hybrid radius
    "radius_miles": 50,
}

# Sample jobs. distance_miles is "how far from the user's city" (None = remote).
JOBS = [
    {"title": "Data Analyst", "company": "NY State Dept of Health",
     "source": "nystatejobs", "country": "USA", "work_type": "Hybrid",
     "distance_miles": 8, "posted": TODAY - timedelta(days=2),
     "desc": "Analyze public health data using SQL and Tableau. Build dashboards and KPI reports for state finance and operations teams."},

    {"title": "Business Intelligence Analyst", "company": "FinCorp",
     "source": "adzuna", "country": "USA", "work_type": "Remote",
     "distance_miles": None, "posted": TODAY - timedelta(days=1),
     "desc": "Remote BI analyst. Python, SQL, Power BI dashboards, data pipelines, financial KPI reporting."},

    {"title": "Senior Data Scientist", "company": "DeepAI",
     "source": "remotive", "country": "USA", "work_type": "Remote",
     "distance_miles": None, "posted": TODAY - timedelta(days=3),
     "desc": "Machine learning, deep learning, PyTorch, large language models, research. PhD preferred."},

    {"title": "Data Analyst (perfect match, wrong country)", "company": "LondonData",
     "source": "adzuna", "country": "UK", "work_type": "Remote",
     "distance_miles": None, "posted": TODAY,
     "desc": "SQL, Python, Excel, Tableau, Power BI, dashboards, data pipelines, KPI reporting for finance teams. Exactly your skills."},

    {"title": "On-site Data Clerk", "company": "Buffalo Logistics",
     "source": "nystatejobs", "country": "USA", "work_type": "In-person",
     "distance_miles": 280, "posted": TODAY - timedelta(days=4),
     "desc": "Data entry and reporting in Excel. On-site in Buffalo NY."},

    {"title": "Marketing Coordinator", "company": "BrandCo",
     "source": "adzuna", "country": "USA", "work_type": "Remote",
     "distance_miles": None, "posted": TODAY - timedelta(days=20),
     "desc": "Social media, content calendars, campaign coordination. No data skills required."},
]

# --------------------------------------------------------------------------
# 2. LAYER ONE — HARD FILTERS (the gate). Returns (kept, [(job, reason_dropped)])
# --------------------------------------------------------------------------

def passes_filters(job, p):
    if p.get("country") and job["country"] != p["country"]:
        return False, f"country {job['country']} != {p['country']}"
    if p.get("work_types") and job["work_type"] not in p["work_types"]:
        return False, f"work type {job['work_type']} not in {p['work_types']}"
    if p.get("posted_within_days") is not None:
        age = (TODAY - job["posted"]).days
        if age > p["posted_within_days"]:
            return False, f"posted {age}d ago > {p['posted_within_days']}d"
    # radius only matters for jobs that require being somewhere (not remote)
    if job["work_type"] != "Remote" and p.get("radius_miles") is not None:
        if job["distance_miles"] is not None and job["distance_miles"] > p["radius_miles"]:
            return False, f"{job['distance_miles']}mi > {p['radius_miles']}mi radius"
    return True, None

# --------------------------------------------------------------------------
# 3. LAYER TWO — SOFT SCORE (ranking) via simple TF-IDF cosine similarity.
#    (No libraries needed. The real app can upgrade this to AI embeddings.)
# --------------------------------------------------------------------------

def tokenize(text):
    return re.findall(r"[a-z]+", text.lower())

def tf(tokens):
    c = Counter(tokens)
    n = len(tokens)
    return {w: c[w] / n for w in c}

def cosine_match(resume, job_desc, corpus):
    # idf = how rare a word is across all jobs (rare words matter more)
    docs = [tokenize(d) for d in corpus]
    N = len(docs)
    idf = {}
    for w in set(w for d in docs for w in d):
        df = sum(1 for d in docs if w in d)
        idf[w] = math.log((N + 1) / (df + 1)) + 1

    def vec(text):
        t = tf(tokenize(text))
        return {w: t[w] * idf.get(w, 1) for w in t}

    a, b = vec(resume), vec(job_desc)
    shared = set(a) & set(b)
    dot = sum(a[w] * b[w] for w in shared)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)

# --------------------------------------------------------------------------
# 4. RUN THE PIPELINE and print a human-readable report
# --------------------------------------------------------------------------

def main():
    corpus = [j["desc"] for j in JOBS]  # used for idf

    print("=" * 70)
    print("STEP 1 — HARD FILTERS (the gate)")
    print("Your filters:", PREFS)
    print("=" * 70)

    kept = []
    for job in JOBS:
        ok, reason = passes_filters(job, PREFS)
        if ok:
            kept.append(job)
            print(f"  KEPT   | {job['title']} @ {job['company']}")
        else:
            print(f"  DROPPED| {job['title']} @ {job['company']}  ->  {reason}")

    print()
    print("=" * 70)
    print("STEP 2 — RESUME MATCH SCORE (ranking the survivors)")
    print("=" * 70)

    scored = []
    for job in kept:
        score = cosine_match(RESUME, job["desc"], corpus)
        scored.append((score, job))
    scored.sort(reverse=True, key=lambda x: x[0])

    for score, job in scored:
        bar = "#" * int(score * 30)
        print(f"  {score*100:5.1f}%  {bar:<30} {job['title']} @ {job['company']} ({job['source']})")

    print()
    print("Notice: the UK 'perfect match' never appears here — it was gated out")
    print("in Step 1 for being the wrong country, no matter how high it would score.")

if __name__ == "__main__":
    main()
