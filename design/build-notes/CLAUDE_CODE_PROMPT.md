# JobBot — Build Prompt for Claude Code

> Paste this whole file into Claude Code as your opening prompt. It is the full spec.
> I (the user) am a **non-coder**. Build it so I can run and maintain it with simple,
> documented commands. Work in **phases** (defined at the bottom). After each phase,
> stop, run it, show me it working, and explain in plain English what you built and why
> before moving to the next phase. Keep a running `README.md` and `.env.example`.

---

## 1. What we're building
An **invite-only, multi-user web app** that continuously finds **recently posted** jobs
from many reputable sources, matches them to each user's uploaded **resume + cover letter**
and their **search preferences**, and pings them (email / dashboard / chat) when new matches
appear. When a user **stars** a job, the app helps them (a) tailor their resume/cover letter
to that job and (b) draft answers to that job's application questions.

## 2. Users & hosting
- Invite-only: an admin invites a small set of users. Each user uploads their own resume +
  cover letter and sets their own preferences. Users only ever see their own data.
- Must run **always-on in the cloud** so alerts fire even when no one's computer is on.

## 3. Core design principle — TWO LAYERS (do not blur these)
1. **Hard filters (a gate):** a job must pass *every* filter the user set. Any filter left
   blank means "any" and is skipped. This is pure yes/no.
2. **Soft score (ranking):** of the jobs that pass the gate, rank by how well the job
   description matches the user's resume, expressed as a 0–100% score. Only alert above the
   user's chosen match threshold.
A reference implementation of both layers exists in `jobbot_demo.py` (pure Python, no installs).
Use it as the seed for the matching module.

## 4. Search filters / preferences (per user — EVERY field optional, blank = "any")
Render each as a dropdown/input the user can set or leave blank:
- **Country** (dropdown)
- **Location + radius** (city or postal code + radius in miles) — applies only to non-remote jobs
- **Work type** (multi-select): Remote / Hybrid / In-person
- **Posted within** (dropdown): today / 3 days / 1 week / 2 weeks / 1 month / custom date range
- **Keywords / role titles** (free text, multiple)
- **Salary minimum** (when the source provides salary)
- **Employment type**: full-time / part-time / contract / internship
- **Seniority**: intern / junior / mid / senior / lead
- **Match threshold**: only alert above X% resume match
Filters are AND-combined; skip any that are blank.

## 5. Job sources — pluggable 3-tier "adapter" system
Every source is an isolated adapter implementing the SAME interface and returning the SAME
normalized `Job` shape. One source breaking must NEVER take down the others. Each adapter
must support: keyword query, posted-since date, country/location, and report work_type +
posted_date so the gate can filter on them.
- **Tier A — Official APIs (most stable, build first):** Adzuna (keyword + date + location radius),
  USAJOBS, Remotive, RemoteOK, Arbeitnow. Use API keys from `.env`.
- **Tier B — Scrapers for boards without feeds (high value):** e.g. nystatejobs and other
  state/government boards, and niche sites not on LinkedIn. Route ALL scraper requests through the
  user's **DataImpulse proxy**, already configured in `.env` as `PROXY_URL`
  (`http://USER:PASS@gw.dataimpulse.com:823`; the `__cr.us` in the username routes via US IPs).
  Read it via `PROXY_URL` / `PROXY_HOST`/`PROXY_PORT`/`PROXY_USER`/`PROXY_PASS`. Never hardcode it
  in source — always read from env. Respect robots where feasible; throttle politely;
  make each scraper resilient to layout changes (clear errors, don't crash the pipeline).
- **Tier C — LinkedIn (optional, OFF by default, isolated):** highest-maintenance, ToS-sensitive.
  Build as a separate toggleable module routed through the DataImpulse proxy. If it fails, log
  and continue — never block other sources.
**Deduplicate** the same job appearing across sources (normalize title + company + location).

## 6. Matching engine
- Start with the TF-IDF + keyword/skill-overlap approach in `jobbot_demo.py` (no paid keys).
- Make it swappable for **AI embeddings** later (Claude / sentence-transformers) behind one
  interface, so we can upgrade match quality without touching the rest of the app.
- Resume parsing: accept PDF and DOCX upload; extract plain text for matching.

## 7. Alerts (multi-channel, user-configurable)
- **Email** (SMTP or SendGrid) — instant or daily digest.
- **Dashboard** — the web app shows ranked matches, lets users star jobs.
- **Chat** — Slack / Discord / Telegram via webhook.
Each user picks which channels they want and digest vs instant.

## 8. Star → tailor & application Q&A (uses Claude API)
- When a user stars a job: generate concrete suggestions to mold their resume + cover letter
  to that job description (show as editable suggestions, never silently overwrite their file).
- Application Q&A helper: the user pastes (or the browser-assist captures) an application
  question; the app drafts an answer grounded in their resume. This is a **draft helper**, not
  an auto-submit/auto-fill bot. Keep a per-job notes area for their saved answers.

## 9. Tech stack (use unless you propose something clearly better, and explain why)
- Backend: **Python + FastAPI**
- Database: **PostgreSQL**
- Scheduler: **APScheduler** (or cron) for always-on polling
- Auth: invite-only accounts, hashed passwords, per-user data isolation
- LLM: **Claude API** for tailoring + Q&A
- Frontend: server-rendered (Jinja + HTMX) or a small React app — pick the simplest that
  gives clean dropdown filters and a matches dashboard; explain your choice.
- Deploy: containerized, deployable to Railway / Fly.io / a VPS, with managed Postgres.

## 10. Data model (starting point — refine as needed)
- `users` (id, email, password_hash, role[admin/user], created_at)
- `resumes` (id, user_id, kind[resume/cover_letter], filename, raw_text, uploaded_at)
- `preferences` (user_id, country, city, radius_miles, work_types[], posted_within_days,
  keywords[], salary_min, employment_type, seniority, match_threshold, alert_channels[], digest_mode)
- `jobs` (id, source, external_id, title, company, country, location, work_type, salary,
  posted_date, url, description, fetched_at, dedupe_key)
- `matches` (id, user_id, job_id, score, created_at, notified_at)
- `stars` (id, user_id, job_id, status, created_at)
- `application_answers` (id, user_id, job_id, question, draft_answer, final_answer, updated_at)

## 11. Edge cases to handle explicitly
Duplicate jobs across sources; stale/expired postings; resume with little text; a user with
zero matches (don't spam an empty alert); source/API rate limits and outages; proxy failures;
LinkedIn layout changes; users leaving every filter blank (return ranked-by-score only);
time zones for "posted within"; never email the same match twice.

## 12. Security & privacy (we are storing other people's resumes)
Encrypt secrets in `.env` (never commit it). Hash passwords. Isolate each user's data behind
auth. Don't log resume contents. Have a clear data-deletion path for a user.

## 13. Build order (PHASES — stop & demo after each)
1. Project scaffold + data model + `.env.example` + README. Migrations create the DB.
2. Ingestion Tier A (Adzuna + key-free feeds), normalized `Job`, dedupe, stored in DB.
3. Matching engine (seed from `jobbot_demo.py`) + the hard-filter gate. Demo on real fetched jobs.
4. Web app: invite-only auth, resume/cover-letter upload, the preference dropdowns, matches dashboard with star.
5. Alerts: email + dashboard + one chat channel; scheduler running the poll→match→alert loop.
6. Star → tailor + application Q&A helper (Claude API).
7. Ingestion Tier B scrapers (nystatejobs etc.) via DataImpulse proxy.
8. Tier C optional LinkedIn module (isolated, off by default).
9. Containerize + deploy always-on with managed Postgres; document how I (non-coder) run/restart it.

After each phase: run it, show output, and explain what + why before continuing.
