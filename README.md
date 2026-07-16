# JobBot

A self-hosted job-search platform that ingests postings from a dozen sources, scores them against a user's resume with AI, alerts through six channels, and tracks applications end to end — running unattended on Linux under systemd.

## Overview

JobBot is an invite-only web application I built and operate in production on my own server. It continuously polls job boards and company ATS pages for fresh postings, filters and ranks them per user against an uploaded resume plus explicit preferences, and notifies each user only about genuinely new, relevant matches. From there it helps with the application itself: AI-tailored resume and cover-letter suggestions, drafted answers to portal questions, applied-status tracking, follow-up reminders, and an opt-in inbox watcher that detects confirmations, interviews, and rejections in the user's own mailbox.

The emphasis throughout is operational: per-source failure isolation, API cost budgeting, idempotent alerting (never the same job twice, never an empty alert), and services that restart themselves and survive reboots.

## Architecture

```
ingest ─▶ normalize + dedupe ─▶ hard-filter gate ─▶ fit scoring ─▶ alerts ─▶ application tracking ─▶ inbox watcher
```

1. **Ingest** — one adapter per source behind a shared interface. Official APIs (Adzuna, Remotive, RemoteOK, Arbeitnow, USAJOBS, The Muse, JSearch), public ATS boards (Greenhouse, Lever, Ashby) for seeded companies, and HTML scrapers for boards with no API (StateJobsNY, Connecticut JobAps) that respect robots.txt, throttle requests, and route through a proxy. Each adapter runs in its own error boundary: a source that is down or misconfigured skips itself; the rest keep going.
2. **Normalize + dedupe** — every source emits the same normalized job shape. Jobs are unique per (source, external_id), and a `dedupe_key` derived from cleaned title + company + location collapses the same role arriving from different boards.
3. **Fit scoring** — three layers, deliberately separated. A yes/no hard-filter gate (location, work type, salary, keywords, recency — unknown values never cause silent rejection); a TF-IDF cosine score of resume text against every surviving job (free, instant, explainable); and an optional LLM re-score of the top candidates that returns a calibrated 0–100 fit with a one-line rationale. LLM verdicts are cached by content hash and capped by a monthly budget, and the layer fails open to the TF-IDF ranking if the API is unavailable.
4. **Alerts** — a scheduler cycle (APScheduler, default every 30 minutes) runs poll → match → alert. Six channels, chosen per user: email (SMTP / SendGrid / Resend, with a dry-run fallback), Slack webhook, Discord webhook, Telegram bot, ntfy push, and SMS via Twilio. Instant or daily-digest delivery; each match is stamped `notified_at` so nothing is ever sent twice.
5. **Application tracking** — starring a job unlocks AI assistance: tailoring suggestions, drafted portal answers, and auto-generated "application kits" for the strongest matches (rate-capped per user per day). Jobs marked applied get a one-time drafted follow-up nudge after a configurable number of days.
6. **Inbox watcher** — with explicit opt-in, JobBot connects to the user's mailbox over read-only IMAP, scans incrementally by UID, prefilters on headers, and classifies only the few job-related messages: application confirmations flip the job to Applied automatically; interviews, offers, and rejections trigger an immediate ping.

## Key features

- 12+ job sources spanning official APIs, ATS boards, and polite scrapers, all normalized and cross-source deduplicated
- Two-layer matching (hard filters + resume similarity) with optional budget-capped AI re-scoring and cached verdicts
- Six per-user alert channels with instant/digest modes and exactly-once delivery
- Invite-only multi-user web app (FastAPI + Jinja2 + HTMX): resume upload (PDF/DOCX/TXT), preferences, ranked matches dashboard, admin panel
- AI application assistant: resume/cover-letter tailoring and Q&A drafts grounded in the user's actual resume — suggestions only, never invented experience
- IMAP inbox watcher that automates applied-status bookkeeping and interview/rejection pings
- Monthly request budgets for metered APIs (job sources and LLM calls) so free tiers are never blown
- Production deployment as systemd user services with auto-restart, boot persistence, and journald logging

## Security notes

- **Credentials encrypted at rest** — the inbox watcher's IMAP app password is Fernet-encrypted (AES-128-CBC + HMAC via the `cryptography` library) with a key derived from the server's `SECRET_KEY`; plaintext is never written to the database.
- **Least-data mailbox access** — IMAP sessions are opened read-only; most messages are only ever seen as headers, and nothing is stored except the subject and message-id of the handful of actionable messages, as an audit trail.
- **Secrets via environment only** — every key, token, and password is read from `.env`/environment variables through one settings module; nothing sensitive lives in code or in the repository.
- **Authentication hardening** — bcrypt-hashed passwords; short-lived 6-digit login codes stored only as bcrypt hashes with expiry and attempt caps; optional SMS 2FA; signed session cookies; per-IP rate limiting on the login form.
- **Privacy by construction** — invite-only registration, strict per-user data isolation, a `delete-user` command that erases a person and everything linked to them, and Discord webhook URL validation so alerts cannot be POSTed to arbitrary hosts.
- **Safe defaults** — the web server binds to 127.0.0.1 unless explicitly exposed; scrapers sit out silently when no proxy is configured rather than leaking the server's IP.

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3 |
| Web | FastAPI, Jinja2, HTMX (server-rendered, no frontend build) |
| Database | SQLAlchemy 2 ORM + Alembic migrations; SQLite (WAL mode) locally, PostgreSQL via one `DATABASE_URL` change |
| Scheduling | APScheduler inside a long-running worker |
| HTTP / parsing | httpx, lxml |
| Security | cryptography (Fernet), bcrypt, itsdangerous |
| AI | OpenAI API behind a swappable one-method provider interface |
| Ops | systemd user services, journald, deployed on a self-managed Linux server |

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -c "import secrets; print('SECRET_KEY=' + secrets.token_urlsafe(48))" > .env   # API keys optional
python manage.py db-upgrade     # build the schema via Alembic
python manage.py create-user --admin
python manage.py serve          # web UI at http://127.0.0.1:8000
python manage.py run-scheduler  # the poll -> match -> alert loop (separate terminal)
```

Several sources need no API key at all, and email/SMS fall back to dry-run logging when unconfigured, so the full pipeline is testable with an empty `.env`. In production, `jobbot-web` and `jobbot-scheduler` run as systemd user services (`Restart=always`, lingering enabled) sharing one SQLite database in WAL mode.

## What I learned

- **Designing multi-channel alerting.** Six delivery channels taught me to separate composing a message from transporting it, to make every transport dry-run capable so the pipeline is testable without live credentials, and to treat idempotency as a schema concern — a unique (user, job) row with a `notified_at` stamp is what actually guarantees "never alert twice," not application logic alone.
- **IMAP and email protocols.** Building the inbox watcher meant working directly with IMAP: read-only sessions, UID-based incremental search (including the gotcha that `UID N:*` always returns at least one message), MIME header decoding, and multipart body extraction. I also learned to scope access deliberately — headers-first prefiltering so most mail is never read at all.
- **Encrypting credentials at rest.** Storing a user's mail app password forced real key-management decisions: deriving a Fernet key from the server secret via SHA-256, failing closed (a bad token decrypts to "not connected," never an error page), and keeping encryption/decryption in one small audited module.
- **Database migrations.** Twenty-plus Alembic revisions evolved a live production schema — adding tables, backfilling columns, staying compatible across SQLite and PostgreSQL — and made "the database is versioned like the code" a habit rather than a slogan.
- **Running scheduled jobs on Linux.** Operating this 24/7 without root meant learning systemd user services end to end: unit files, `Restart=always`, `loginctl enable-linger` for boot persistence, `journalctl --user` for debugging, and kill-testing recovery. Concurrent access from two services drove me to SQLite WAL mode and busy timeouts to eliminate lock errors.
- **Operating against third-party APIs.** Per-source failure isolation, monthly request budgets for metered free tiers, response caching to avoid paying twice for the same answer, and respectful scraping (robots.txt checks, throttling, proxy routing) — the difference between a script that works once and a service that runs for months.

---
Built and maintained by **Edward J. Penna** — [github.com/wardoep](https://github.com/wardoep)
