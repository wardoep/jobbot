#!/usr/bin/env python
"""
JobBot management commands — the friendly front door for running the app.

You don't need to know Python to use this. From the project folder, with the
virtual environment active, run:

    python manage.py db-upgrade        # create/update the database tables
    python manage.py show-schema       # list the tables that exist
    python manage.py create-user       # add a user (prompts you for details)
    python manage.py list-users        # see who has an account
    python manage.py delete-user EMAIL # erase a user and ALL their data
    python manage.py run-once          # poll+match+alert once (test the loop)
    python manage.py run-scheduler     # the always-on loop (poll/match/alert)
    python manage.py test-email --to you@example.com  # check email settings
    python manage.py llm-check --ping  # check the OpenAI tailoring/Q&A setup
    python manage.py tailor --user you@example.com --job 12   # tailoring tips
    python manage.py answer --user you@example.com --job 12 --question "Why us?"
    python manage.py db-revision -m "what changed"   # (developer) new migration

Each command prints what it did in plain English.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

PROJECT_ROOT = Path(__file__).resolve().parent


def _alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


# ---------------------------------------------------------------------------
# Database commands
# ---------------------------------------------------------------------------
def cmd_db_upgrade(args: argparse.Namespace) -> None:
    """Build the database (or bring it up to the latest schema)."""
    from app.config import settings

    where = "local SQLite file" if settings.using_sqlite else "PostgreSQL"
    print(f"Applying migrations to the {where}...")
    command.upgrade(_alembic_config(), "head")
    print("Done. The database now has all the latest tables.")


def cmd_db_revision(args: argparse.Namespace) -> None:
    """(Developer) Auto-create a new migration from changes in app/models.py."""
    command.revision(_alembic_config(), message=args.message, autogenerate=True)
    print("New migration written to migrations/versions/. Review it, then run:")
    print("    python manage.py db-upgrade")


def cmd_db_current(args: argparse.Namespace) -> None:
    """Show which migration the database is currently at."""
    command.current(_alembic_config(), verbose=True)


# ---------------------------------------------------------------------------
# User commands
# ---------------------------------------------------------------------------
def cmd_create_user(args: argparse.Namespace) -> None:
    from app.db import Session
    from app.models import User
    from app.security import hash_password

    email = args.email or input("Email: ").strip()
    password = args.password or getpass.getpass("Password: ")
    if not email or not password:
        sys.exit("Email and password are both required.")

    with Session() as session:
        existing = session.query(User).filter_by(email=email).first()
        if existing:
            sys.exit(f"A user with email {email!r} already exists.")
        user = User(
            email=email,
            password_hash=hash_password(password),
            role="admin" if args.admin else "user",
        )
        session.add(user)
        session.commit()
        print(f"Created {user.role} account for {email} (id={user.id}).")


def cmd_login_code(args: argparse.Namespace) -> None:
    """Issue a one-time sign-in code and print it (owner safety net).

    Lets you sign in from the server console even if email delivery is broken.
    The code is the same kind the website emails; it expires in a few minutes.
    """
    from app.db import Session
    from app.web.login_codes import issue_code

    email = (args.email or input("Email: ").strip()).strip().lower()
    if not email:
        sys.exit("An email is required: python manage.py login-code --email you@example.com")

    with Session() as session:
        code = issue_code(session, email, "login")

    print(f"Sign-in code for {email}: {code}")
    print("Enter it on the website's 'Check your email' step. It expires shortly.")


def cmd_list_users(args: argparse.Namespace) -> None:
    from app.db import Session
    from app.models import User

    with Session() as session:
        users = session.query(User).order_by(User.id).all()
        if not users:
            print("No users yet. Add one with: python manage.py create-user")
            return
        print(f"{'id':<4} {'role':<7} email")
        print("-" * 40)
        for u in users:
            print(f"{u.id:<4} {u.role:<7} {u.email}")


def cmd_delete_user(args: argparse.Namespace) -> None:
    """Erase a user and ALL their private data (resumes, matches, etc.)."""
    from app.db import Session
    from app.models import User

    with Session() as session:
        user = session.query(User).filter_by(email=args.email).first()
        if not user:
            sys.exit(f"No user found with email {args.email!r}.")
        if not args.yes:
            confirm = input(
                f"Permanently delete {args.email} and all their data? [y/N] "
            )
            if confirm.strip().lower() != "y":
                print("Cancelled.")
                return
        session.delete(user)  # cascades to resumes, prefs, matches, stars, answers
        session.commit()
        print(f"Deleted {args.email} and all associated data.")


# ---------------------------------------------------------------------------
# Job ingestion (Phase 2)
# ---------------------------------------------------------------------------
def cmd_fetch_jobs(args: argparse.Namespace) -> None:
    """Pull recent jobs from the sources and store the new ones."""
    from app.ingest import run_ingestion
    from app.sources import ENABLED_SOURCES
    from app.sources.base import SearchQuery

    keywords: list[str] = []
    if args.keywords:
        # accept "data analyst, react" or repeated --keywords
        for chunk in args.keywords:
            keywords.extend(k.strip() for k in chunk.split(",") if k.strip())

    query = SearchQuery(
        keywords=keywords,
        country=args.country,
        location=args.location,
        posted_within_days=args.posted_within_days,
        max_results=args.max_results,
    )

    chosen = ENABLED_SOURCES
    if args.source:
        chosen = [s for s in ENABLED_SOURCES if s.name == args.source]
        if not chosen:
            names = ", ".join(s.name for s in ENABLED_SOURCES)
            sys.exit(f"Unknown source {args.source!r}. Available: {names}")

    print("Fetching jobs (this calls live job-board APIs)...")
    report = run_ingestion(query, sources=chosen)
    print()
    print(report.summary())


def cmd_fetch_ats(args: argparse.Namespace) -> None:
    """Pull live postings from company ATS boards (Greenhouse/Lever/Ashby)."""
    _enable_logs()
    from app.ats_ingest import run_ats_ingestion
    from app.sources.companies_seed import ATS_COMPANIES

    seed = ATS_COMPANIES
    if args.provider:
        seed = [c for c in seed if c[1] == args.provider]
    if args.company:
        needle = args.company.lower()
        seed = [c for c in seed if needle in (c[0].lower(), c[2].lower())]
    if not seed:
        sys.exit("No matching companies in the seed list.")

    cap = args.limit if args.limit is not None else 80
    print(f"Fetching {len(seed)} company ATS board(s) — live public feeds...\n")
    report = run_ats_ingestion(companies=seed, per_company_cap=cap)
    print(report.summary())


def cmd_parse_resume(args: argparse.Namespace) -> None:
    """Extract a structured profile from a stored resume into resumes.parsed_json."""
    _enable_logs()
    import json

    from app.assist import parse_resume
    from app.db import Session
    from app.models import Resume

    session = Session()
    try:
        if args.id:
            doc = session.get(Resume, args.id)
            if doc is None:
                sys.exit(f"No resume with id {args.id}.")
            docs = [doc]
        elif args.all_unparsed:
            docs = (
                session.query(Resume)
                .filter_by(kind="resume")
                .filter(Resume.parsed_json.is_(None))
                .all()
            )
        else:  # default: the most recently uploaded resume
            docs = (
                session.query(Resume).filter_by(kind="resume")
                .order_by(Resume.uploaded_at.desc()).limit(1).all()
            )
        if not docs:
            sys.exit("No resume found. Upload one first (or pass --id).")

        for doc in docs:
            if doc.kind != "resume":
                print(f"[{doc.id}] {doc.filename}: not a resume — skipping.")
                continue
            chars = len(doc.raw_text or "")
            print(f"\nParsing resume [{doc.id}] {doc.filename} ({chars} chars)...")
            profile = parse_resume(doc.raw_text)
            doc.parsed_json = profile
            session.commit()
            print(json.dumps(profile, indent=2, ensure_ascii=False))
    finally:
        session.close()


def cmd_list_jobs(args: argparse.Namespace) -> None:
    """Show stored jobs (most recently fetched first)."""
    from app.db import Session
    from app.models import Job

    with Session() as session:
        q = session.query(Job)
        if args.source:
            q = q.filter_by(source=args.source)
        total = q.count()
        rows = q.order_by(Job.fetched_at.desc()).limit(args.limit).all()
        if not rows:
            print("No jobs stored yet. Run: python manage.py fetch-jobs")
            return
        print(f"{total} job(s) stored. Showing {len(rows)}:\n")
        print(f"{'id':<5}{'source':<11}{'posted':<12}{'work':<10}title @ company")
        print("-" * 78)
        for j in rows:
            posted = j.posted_date.isoformat() if j.posted_date else "—"
            work = j.work_type or "—"
            title = (j.title or "")[:38]
            company = j.company or "—"
            print(f"{j.id:<5}{j.source:<11}{posted:<12}{work:<10}{title} @ {company}")


# ---------------------------------------------------------------------------
# Matching (Phase 3)
# ---------------------------------------------------------------------------
def cmd_match(args: argparse.Namespace) -> None:
    """Run the two-layer matcher (gate + resume score) over the stored jobs."""
    from collections import Counter

    from app.db import Session
    from app.matching import FilterPrefs, evaluate_jobs
    from app.models import Job, User

    # --- resume text -------------------------------------------------------
    resume_text = ""
    if args.resume:
        path = Path(args.resume)
        if not path.exists():
            sys.exit(f"Resume file not found: {path}")
        resume_text = path.read_text(encoding="utf-8", errors="ignore")
    elif args.user:
        from app.models import Resume

        with Session() as s:
            user = s.query(User).filter_by(email=args.user).first()
            if not user:
                sys.exit(f"No user with email {args.user!r}.")
            rows = s.query(Resume).filter_by(user_id=user.id, kind="resume").all()
            resume_text = "\n".join(r.raw_text for r in rows if r.raw_text)
    if not resume_text.strip():
        sys.exit("No resume text. Pass --resume PATH (or upload one in Phase 4).")

    # --- filters from flags (blank = any) ----------------------------------
    keywords: list[str] = []
    for chunk in args.keywords or []:
        keywords.extend(k.strip() for k in chunk.split(",") if k.strip())
    prefs = FilterPrefs(
        country=args.country,
        city=args.location,
        work_types=args.work_type or [],
        posted_within_days=args.posted_within_days,
        salary_min=args.salary_min,
        employment_type=args.employment_type,
        seniority=args.seniority,
        keywords=keywords,
        match_threshold=args.threshold,
    )

    with Session() as session:
        jobs = session.query(Job).all()
        if not jobs:
            sys.exit("No jobs stored. Run: python manage.py fetch-jobs")
        survivors, dropped = evaluate_jobs(jobs, prefs, resume_text)

        print("=" * 72)
        print(f"LAYER 1 — HARD FILTERS (gate):  {len(survivors)} of {len(jobs)} passed")
        print("=" * 72)
        if dropped:
            reasons = Counter(_reason_kind(d.reason) for d in dropped)
            for kind, count in reasons.most_common():
                print(f"  dropped {count:>3}  — {kind}")
            print("  e.g.:")
            for d in dropped[:3]:
                print(f"    - {d.job.title[:40]} @ {d.job.company or '—'}  ({d.reason})")

        above = [s for s in survivors if s.score >= args.threshold]
        print()
        print("=" * 72)
        print(f"LAYER 2 — RESUME MATCH SCORE (ranking the {len(survivors)} survivors)")
        if args.threshold:
            print(f"          showing only scores ≥ {args.threshold}% "
                  f"({len(above)} of {len(survivors)})")
        print("=" * 72)
        for s in (above if args.threshold else survivors)[: args.limit]:
            bar = "#" * int(s.score / 100 * 30)
            title = (s.job.title or "")[:34]
            print(f"  {s.score:5.1f}%  {bar:<30} {title} @ {s.job.company or '—'} "
                  f"[{s.job.source}]")

        # --- optionally store matches for a user ---------------------------
        if args.store:
            if not args.user:
                sys.exit("--store needs --user EMAIL to know whose matches to save.")
            user = session.query(User).filter_by(email=args.user).first()
            if not user:
                sys.exit(f"No user with email {args.user!r}.")
            from app.models import Match

            existing = {m.job_id: m for m in
                        session.query(Match).filter_by(user_id=user.id)}
            stored = 0
            for s in above:
                m = existing.get(s.job.id)
                if m is None:
                    session.add(Match(user_id=user.id, job_id=s.job.id, score=s.score))
                else:
                    m.score = s.score
                stored += 1
            session.commit()
            print(f"\nStored/updated {stored} match(es) for {args.user} "
                  f"(score ≥ {args.threshold}%).")


def _reason_kind(reason: str | None) -> str:
    """Collapse a specific drop reason into a category for the summary."""
    if not reason:
        return "other"
    return reason.split()[0] if " " in reason else reason


# ---------------------------------------------------------------------------
# Web server (Phase 4)
# ---------------------------------------------------------------------------
def cmd_serve(args: argparse.Namespace) -> None:
    """Start the JobBot web app at http://HOST:PORT."""
    import uvicorn

    from app.config import settings

    host = args.host or settings.web_host
    port = args.port or settings.web_port
    print(f"Starting JobBot at http://{host}:{port}  (Ctrl+C to stop)")
    uvicorn.run(
        "app.web.main:app",
        host=host,
        port=port,
        reload=args.reload,
    )


# ---------------------------------------------------------------------------
# Inspection
# ---------------------------------------------------------------------------
def cmd_show_schema(args: argparse.Namespace) -> None:
    """List every table and its columns (a quick sanity check)."""
    from sqlalchemy import inspect

    from app.db import engine

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    app_tables = [t for t in tables if t != "alembic_version"]
    if not app_tables:
        print("No tables yet. Run: python manage.py db-upgrade")
        return
    for table in sorted(app_tables):
        print(f"\n{table}")
        for col in inspector.get_columns(table):
            print(f"  - {col['name']}: {col['type']}")
    print(f"\n{len(app_tables)} tables.")


# ---------------------------------------------------------------------------
# Alerts + always-on scheduler (Phase 5)
# ---------------------------------------------------------------------------
def _enable_logs() -> None:
    """Show INFO logs (cycle progress + dry-run emails) on the console."""
    import logging

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _query_from_args(args: argparse.Namespace):
    """Build the SearchQuery the scheduler polls sources with (same as fetch-jobs)."""
    from app.sources.base import SearchQuery

    keywords: list[str] = []
    for chunk in getattr(args, "keywords", None) or []:
        keywords.extend(k.strip() for k in chunk.split(",") if k.strip())
    return SearchQuery(
        keywords=keywords,
        country=args.country,
        location=args.location,
        posted_within_days=args.posted_within_days,
        max_results=args.max_results,
    )


def cmd_run_once(args: argparse.Namespace) -> None:
    """Run ONE poll -> match -> alert cycle now (handy for testing alerts)."""
    _enable_logs()
    from app.runner import run_cycle

    print("Running one cycle (poll -> match -> alert)...\n")
    rep = run_cycle(
        _query_from_args(args), send=not args.no_send, force_digest=args.force_digest
    )
    print()
    print(rep.summary())
    if args.no_send:
        print("\n(--no-send: matched only; no alerts were sent.)")


def cmd_run_scheduler(args: argparse.Namespace) -> None:
    """Start the always-on loop: a cycle now, then every N minutes until Ctrl+C."""
    _enable_logs()
    from app.config import settings
    from app.runner import start_scheduler

    interval = args.interval_minutes or settings.scheduler_interval_minutes
    print(
        f"JobBot scheduler starting — a cycle now, then every {interval} min "
        f"(email mode: {settings.email_mode}). Press Ctrl+C to stop.\n"
    )
    try:
        start_scheduler(
            _query_from_args(args), interval, force_digest=args.force_digest
        )
    except (KeyboardInterrupt, SystemExit):
        print("\nScheduler stopped.")


def cmd_test_email(args: argparse.Namespace) -> None:
    """Send a single test email to confirm your mail settings work."""
    _enable_logs()
    from app.alerts import send_email
    from app.config import settings

    print(f"Email mode: {settings.email_mode}. Sending a test to {args.to}...\n")
    res = send_email(
        args.to,
        "JobBot test email",
        "This is a test from JobBot. If you can read this, email alerts work.",
        "<p>This is a <b>test</b> from JobBot. "
        "If you can read this, email alerts work.</p>",
    )
    if not res.ok:
        sys.exit(f"\nFailed via {res.transport}: {res.detail}")
    if res.transport == "dry-run":
        print("\nDry-run: no mail account is configured, so the message was logged "
              "above instead of emailed. Fill in SMTP_* (or SENDGRID_API_KEY) in "
              ".env to send for real.")
    else:
        print(f"\nSent via {res.transport}. Check the {args.to} inbox (and spam).")


# ---------------------------------------------------------------------------
# Application assistant: tailoring + Q&A (Phase 6)
# ---------------------------------------------------------------------------
def _user_and_job(session, email: str, job_id: int):
    """Load a (user, job) pair for the assistant CLI, or exit with a clear error."""
    from app.models import Job, User

    user = session.query(User).filter_by(email=email).first()
    if not user:
        sys.exit(f"No user with email {email!r}.")
    job = session.get(Job, job_id)
    if not job:
        sys.exit(f"No job with id {job_id}. Try: python manage.py list-jobs")
    return user, job


def _user_texts(user):
    resume = "\n".join(
        r.raw_text for r in user.resumes if r.kind == "resume" and r.raw_text
    )
    cover = "\n".join(
        r.raw_text for r in user.resumes if r.kind == "cover_letter" and r.raw_text
    )
    return resume, cover


def cmd_llm_check(args: argparse.Namespace) -> None:
    """Show which LLM provider/model is active and (optionally) ping it."""
    from app.llm import LLMError, get_default_provider

    provider = get_default_provider()
    print(f"Provider: {provider.name}   Model: {provider.model}   "
          f"Configured: {provider.is_configured()}")
    if not provider.is_configured():
        print("Set OPENAI_API_KEY in .env to enable tailoring + Q&A.")
        return
    if args.ping:
        try:
            reply = provider.complete(
                "You are terse.", "Reply with: ok", max_output_tokens=5, temperature=0
            )
            print("Ping reply:", reply.strip())
        except LLMError as exc:
            sys.exit(f"LLM error: {exc}")


def cmd_llm_usage(args: argparse.Namespace) -> None:
    """Show how much of the monthly AI-scoring budget has been used."""
    from app.db import Session
    from app.llm_budget import month_usage

    session = Session()
    try:
        used, cap = month_usage(session)
    finally:
        session.close()
    cap_label = str(cap) if cap else "unlimited"
    print(f"AI match-scoring calls this month: {used} / {cap_label}")
    if cap:
        print(f"Change the cap with JOBBOT_LLM_MONTHLY_CAP in .env "
              f"(0 = unlimited). When it's hit, matching falls back to the "
              f"free word-overlap scores until next month.")


def cmd_tailor(args: argparse.Namespace) -> None:
    """Print tailoring suggestions for one user + job (no browser needed)."""
    from app.assist import tailor_application
    from app.db import Session
    from app.llm import LLMError

    with Session() as session:
        user, job = _user_and_job(session, args.user, args.job)
        resume, cover = _user_texts(user)
        try:
            t = tailor_application(resume, cover, job)
        except LLMError as exc:
            sys.exit(f"Could not tailor: {exc}")

    print(f"Job: {job.title} @ {job.company or '—'}   (model: {t.model})")
    print("\n== FIT ==\n" + (t.summary or "—"))
    print("\n== RESUME SUGGESTIONS ==\n" + (t.resume or "—"))
    if t.cover_letter:
        print("\n== COVER-LETTER SUGGESTIONS ==\n" + t.cover_letter)
    if t.keywords:
        print("\n== KEYWORDS ==\n" + ", ".join(t.keywords))


def cmd_answer(args: argparse.Namespace) -> None:
    """Draft an answer to one application question for a user + job."""
    from app.assist import draft_answer
    from app.db import Session
    from app.llm import LLMError
    from app.models import ApplicationAnswer

    with Session() as session:
        user, job = _user_and_job(session, args.user, args.job)
        resume, _cover = _user_texts(user)
        try:
            answer = draft_answer(resume, job, args.question)
        except LLMError as exc:
            sys.exit(f"Could not draft an answer: {exc}")
        if args.save:
            session.add(ApplicationAnswer(
                user_id=user.id, job_id=job.id, question=args.question.strip(),
                draft_answer=answer, final_answer=answer,
            ))
            session.commit()

    print(f"Job: {job.title} @ {job.company or '—'}")
    print(f"Q: {args.question}\n")
    print(answer)
    if args.save:
        print("\n(saved to this user's answers — visible on the job page)")


def main() -> None:
    parser = argparse.ArgumentParser(description="JobBot management commands")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("db-upgrade", help="create/update the database tables").set_defaults(
        func=cmd_db_upgrade
    )

    p_rev = sub.add_parser("db-revision", help="(dev) auto-create a migration")
    p_rev.add_argument("-m", "--message", required=True, help="what changed")
    p_rev.set_defaults(func=cmd_db_revision)

    sub.add_parser("db-current", help="show the DB's current migration").set_defaults(
        func=cmd_db_current
    )

    p_cu = sub.add_parser("create-user", help="add a user account")
    p_cu.add_argument("--email")
    p_cu.add_argument("--password")
    p_cu.add_argument("--admin", action="store_true", help="make this an admin")
    p_cu.set_defaults(func=cmd_create_user)

    p_lc = sub.add_parser(
        "login-code", help="issue + print a sign-in code (owner safety net)"
    )
    p_lc.add_argument("--email", help="the account's email address")
    p_lc.set_defaults(func=cmd_login_code)

    sub.add_parser("list-users", help="list all accounts").set_defaults(
        func=cmd_list_users
    )

    p_del = sub.add_parser("delete-user", help="erase a user and all their data")
    p_del.add_argument("email")
    p_del.add_argument("--yes", action="store_true", help="skip the confirmation")
    p_del.set_defaults(func=cmd_delete_user)

    p_fetch = sub.add_parser("fetch-jobs", help="pull recent jobs from all sources")
    p_fetch.add_argument(
        "--keywords", action="append",
        help='role/keywords, e.g. --keywords "data analyst, python" (repeatable)',
    )
    p_fetch.add_argument("--country", help='e.g. "USA" (mainly affects Adzuna/USAJOBS)')
    p_fetch.add_argument("--location", help="city/area for non-remote roles")
    p_fetch.add_argument(
        "--posted-within-days", type=int, dest="posted_within_days",
        help="only keep jobs posted within this many days",
    )
    p_fetch.add_argument(
        "--max-results", type=int, default=50, dest="max_results",
        help="max jobs to request per source (default 50)",
    )
    p_fetch.add_argument("--source", help="limit to a single source by name")
    p_fetch.set_defaults(func=cmd_fetch_jobs)

    p_ats = sub.add_parser(
        "fetch-ats", help="pull jobs from company ATS boards (Greenhouse/Lever/Ashby)"
    )
    p_ats.add_argument(
        "--provider", choices=["greenhouse", "lever", "ashby"],
        help="limit to one ATS provider",
    )
    p_ats.add_argument("--company", help="limit to one company (name or slug)")
    p_ats.add_argument(
        "--limit", type=int, default=None,
        help="max jobs per company (0 = all; default 80)",
    )
    p_ats.set_defaults(func=cmd_fetch_ats)

    p_pr = sub.add_parser(
        "parse-resume", help="extract a structured profile into resumes.parsed_json"
    )
    p_pr.add_argument("--id", type=int, help="resume id (default: most recent resume)")
    p_pr.add_argument(
        "--all-unparsed", action="store_true", dest="all_unparsed",
        help="parse every resume that has no parsed_json yet",
    )
    p_pr.set_defaults(func=cmd_parse_resume)

    p_lj = sub.add_parser("list-jobs", help="show stored jobs")
    p_lj.add_argument("--source", help="only show this source")
    p_lj.add_argument("--limit", type=int, default=25, help="rows to show (default 25)")
    p_lj.set_defaults(func=cmd_list_jobs)

    p_m = sub.add_parser("match", help="run the matcher (gate + resume score)")
    p_m.add_argument("--resume", help="path to a resume text file")
    p_m.add_argument("--user", help="email; use their stored resume and/or --store")
    p_m.add_argument("--country", help="e.g. USA")
    p_m.add_argument(
        "--work-type", action="append", dest="work_type",
        help="Remote / Hybrid / In-person (repeat for several)",
    )
    p_m.add_argument("--location", help="city/area for non-remote roles")
    p_m.add_argument("--posted-within-days", type=int, dest="posted_within_days")
    p_m.add_argument("--salary-min", type=int, dest="salary_min")
    p_m.add_argument("--employment-type", dest="employment_type",
                     help="full-time / part-time / contract / internship")
    p_m.add_argument("--seniority", help="intern / junior / mid / senior / lead")
    p_m.add_argument("--keywords", action="append", help="role keywords (repeatable)")
    p_m.add_argument("--threshold", type=float, default=0.0,
                     help="only show/store matches at or above this %% (default 0)")
    p_m.add_argument("--limit", type=int, default=15, help="rows to show (default 15)")
    p_m.add_argument("--store", action="store_true",
                     help="save results as matches for --user")
    p_m.set_defaults(func=cmd_match)

    p_serve = sub.add_parser("serve", help="start the web app")
    p_serve.add_argument("--host", default=None,
                         help="bind address (default: WEB_HOST in .env, else 127.0.0.1)")
    p_serve.add_argument("--port", type=int, default=None,
                         help="port (default: WEB_PORT in .env, else 8000)")
    p_serve.add_argument("--reload", action="store_true",
                         help="auto-restart on code changes (for development)")
    p_serve.set_defaults(func=cmd_serve)

    sub.add_parser("show-schema", help="list tables and columns").set_defaults(
        func=cmd_show_schema
    )

    # --- Phase 5: alerts + always-on scheduler ---
    def _add_poll_args(p: argparse.ArgumentParser) -> None:
        p.add_argument(
            "--keywords", action="append",
            help='role/keywords to poll, e.g. --keywords "data analyst" (repeatable)',
        )
        p.add_argument("--country", help='e.g. "USA" (mainly affects Adzuna/USAJOBS)')
        p.add_argument("--location", help="city/area for non-remote roles")
        p.add_argument(
            "--posted-within-days", type=int, dest="posted_within_days",
            help="only keep jobs posted within this many days",
        )
        p.add_argument(
            "--max-results", type=int, default=50, dest="max_results",
            help="max jobs to request per source (default 50)",
        )

    p_once = sub.add_parser(
        "run-once", help="run one poll->match->alert cycle now (test the loop)"
    )
    _add_poll_args(p_once)
    p_once.add_argument(
        "--no-send", action="store_true", dest="no_send",
        help="match only; don't send any alerts",
    )
    p_once.add_argument(
        "--force-digest", action="store_true", dest="force_digest",
        help="ignore the once-a-day digest limit and send now",
    )
    p_once.set_defaults(func=cmd_run_once)

    p_sched = sub.add_parser(
        "run-scheduler", help="start the always-on loop (cycle now, then every N min)"
    )
    _add_poll_args(p_sched)
    p_sched.add_argument(
        "--interval-minutes", type=int, dest="interval_minutes",
        help="minutes between cycles (default from .env: SCHEDULER_INTERVAL_MINUTES)",
    )
    p_sched.add_argument(
        "--force-digest", action="store_true", dest="force_digest",
        help="ignore the once-a-day digest limit on every cycle",
    )
    p_sched.set_defaults(func=cmd_run_scheduler)

    p_test = sub.add_parser("test-email", help="send a test email to check mail setup")
    p_test.add_argument("--to", required=True, help="address to send the test to")
    p_test.set_defaults(func=cmd_test_email)

    # --- Phase 6: tailoring + application Q&A (OpenAI) ---
    p_llm = sub.add_parser("llm-check", help="show the active LLM provider/model")
    p_llm.add_argument("--ping", action="store_true", help="also send a tiny test request")
    p_llm.set_defaults(func=cmd_llm_check)

    sub.add_parser(
        "llm-usage", help="show this month's AI-scoring calls vs the monthly cap"
    ).set_defaults(func=cmd_llm_usage)

    p_tailor = sub.add_parser("tailor", help="suggest resume/cover-letter tweaks for a job")
    p_tailor.add_argument("--user", required=True, help="the user's email")
    p_tailor.add_argument("--job", type=int, required=True, help="job id (see list-jobs)")
    p_tailor.set_defaults(func=cmd_tailor)

    p_ans = sub.add_parser("answer", help="draft an answer to an application question")
    p_ans.add_argument("--user", required=True, help="the user's email")
    p_ans.add_argument("--job", type=int, required=True, help="job id (see list-jobs)")
    p_ans.add_argument("--question", required=True, help="the application question")
    p_ans.add_argument("--save", action="store_true", help="save it to this user's answers")
    p_ans.set_defaults(func=cmd_answer)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
