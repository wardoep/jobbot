# JobBot

An invite-only web app that continuously finds **recently posted** jobs from many
sources, matches them to each user's resume + preferences, and alerts them when new
matches appear. When a user stars a job, it helps tailor their resume/cover letter
and draft answers to the application's questions.

This README grows with every build phase. **You do not need to be a coder to run it** —
every command you need is listed here in plain English.

---

## Where we are: Phase 9 of 9 ✅ — running in production

| Phase | What it adds | Status |
|------:|--------------|--------|
| **1** | Project scaffold, database schema, migrations, this README | ✅ Done |
| **2** | Job ingestion (Adzuna + free feeds), normalize + dedupe | ✅ Done |
| **3** | Matching engine + the hard-filter gate | ✅ Done |
| **4** | Web app: login, resume upload, preferences, matches dashboard | ✅ Done |
| **5** | Alerts (email + dashboard + Slack) + the always-on scheduler | ✅ Done |
| **6** | Star → resume tailoring + application Q&A (OpenAI) | ✅ Done |
| **7** | Tier B scrapers (StateJobsNY + Connecticut) via the proxy | ✅ Done |
| 8 | Tier C optional LinkedIn module (off by default) | ⬜ Optional — not built |
| **9** | Always-on deploy on this server (systemd + SQLite/WAL) | ✅ Done |

---

## What Phase 1 built (plain English)

Think of this phase as **pouring the foundation** before building the house.

1. **A settings file (`.env`)** — one private place for all passwords/keys. The app
   reads everything from here, so secrets never live in the code. `.env.example` is the
   blank template; your real filled-in copy is `.env` (never shared, never committed).

2. **A database schema** — the empty "filing cabinet" with one labelled drawer (table)
   for each kind of thing the app tracks: `users`, `resumes`, `preferences`, `jobs`,
   `matches`, `stars`, and `application_answers`. Right now they're empty; later phases
   fill them.

3. **Migrations** — versioned scripts that *build* those drawers. Running one command
   creates the whole database from scratch. (We use this instead of building tables by
   hand so the cloud database in Phase 9 ends up identical to your local one.)

4. **A management tool (`manage.py`)** — simple commands to build the database, add or
   remove users, and inspect what exists.

**Why SQLite locally but PostgreSQL in the cloud?** To try JobBot on your computer you
shouldn't have to install a database server. So locally it uses a single file,
`jobbot.db` (SQLite — built into Python). In the cloud (Phase 9) you'll point
`DATABASE_URL` at a managed PostgreSQL database. The same code runs on both; you change
nothing but that one setting.

---

## What Phase 2 built (plain English)

Phase 2 is the **intake pipe**: it calls real job boards, translates every board's
different format into ONE common shape, throws away duplicates, and files the survivors
into the `jobs` table.

1. **Adapters (one per board).** Each job board speaks its own "language." An *adapter*
   is a small translator that knows how to talk to one board and hand back jobs in
   JobBot's single normalized shape. We built five Tier A (official-API) adapters:
   **Adzuna**, **Remotive**, **RemoteOK**, **Arbeitnow**, and **USAJOBS**.

2. **Failure isolation.** Every adapter runs inside its own safety net. If a board is
   down, rate-limits us, or changes its format, that one source reports an error and the
   others keep going. You saw this live: `usajobs` cleanly **skipped** itself (no key set)
   while the rest fetched normally.

3. **Deduplication, two ways.** The same job often appears on several boards. We compute
   a `dedupe_key` from a cleaned-up *title + company + location*, so the same role from
   two boards collides into one. We also skip jobs we already stored. (Proof: fetching the
   same query twice stored **40 new** the first time and **0 new / 40 duplicates** the
   second.)

4. **Recency built in.** Each adapter can ask for / filter to "posted within N days," so
   we focus on fresh postings — the whole point of the product.

**Which sources need keys?** Adzuna and USAJOBS need free API keys in `.env`. Remotive,
RemoteOK, and Arbeitnow need none. USAJOBS is optional — leave its keys blank and it
simply sits out.

> Note: some boards (e.g. Adzuna) don't say whether a job is Remote/Hybrid/In-person, so
> we only tag a `work_type` when we're confident; otherwise it's left blank and Phase 3's
> filters treat blank as "unknown" rather than guessing wrong.

## What Phase 3 built (plain English)

Phase 3 is the **brain**. It decides which stored jobs are worth showing a person,
in two deliberately separate layers (this separation is the heart of the product):

**Layer 1 — the hard-filter gate (a yes/no bouncer).** A job must clear *every* filter
the user set; any filter left blank means "any" and is skipped. Filters: country, work
type, posted-within-days, salary minimum, keywords, employment type, seniority, and
location. One important fairness rule: we only reject a job when it has a *known* value
that conflicts — if a board didn't report (say) a country, we don't silently throw the
job away.

**Layer 2 — the resume match score (a 0–100% ranking).** Only the jobs that cleared the
gate get scored. We compare the user's resume text against each job using **TF-IDF +
cosine similarity** (the method seeded from `jobbot_demo.py`) — no API key, runs anywhere.
A higher score means more shared, meaningful words.

You saw both layers on the **65 real jobs** we fetched:
- Filtering to *Remote/Hybrid* dropped exactly the one In-person job.
- Filtering to *senior* dropped the *Junior Data Analyst* and the *Tech Lead* roles.
- Data-analyst roles scored highest against the data-analyst sample resume.

**Why TF-IDF first, embeddings later?** TF-IDF matches on shared *words*; it's free,
instant, and explainable. It can't tell that "ETL" and "data pipelines" mean the same
thing — AI *embeddings* can. The scorer lives behind a one-method interface
(`Scorer.score`), so swapping in an embedding model later changes **one line** and touches
nothing else.

> A note on best-effort filters: the database doesn't store a job's seniority or
> employment type as its own field, so we infer them from the text (seniority from the
> *title*, to avoid matching the verb "lead"). It's good, not perfect — which is exactly
> why these stay *hard filters you opt into*, not silent guesses.

## What Phase 4 built (plain English)

Phase 4 is the **website** — the part people actually log into. Everything from Phases
1–3 (the database, the job sources, the matcher) now has a face.

1. **Invite-only login.** There's no public sign-up. An admin opens the **Admin** page,
   creates an **invite**, and sends the resulting one-time link to a person. They open it,
   set a password, and they're in. Spent invites can't be reused.
2. **Resume & cover-letter upload.** Users upload a **PDF, Word (.docx), or text** file;
   JobBot extracts the words for matching and keeps the original privately. Cover letters
   can be uploaded too (used for tailoring in Phase 6).
3. **Preferences page** — all the hard filters as friendly dropdowns/checkboxes (country,
   work type, posted-within, keywords, salary, employment type, seniority, match threshold,
   alert channels). Blank still means "any".
4. **Matches dashboard** — your jobs, ranked by match %, each with a working link, key
   facts, and a **★ Star** button. A **“Refresh my matches”** button re-runs the matcher
   (gate + score) against the latest jobs using your resume and preferences.

**Privacy is enforced, not just intended** (all verified live this phase):
- Each user sees **only their own** data — the admin's 36 matches were invisible to a new
  user, whose dashboard was empty.
- Non-admins are bounced from the Admin page; logged-out visitors are bounced to login.
- Passwords are bcrypt-hashed (Phase 1); the login cookie is **signed** with `SECRET_KEY`
  so it can't be forged.

**Why this stack?** Server-rendered **FastAPI + Jinja + HTMX**. There's no separate
front-end app to install or run — you start one program and open a browser. HTMX gives small
interactive touches (the star button updates without a page reload) without a heavy
JavaScript framework. Simplest thing that delivers clean dropdowns and a live dashboard.

## What Phase 5 built (plain English)

Phase 5 makes JobBot **run itself and reach out to you**. Until now you had to click
“Refresh my matches”; now a background **scheduler** does the whole loop on a timer and
**alerts** each person when genuinely new matches appear.

1. **One repeating loop, three steps (poll → match → alert).** Every cycle the scheduler:
   *polls* all job sources for fresh postings (Phase 2), re-runs the *match* (Phase 3) for
   every user, then sends each user an *alert* listing only their brand-new matches. One
   command starts it and it keeps running:
   ```bash
   python manage.py run-scheduler        # a cycle now, then every 30 min (Ctrl+C to stop)
   ```
   This is what “always-on” means — a program that wakes *itself* up, so alerts fire even
   when your browser is closed. (In Phase 9 this runs in the cloud so your computer needn't
   be on at all.) We use **APScheduler** for the timer.

2. **Three alert channels, picked per user** (on your Preferences page):
   - **email** — a tidy list of new matches sent to your address.
   - **dashboard** — matches added in the last 24h get a green **New** badge.
   - **slack** — posted to *your own* Slack webhook, so people's alerts never mix.

3. **Instant vs daily digest.** “Instant” emails you each cycle there's something new;
   “daily digest” collects them and sends at most once a day. Your choice, per account.

4. **It never alerts you about the same job twice, and never sends an empty alert.** Once a
   match has been sent, it's stamped (`notified_at`) and skipped forever after. If you have
   nothing new this cycle, you hear nothing.

5. **You don't need a mail account to try it.** If you haven't filled in email settings,
   JobBot runs in **dry-run** mode: it prints the exact email it *would* send to the log, so
   the whole pipeline is testable today. Fill in SMTP (e.g. a Gmail “app password”) or a
   SendGrid key in `.env` whenever you're ready to send for real.

**Seen working live this phase** (admin account, 65 stored jobs):
- A single `run-once` cycle polled all 5 sources (one returned 0, the rest fetched fine —
  the per-source safety net from Phase 2 still holds), re-matched, and produced a **daily
  digest** email listing **30 matches** at or above the 12% threshold.
- Running the cycle **again** sent **nothing**: the 30 were already stamped as notified, and
  the 8 remaining matches (scores 10–12%) were correctly below the threshold.

## What Phase 6 built (plain English)

Phase 6 adds an **AI application assistant**. On any matched job you can ask JobBot to
(a) suggest how to **tailor your resume and cover letter** to that specific posting, and
(b) **draft answers** to the application's questions — both grounded in *your* resume.

1. **It uses OpenAI, behind a swappable interface.** The model lives behind one small
   interface (`app/llm/`), the same trick we used for the matching scorer: the rest of the
   app calls `provider.complete(...)` and doesn't care which company runs the model. Today
   the only provider is **OpenAI**, and it's the default; adding another later is one class
   plus one line. The model is a **low-cost default (`gpt-4o-mini`)** that you can change in
   `.env` with `OPENAI_MODEL`.
2. **Tailoring = honest, editable suggestions — never a rewrite.** Open a job from your
   dashboard (“✨ Tailor & answer →”) and hit **Generate suggestions**. You get a short fit
   assessment, concrete resume tweaks, cover-letter pointers, and keywords worth mirroring.
   They appear in **editable boxes you copy from** — JobBot *never* touches your uploaded
   files, and the prompt forbids inventing experience you don't have.
3. **Q&A helper = a draft, not an auto-filler.** Paste an application question; JobBot writes
   a first-person draft using only what's in your resume, flags anything you should add, and
   **saves it** so you can edit and reuse it. You can edit or delete saved answers anytime.
   (Saved answers live in the `application_answers` table from Phase 1.)
4. **Privacy you should know about.** To do this, your **resume text is sent to OpenAI** for
   that one request. We don't log it, and it's only sent when *you* click tailor/draft. If
   you'd rather not, simply don't use these two features (everything else works without a
   key). No schema change was needed this phase.

**Seen working live this phase** (admin account, real OpenAI calls with `gpt-4o-mini`):
- `tailor` on the top Data-Analyst match returned an honest fit note plus specific,
  resume-grounded suggestions and keywords — no invented experience.
- `answer` drafted a first-person response that drew on the resume's real tools (SQL,
  Tableau, Power BI) and appended a note on what to strengthen; saving it made it appear on
  the job's page.

## What Phase 7 built (plain English)

Phases 2–6 used job boards that hand out data through an **official API**. Many great
boards — especially **state and government** sites — have no API at all. Phase 7 adds the
first **Tier B scraper**: it reads a board's web pages like a browser would. The first one
is **StateJobsNY** (New York State's official jobs site, `statejobsny.com`).

1. **It goes through your DataImpulse proxy — always.** Scrapers can get an ordinary home/
   office IP blocked, so every request is routed through the proxy from your `.env` (verified
   live: requests came out of a **US IP**). The proxy details are *only* read from `.env`,
   never written in the code. A scraper that finds no proxy configured simply **sits out**
   (like a Tier A source missing its key) — it never errors.
2. **Two-step read, kept cheap.** StateJobsNY lists every open vacancy in one big table
   (Item #, Title, Grade, Posted, Deadline, Agency, County). JobBot fetches that **once**,
   filters by your keywords + recency, and only *then* opens the detail page for the handful
   that pass — to pull the duties description, employment type, and city. So a search costs
   one big request plus a few small ones, not thousands.
3. **Polite and resilient, by design (the spec's rules).** It waits a second between requests,
   checks `robots.txt` first (StateJobsNY has none, so nothing is disallowed), and parses the
   table **by column name**, not fixed positions. If the site changes its layout, you get
   fewer or thinner results and a clear log line — **never a crash** (the ingester guards each
   source too).
4. **Same shape as every other source.** The scraper returns the exact normalized `Job` used
   everywhere, so matching, alerts, the dashboard, and the scheduler treat NY State jobs
   identically — and **dedupe** still removes the same role seen elsewhere. Because it's
   registered in `ENABLED_SOURCES`, the **always-on scheduler now polls it automatically**.

**Seen working live this phase:**
- `fetch-jobs --source nystatejobs --keywords "data analyst"` pulled **8 real NY State Data
  Analyst vacancies** (e.g. *Data Analyst 2* at the Office of Addiction Services, Albany) with
  agencies, city-level locations, posted dates, and 2.7–4.1 KB duties descriptions — all
  through the proxy.
- Re-running the same search stored **0 new / 8 duplicates** — dedupe works for scrapers too.

> ⚠️ **Scrapers are higher-maintenance than APIs.** A site can redesign its pages at any time;
> when StateJobsNY does, this adapter may need a tweak (you'll see a "layout change?" log, not
> a crash). That's the nature of Tier B — and why risky boards stay isolated, one file each.

## What Phase 9 built (plain English)

Phase 9 makes JobBot **run by itself on this server, forever** — no terminal left open, no
manual restarts. Two background **services** are now managed by the server's own service
manager (systemd):

- **`jobbot-web`** — the website (the dashboard you log into).
- **`jobbot-scheduler`** — the always-on poll → match → alert loop.

Each service is set up to:
- **Start automatically when the server boots** (you don't start anything by hand).
- **Restart automatically if it crashes** (verified live: killing each one, it came back on
  its own within a few seconds).
- **Keep running after you log out** (they don't belong to your terminal session).

These run as *your* user — so every command below works **without `sudo`**.

**SQLite, but safe for two programs at once.** The web app and the scheduler both use the
same `jobbot.db` file. We turned on SQLite **WAL mode** (plus a 5-second “busy timeout”) so
they can read and write at the same time without “database is locked” errors. You don't have
to do anything — it's automatic.

**Scaling later is one line.** When you outgrow a single server, switch to PostgreSQL by
setting `DATABASE_URL` in `.env` (see “Switching to PostgreSQL” below). The WAL settings turn
themselves off on Postgres, so nothing else changes.

## Running it in production (your two services)

All commands are copy-paste, no `sudo` needed. (The web app listens on `127.0.0.1:8000` —
**this machine only** — by default; see “Opening the dashboard” at the end.)

**Check status — are they running?**
```bash
systemctl --user status jobbot-web         # the website
systemctl --user status jobbot-scheduler   # the poll/match/alert loop
# (look for "Active: active (running)". Press q to exit.)
```

**View logs — what are they doing?**
```bash
journalctl --user -u jobbot-scheduler -f     # follow live (Ctrl+C to stop watching)
journalctl --user -u jobbot-web -n 50        # the last 50 lines
journalctl --user -u jobbot-scheduler -b     # everything since the last boot
```

**Restart / stop / start** (e.g. after you change `.env` or upgrade the code):
```bash
systemctl --user restart jobbot-web jobbot-scheduler   # restart both
systemctl --user stop jobbot-scheduler                 # pause the loop
systemctl --user start jobbot-scheduler                # resume it
```

**Verify it survives a reboot** (the real test):
```bash
# Reboot the server however you normally do, then log back in and run:
systemctl --user is-active jobbot-web jobbot-scheduler   # should print: active  active
curl -s http://127.0.0.1:8000/healthz                    # should print: {"status":"ok"}
journalctl --user -u jobbot-scheduler -b | grep "Scheduler started"   # the loop began on its own
```
> Why didn't I reboot it for you? A reboot would drop my own connection to the server, so I
> couldn't watch it come back or fix anything if it didn't. The services are **enabled** and
> your account has **lingering** turned on, which is exactly what makes systemd start them at
> boot — the three commands above confirm it after you reboot.

**If you ever edit a service file** (`~/.config/systemd/user/jobbot-*.service`):
```bash
systemctl --user daemon-reload && systemctl --user restart jobbot-web jobbot-scheduler
```

### Switching to PostgreSQL (the one-line scale-up)
```bash
.venv/bin/pip install "psycopg[binary]"          # 1. install the Postgres driver (once)
#  2. THE one line — put your database URL in .env:
#       DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/jobbot
.venv/bin/python manage.py db-upgrade            # 3. create the tables in Postgres
systemctl --user restart jobbot-web jobbot-scheduler   # 4. restart both
```
Blank `DATABASE_URL` = SQLite (today); filled in = Postgres. (Moving your *existing* SQLite
rows into Postgres is a separate one-time copy — ask when you get there.)

### Opening the dashboard
By default the site is bound to `127.0.0.1` (private to the server). To reach it from your
laptop, tunnel over SSH and open `http://localhost:8000`:
```bash
ssh -L 8000:127.0.0.1:8000 eddie@<this-server>     # then browse to http://localhost:8000
```
To expose it on the network instead, set `WEB_HOST=0.0.0.0` in `.env` and restart the web
service — but put it behind a reverse proxy with HTTPS first.

## Running the web app yourself (development)

> In production the `jobbot-web` service above already runs this for you. The commands here
> are for running it by hand while developing (e.g. with auto-reload).

```bash
source .venv/bin/activate
python manage.py db-upgrade          # if you haven't already
python manage.py serve               # then open http://127.0.0.1:8000
```

First time in:
1. Log in as the admin you made in Phase 1 (`python manage.py create-user --admin` if you
   haven't): e.g. `jordan.lee@example.com`.
2. Go to **Admin → create an invite** to add more people (or keep using the admin account).
3. **Resumes →** upload your resume. **Preferences →** set your filters and **Save**.
4. **Dashboard → “Refresh my matches.”** (Or just start `python manage.py run-scheduler`
   in another terminal and JobBot fetches, matches, and alerts on a timer for you.)

> Add `--reload` while developing (`python manage.py serve --reload`) to auto-restart on
> code changes. For other machines on your network use `--host 0.0.0.0`.

## One-time setup

You only do this once.

```bash
# 1. Go to the project folder
cd ~/jobbot

# 2. Create an isolated Python environment (keeps JobBot's packages separate)
python3 -m venv .venv

# 3. Turn it on (do this every new terminal session — your prompt will show ".venv")
source .venv/bin/activate

# 4. Install the packages JobBot needs
pip install -r requirements.txt

# 5. Create your private settings file from the template, then open it and fill it in
cp .env.example .env
#    For Phase 1 you can leave everything blank — it just works with the local file DB.
#    (Optional) generate a SECRET_KEY for later:
#        python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Build / start the database

```bash
source .venv/bin/activate     # if not already active
python manage.py db-upgrade   # creates (or updates) all the tables
```

## Everyday commands

```bash
python manage.py show-schema                 # list every table and its columns
python manage.py create-user --admin         # add an admin (prompts for email + password)
python manage.py create-user                 # add a normal user
python manage.py list-users                  # see who has an account
python manage.py delete-user EMAIL           # erase a user and ALL their data (privacy)
python manage.py db-current                  # show the DB's current version
```

### Fetching jobs (Phase 2)

```bash
# Pull recent jobs from every source and store the new ones:
python manage.py fetch-jobs --keywords "data analyst" --country USA --posted-within-days 14

# Other options:
#   --keywords "react, typescript"   role/keywords (comma-separated or repeat the flag)
#   --location "Albany, NY"           city/area (matters for non-remote roles)
#   --max-results 50                  how many to request per source
#   --source remotive                 limit to a single source

python manage.py list-jobs                   # show stored jobs (newest first)
python manage.py list-jobs --source adzuna   # only one source
```

**Tier B scrapers — StateJobsNY & Connecticut (Phase 7).** Sources with no API, scraped
through your DataImpulse proxy. They're just more `--source`s, but they need the proxy
filled in (`PROXY_URL` / `PROXY_USER` / `PROXY_PASS` in `.env`); without it, they quietly
sit out.

```bash
# New York State vacancies (statejobsny.com):
python manage.py fetch-jobs --source nystatejobs --keywords "data analyst" --posted-within-days 30
# Connecticut state jobs (jobapscloud.com/CT):
python manage.py fetch-jobs --source ctstatejobs --keywords "analyst" --posted-within-days 30
python manage.py list-jobs --source ctstatejobs
```

Both are part of the normal all-sources run (`fetch-jobs` with no `--source`) and the
always-on scheduler, so once the proxy is set you don't have to do anything special.

> Why Connecticut (not, say, Dice)? Dice's `robots.txt` disallows scraping its job pages,
> so we respect that and skip it. Among large state boards, California is blocked by the
> proxy and most others (TX/PA/OH…) are JavaScript apps we can't read as plain HTML;
> Connecticut's older JobAps platform is server-rendered and has no robots.txt, so it's a
> clean fit — and its pages even embed machine-readable JSON for reliable parsing.

### Matching jobs to a resume (Phase 3)

```bash
# Rank the stored jobs against a resume, with optional hard filters.
# Every filter is optional — leave it off to mean "any".
python manage.py match \
  --resume examples/sample_resume.txt \
  --country USA --work-type Remote --work-type Hybrid \
  --keywords "data analyst" --threshold 10

# Other filters: --seniority senior   --employment-type full-time
#                --salary-min 90000   --location "Albany, NY"
#                --posted-within-days 7   --limit 20

# Save the results as this user's matches (for the dashboard/alerts later):
python manage.py match --resume examples/sample_resume.txt \
  --user you@example.com --threshold 10 --store
```

The output shows **Layer 1** (how many jobs passed the gate, and why others were
dropped) then **Layer 2** (the surviving jobs ranked by resume-match %).

### Alerts & the always-on scheduler (Phase 5)

```bash
# Start the always-on loop: fetch -> match -> alert, now and every 30 minutes.
# Leave it running (in its own terminal, or as a service in Phase 9). Ctrl+C stops it.
python manage.py run-scheduler --keywords "data analyst" --country USA

#   --interval-minutes 15     how often to run (default 30, or SCHEDULER_INTERVAL_MINUTES)
#   the same --keywords/--country/--location/--posted-within-days/--max-results as fetch-jobs

# Run the loop exactly once (great for testing without waiting):
python manage.py run-once --keywords "data analyst"
python manage.py run-once --no-send        # match only, send no alerts
python manage.py run-once --force-digest    # ignore the once-a-day digest limit

# Check your email settings by sending one test message:
python manage.py test-email --to you@example.com
```

**Setting up real email (optional).** Until you do this, alerts are logged, not sent
(“dry-run”). In `.env`, fill in **either** SMTP **or** SendGrid:
- *SMTP* (e.g. Gmail): set `SMTP_HOST=smtp.gmail.com`, `SMTP_PORT=587`, `SMTP_USER` to your
  address, and `SMTP_PASSWORD` to a Gmail **App Password** (not your normal password).
- *SendGrid*: set `SENDGRID_API_KEY`.
- Set `APP_BASE_URL` to where the app is reachable so the “see your matches” links work.

**Setting up Slack (optional, per user).** On the **Preferences** page, tick the *slack*
channel and paste your personal **Incoming Webhook URL**. Only your matches go to it.

### Resume tailoring & application Q&A (Phase 6)

First put your OpenAI key in `.env` as `OPENAI_API_KEY` (and optionally `OPENAI_MODEL`),
then either use the **dashboard** (open a job → “✨ Tailor & answer”) or the CLI:

```bash
python manage.py llm-check --ping        # confirm the provider/model + a live test call

# Suggest resume/cover-letter tweaks for a user + job (job ids come from list-jobs):
python manage.py tailor --user you@example.com --job 24

# Draft an answer to an application question (optionally --save it to the job page):
python manage.py answer --user you@example.com --job 24 \
  --question "Why do you want this role?" --save
```

- The assistant defaults to **OpenAI** with the low-cost **`gpt-4o-mini`** model; change it
  with `OPENAI_MODEL=` in `.env`. It's built behind a swappable interface, so a different
  provider can be added later without touching the rest of the app.
- These are **draft helpers**: suggestions are editable and never overwrite your files, and
  answers are drafts you edit before using. Your **resume text is sent to OpenAI** only when
  you run tailor/answer — skip these two features if you'd rather it never leave your machine.

> Tip: every command prints what it did. If something looks wrong, copy the output and
> we'll read it together.

---

## The data model (the 7 tables)

| Table | Holds | Key columns |
|-------|-------|-------------|
| `users` | login accounts | email, password_hash, role (admin/user) |
| `resumes` | uploaded resume **or** cover letter + its extracted text | user_id, kind, raw_text |
| `preferences` | each user's search filters + alert settings | country, work_types, keywords, match_threshold… |
| `jobs` | normalized postings from every source | source, title, company, work_type, posted_date, dedupe_key |
| `matches` | a (user, job) pairing with a 0–100 score | user_id, job_id, score, notified_at |
| `stars` | jobs a user flagged to act on | user_id, job_id, status |
| `application_answers` | drafted answers to a job's questions | question, draft_answer, final_answer |

**Two design rules already baked into the schema:**
- *Never alert twice:* `matches` is unique per (user, job) and carries `notified_at`.
- *Never store a job twice:* `jobs` is unique per (source, external_id) and carries a
  `dedupe_key` to also catch the *same* job arriving from *different* sources.

---

## Security & privacy (already in place)

- Passwords are stored as one-way **bcrypt hashes**, never as plain text.
- `.env` (your secrets) and `jobbot.db` / `uploads/` (private data) are git-ignored.
- `delete-user` fully erases a person and everything linked to them (resumes, matches,
  stars, answers) in one step — our data-deletion path.

---

## Project layout

```
jobbot/
├── .env                # YOUR secrets (private, not committed)
├── .env.example        # blank template to copy
├── requirements.txt    # the packages to install
├── manage.py           # the commands you run
├── alembic.ini         # migration settings
├── migrations/         # the versioned DB-building scripts
│   └── versions/
├── app/
│   ├── config.py       # loads settings from .env
│   ├── db.py           # database connection
│   ├── models.py       # the 7 tables, as Python classes
│   ├── security.py     # password hashing
│   ├── ingest.py       # runs all sources, dedupes, stores jobs
│   ├── matching/       # the "brain"
│   │   ├── gate.py     #   Layer 1: hard filters (yes/no)
│   │   ├── scorer.py   #   Layer 2: resume score (swappable: TF-IDF → embeddings)
│   │   └── engine.py   #   runs both layers, stores matches
│   ├── alerts/         # Phase 5: turn new matches into emails / Slack messages
│   │   ├── email.py    #   send mail (SMTP → SendGrid → dry-run fallback)
│   │   ├── slack.py    #   post to a user's own Slack webhook
│   │   ├── compose.py  #   render matches into subject + bodies (no resume text)
│   │   └── notify.py   #   per-user: channels, instant vs digest, mark notified
│   ├── runner.py       # Phase 5: the poll→match→alert cycle + APScheduler timer
│   ├── llm/            # Phase 6: the swappable LLM provider (OpenAI by default)
│   │   ├── base.py     #   the LLMProvider interface (one method: complete)
│   │   └── openai_provider.py  # OpenAI via httpx (Chat Completions)
│   ├── assist.py       # Phase 6: tailoring + Q&A prompts (provider-agnostic)
│   ├── resume_parse.py # extracts text from PDF / DOCX / TXT uploads
│   ├── web/            # the website (FastAPI + Jinja + HTMX)
│   │   ├── main.py     #   the app object + routers + error redirects
│   │   ├── auth.py     #   login / logout / invite registration
│   │   ├── admin.py    #   invite creation (admin only)
│   │   ├── resumes.py  #   upload / list / delete documents
│   │   ├── preferences.py  # the filters form
│   │   ├── dashboard.py    # matches + star toggle + refresh
│   │   ├── assist.py       # Phase 6: /jobs/{id} tailoring + Q&A page
│   │   ├── templates/  #   the HTML pages
│   │   └── static/     #   the stylesheet
│   └── sources/        # one adapter per job board (same shape out)
│       ├── base.py     #   the shared interface + normalization helpers
│       ├── adzuna.py   #   Tier A adapters ...
│       ├── remotive.py
│       ├── remoteok.py
│       ├── arbeitnow.py
│       ├── usajobs.py          #   (Tier A — official APIs — ends here)
│       ├── http_util.py        #   shared GET helpers (JSON + HTML, proxy-aware)
│       ├── scraper_base.py     #   Tier B base: proxy + throttle + robots (Phase 7)
│       ├── nystatejobs.py      #   Tier B scraper: StateJobsNY through the proxy
│       └── ctstatejobs.py      #   Tier B scraper: Connecticut (JobAps) through the proxy
├── jobbot_demo.py      # the matching-logic reference (seeds Phase 3)
└── jobbot.db           # the local database file (created by db-upgrade)
```
