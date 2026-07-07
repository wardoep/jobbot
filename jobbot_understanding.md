# JobBot — Build & Understanding Tracker

This is our shared map. As we build, we'll check off boxes only once you can explain each item back to me — high level (the *why*) and low level (the *how* and the edge cases). Nothing here is a black box.

---

## The product, in one sentence
An invite-only web app where each user uploads their resume + cover letter, says what they're looking for, and the system continuously finds **recently posted** jobs from reputable sources that match them — pinging them by email / dashboard / chat, and helping them tailor their resume and answer application questions on jobs they star.

---

## Stage 1 — The problem (understand *why this is hard*)
- [ ] Why we **don't scrape LinkedIn directly** (ToS + anti-bot) and what we use instead
- [ ] The difference between a **personal script** and a **multi-user cloud app** (and why your choices push us to the bigger build)
- [ ] What "match my resume" actually means as a computable problem (text → numbers → similarity score)
- [ ] What "recently posted" requires from a data source (a reliable date field + filtering)
- [ ] Why "auto-answer questions on any website" is a *draft helper*, not a universal form-filler

## Stage 2 — The solution & design decisions (understand *how & why this way*)
- [ ] The **5 components** and how data flows between them
- [ ] Why we chose the **tech stack** (and what each piece does)
- [ ] The **database schema** — what tables exist and why
- [ ] The **matching algorithm** — keyword/TF-IDF now, embeddings later, and the tradeoff
- [ ] **Edge cases**: duplicate jobs across sources, stale postings, empty resume, no matches, rate limits
- [ ] Why **scheduled polling** (not real-time) and how "always-on" works

## Stage 3 — The broader context (understand *why it matters & what it impacts*)
- [ ] Privacy/security implications of storing other people's resumes
- [ ] Cost model (free API tiers, LLM usage, hosting) and where it bites at scale
- [ ] What changes when you go from "a few selected people" to "public"
- [ ] Legal/ToS boundaries that constrain the product

---

## Architecture (the 5 components)

```
                ┌─────────────────────────────────────────────┐
                │                 WEB APP (UI + auth)           │
                │  upload resume/cover letter, set preferences, │
                │  view matches, star jobs, get Q&A help        │
                └───────────────┬───────────────────────────────┘
                                │
        ┌───────────────────────┼───────────────────────────────┐
        │                       │                                │
┌───────▼────────┐    ┌─────────▼─────────┐         ┌────────────▼───────────┐
│ 1. INGESTION   │    │ 3. DATABASE        │         │ 2. MATCHING ENGINE      │
│ poll job APIs  │───▶│ users, resumes,    │◀───────▶│ score each job vs each  │
│ (Adzuna, etc.) │    │ jobs, matches,     │         │ user's resume + prefs   │
│ normalize+dedupe│    │ stars, prefs       │         │ rank & store matches    │
└────────────────┘    └─────────┬──────────┘         └─────────────────────────┘
                                 │
                    ┌────────────▼────────────┐   ┌──────────────────────────┐
                    │ 4. ALERTS                │   │ 5. TAILOR & Q&A HELPER   │
                    │ email / dashboard / chat │   │ (LLM) resume tweaks +    │
                    │ on new matches           │   │ draft application answers│
                    └──────────────────────────┘   └──────────────────────────┘

      A SCHEDULER (cron) wakes the Ingestion + Matching + Alerts loop on an interval.
```

## Search filters / preferences (per user — every one optional)
Each filter is a dropdown/input the user can set *or leave blank* ("any"). Blank = don't filter on it.
- **Country** (dropdown)
- **Location + radius** (city/postal code + radius in miles) — only applies to non-remote roles
- **Work type** (multi-select): Remote / Hybrid / In-person
- **Posted within** (dropdown): today / 3 days / 1 week / 2 weeks / 1 month / custom range
- **Keywords / role titles** (e.g. "data analyst", "react")
- **Salary minimum** (where the source provides it)
- **Employment type**: full-time / part-time / contract / internship
- **Seniority**: intern / junior / mid / senior / lead
- **Match threshold**: only alert me above an X% resume-match score

> Design rule: filters are **AND**-combined, each one skipped when left blank. The matching score then *ranks* whatever passes the filters. Two layers: hard filters (must pass) + soft score (ranking).

## Tech stack (proposed — we'll confirm together)
- **Backend:** Python + FastAPI — best ecosystem for resume parsing, text matching, and talking to job APIs.
- **Database:** PostgreSQL — relational data (users ↔ resumes ↔ matches) fits a SQL DB; reliable and free to host.
- **Job sources (pluggable 3-tier system):** every source is an isolated "adapter" with the same output shape, so one breaking never takes down the rest.
  - *Tier A — Official APIs (most stable):* Adzuna (keyword + date + location-radius filter), USAJOBS, Remotive, RemoteOK, Arbeitnow.
  - *Tier B — Scrapers for boards without feeds (the real value):* nystatejobs & other state/gov boards, niche sites not on LinkedIn. Uses your DataImpulse proxy to avoid IP blocks.
  - *Tier C — LinkedIn (optional, isolated, highest-maintenance):* off by default; switch on knowing it breaks most often and carries ToS risk.
- **Matching:** start with TF-IDF + skill-keyword overlap (no API key, runs anywhere); upgrade to embeddings later for smarter semantic matching.
- **Alerts:** SMTP/SendGrid (email), webhooks (Slack/Discord/Telegram), and the dashboard itself.
- **LLM (tailoring + Q&A):** Claude API.
- **Scheduling:** APScheduler/cron for always-on polling.
- **Hosting:** a small always-on host (e.g. Railway / Fly.io / a VPS) + managed Postgres.

## Roadmap (phases)
1. ✅ Architecture & data model *(in progress)*
2. ⬜ Job-source ingestion (recency filter, dedupe)
3. ⬜ Resume parsing & matching engine
4. ⬜ Alerts (email / dashboard / chat)
5. ⬜ Resume tailoring & application Q&A helper
6. ⬜ Multi-user web app, auth & cloud deploy

---
*Last updated: Stage 1 in progress.*
