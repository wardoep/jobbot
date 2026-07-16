# JobBot — Backend Build Spec

This turns the JobBot front-end prototype into a working product: real job data, real
resume-based matching, and passwordless email-code login. Build in the phases at the
bottom — don't try to do it all at once. The goal of the MVP is to answer one question:
**are the matches actually good?**

---

## Recommended stack

- **Frontend:** the existing React app (recreated from this design handoff).
- **Backend:** Node.js + TypeScript (Fastify or Express), or Next.js API routes.
- **Database + Auth + Email codes:** **Supabase** (Postgres + built-in email OTP auth).
  This is the fast path — it covers the DB *and* the login codes. Alternative if you
  want everything self-hosted on your VPS: self-managed Postgres + Resend (email) +
  your own OTP logic (both flows documented below).
- **Vectors:** `pgvector` extension on Postgres (Supabase supports it) for embedding search.
- **AI:** Anthropic Claude API for resume parsing, match scoring, and explanations.
- **Scheduled ingestion:** a cron worker (node-cron, or a separate small service).

All secrets (Supabase keys, Resend key, ANTHROPIC_API_KEY) live in server-side env vars.
Never expose them in the front-end. All Claude calls and code verification happen on the server.

---

## Data model

> Reflects the refined preferences captured in the current UI (must-have skills,
> compensation priority, relocation, industries-to-avoid, pause/quiet-hours).

```
users
  id (uuid, pk)
  email (text, unique)
  created_at (timestamptz)

# Only needed if NOT using Supabase Auth (DIY route)
login_codes
  id (uuid, pk)
  email (text)
  code_hash (text)         # store a HASH of the 6-digit code, never the code
  expires_at (timestamptz) # ~10 minutes out
  used (boolean, default false)
  attempts (int, default 0)
  created_at (timestamptz)

resumes
  id (uuid, pk)
  user_id (uuid, fk -> users)
  raw_text (text)
  parsed_json (jsonb)      # Claude-extracted structured profile
  is_default (boolean)
  created_at (timestamptz)

preferences
  user_id (uuid, fk -> users, pk)
  # --- hard filters (SQL WHERE) ---
  titles (text[])
  locations (text[])
  remote_pref (text)             # remote | hybrid | onsite | any   (UI: "Work type")
  min_salary (int)
  seniority (text[])             # multi-select range (UI: "Experience level")
  job_types (text[])             # full-time | part-time | contract | temporary | internship
  required_keywords (text[])     # UI: "Must-have skills" — role must mention ALL
  excluded_keywords (text[])     # UI: "Exclude keywords"
  excluded_companies (text[])    # UI: "Block companies"
  industries (text[])            # UI: "Industry" (include)
  industries_excluded (text[])   # UI: "Industries to avoid"
  company_sizes (text[])         # startup | mid | large
  date_posted (text)             # any | 24h | week | month  (freshness)
  min_rating (numeric)           # hide employers below this
  willing_to_relocate (boolean)  # UI: "Open to relocation"
  needs_sponsorship (boolean)    # UI toggle "Offers visa sponsorship"
  easy_apply_only (boolean)
  exclude_agencies (boolean)
  # --- soft signals (fed to Claude scoring) ---
  keywords (text[])              # soft match keywords / desired tech
  equity_importance (text)       # salary | balanced | equity  (UI: "Compensation priority")
  # --- account status / delivery ---
  is_active (boolean, default true)   # UI: "Pause new matches"
  paused_until (timestamptz)
  alert_mode (text)                   # top | all | digest
  alert_channels (jsonb)              # { email, push, sms }
  quiet_hours (boolean)
  quiet_start (text)                  # e.g. "10:00 PM"
  quiet_end (text)                    # e.g. "8:00 AM"
  onboarding_completed (boolean)
  updated_at (timestamptz)

companies
  id (uuid, pk)
  name (text)
  ats_provider (text)      # greenhouse | lever | ashby | workable | aggregator
  ats_id (text)            # the company's slug/id on that ATS

jobs
  id (uuid, pk)
  source (text)            # greenhouse | lever | theirstack | serpapi | ...
  source_id (text)
  company_id (uuid, fk -> companies)
  title (text)
  location (text)
  remote_type (text)       # remote | hybrid | onsite
  salary_min (int), salary_max (int), salary_currency (text)
  description_md (text)     # normalize all descriptions to Markdown
  posted_at (timestamptz)
  url (text)
  dedupe_key (text)        # normalized(company + title + location)
  ghost_score (float)      # heuristic 0..1, higher = more likely fake
  embedding (vector)       # pgvector, from description
  created_at (timestamptz)
  unique (source, source_id)

matches
  id (uuid, pk)
  user_id (uuid, fk -> users)
  job_id (uuid, fk -> jobs)
  score (int)              # 0..100 from Claude
  fit_label (text)         # Good fit | Strong fit | Excellent fit
  explanation (text)       # the "why this fits" line
  status (text)            # new | saved | applied | refused
  created_at (timestamptz)
  unique (user_id, job_id)
```

---

## Ingestion flow (scheduled, e.g. hourly)

For each company / source:
1. **Fetch** the ATS feed. Greenhouse, Lever, and Ashby expose public JSON job-board
   endpoints per company — start there (free, clean, legal).
2. **Normalize** each posting into the canonical `jobs` shape. Convert the description
   to Markdown. Parse salary into min/max/currency. Standardize location.
3. **Dedupe** with `dedupe_key`. Collapse the same role appearing across sources. Use
   URL + normalized company/title/location, and a semantic similarity check.
4. **Ghost-job heuristic** -> `ghost_score`: flag postings that are very old, reposted
   many times, or vague/templated. Filter out high scores before they reach a user.
5. **Upsert** into `jobs`.
6. **Embed** new jobs: compute an embedding of the description, store in `embedding`.

Later, add a managed aggregator (TheirStack, LoopCV, or SerpApi's Google Jobs) for
breadth. Do NOT scrape Indeed/LinkedIn directly.

---

## Matching flow (per user; on resume/preference change or daily)

1. **Hard filter** `jobs` using the hard-filter preference columns above (location/remote,
   salary, seniority, job_types, freshness, required/excluded keywords, excluded
   companies & industries, min_rating, sponsorship). Skip entirely if `is_active=false`
   or `paused_until` is in the future.
2. **Embedding rank:** cosine similarity between the user's resume embedding and the
   filtered jobs' embeddings (pgvector `<=>`). Take the top ~20-30.
3. **Claude scoring + explanation:** for each top job, send the parsed resume profile +
   the soft-signal preferences (keywords, equity_importance) + job description to Claude;
   get back `{ score, fit_label, explanation }`.
4. **Upsert** into `matches`. Surface in the UI (Today's top pick = highest score).

---

## Where each Claude API call goes

- **Resume parsing** — on resume upload. Raw text -> structured `parsed_json`.
- **Match scoring + explanation** — top-N jobs per user. parsed profile + soft prefs +
  job description -> `score`, `fit_label`, one-sentence `explanation`.
- **Tailor & apply** (the starred-job feature) — on demand. resume + a specific job ->
  suggested resume tweaks and draft answers.
- **Embeddings** — vectorize resumes and job descriptions for the similarity pre-filter.

---

## Auth: passwordless email codes

### Option A — Supabase Auth (recommended, least code)
1. Frontend `signInWithOtp({ email })` -> Supabase emails a 6-digit code.
2. User enters the code; frontend `verifyOtp({ email, token })` -> returns a session.
3. Configure the email template + your own sending domain for deliverability.

### Option B — DIY on your VPS (Resend/Postmark/SES)
1. `POST /auth/request-code` — generate code, store `hash(code)` + `expires_at` (~10 min),
   email it, rate-limit per email and IP, keep one active code per email.
2. `POST /auth/verify` — look up latest unused/unexpired code, compare hashes, increment
   `attempts` (cap ~5), on success mark used, create/find user, issue session.
3. Never store the raw code; short expiry; limit attempts; rate limit; don't reveal
   whether an email already has an account.

**Deliverability (both options):** verify your sending domain with SPF, DKIM, DMARC.

---

## Build order (ship the smallest real thing first)

1. **Auth** — email-code login end to end (Option A fastest).
2. **Ingestion, narrow** — ~50 target companies via Greenhouse/Lever/Ashby into `jobs`.
3. **Resume upload + parse** — Claude parses into `parsed_json`.
4. **Matching** — filter -> embedding rank -> Claude score/explain -> populate `matches`.
   Render the ranked list with real fit badges and explanations.
5. **Validate** — put it in front of ~10 real users. Are the matches good?
6. **Then** add aggregator breadth, Tailor & apply, alerts/digests, etc.

From here, **match quality is the entire game** — everything above exists to make
"only the roles worth your time" actually true.
