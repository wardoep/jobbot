"""
The database schema, expressed as Python classes (SQLAlchemy ORM models).

Each class below becomes a TABLE; each attribute becomes a COLUMN. This mirrors
the data model in the build spec (section 10). The relationships at the bottom
let us walk between rows (e.g. user.resumes) in plain Python.

Notes on portability:
- We use JSON columns for the "list" preferences (work_types, keywords,
  alert_channels). PostgreSQL has a native array type, but JSON works
  identically on SQLite AND Postgres, so the same code runs everywhere.
- IDs are plain auto-incrementing integers — simple and database-agnostic.
"""

from __future__ import annotations

from datetime import datetime, date
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


# ---------------------------------------------------------------------------
# users — one row per person who can log in
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    # "admin" can invite others; "user" is a normal account.
    role: Mapped[str] = mapped_column(String(20), default="user")
    # Tier: "free" | "premium". premium_until = NULL means no expiry (admin
    # comped); a future billing system sets plan + premium_until on purchase
    # and deps.is_premium() is the single place that interprets both.
    plan: Mapped[str] = mapped_column(String(20), default="free", server_default="free")
    premium_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Optional friendly name shown in the UI (collected at passwordless register).
    display_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    # Filename of the user's uploaded avatar within uploads/<id>/ (NULL = none, we
    # fall back to their initial). Only the file NAME is stored here; the bytes live
    # privately on disk and are served by GET /options/avatar (owner-only).
    avatar_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # E.164-ish phone for optional SMS 2FA; NULL until the user opts in (Phase 6).
    phone: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # Telegram alert channel: the user's private chat with the bot (NULL until
    # they connect on Options), and the one-time token used to link it.
    telegram_chat_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    telegram_link_token: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Inbox watcher (opt-in on Options): read-only IMAP access to the user's own
    # mailbox so JobBot can spot application confirmations / rejections /
    # interview invites. The password is Fernet-encrypted with a key derived
    # from SECRET_KEY (see app/inbox.py seal/unseal) — never stored plaintext.
    imap_host: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    imap_email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    imap_password: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    inbox_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    inbox_last_uid: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    inbox_scanned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # How the inbox watcher should ping this user — a list drawn from
    # ["telegram", "email", "ntfy", "discord"]. NULL = default behavior
    # (Telegram when connected, else email). ntfy_topic is a topic name on
    # ntfy.sh or a full URL for self-hosted servers; discord_webhook is a
    # Discord channel webhook URL.
    inbox_ping_channels: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    ntfy_topic: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    discord_webhook: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # When True (and a phone is set), login requires a second SMS code.
    sms_2fa_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Convenience links (deleting a user deletes their private data).
    resumes: Mapped[list["Resume"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    preferences: Mapped[Optional["Preference"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )
    matches: Mapped[list["Match"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    stars: Mapped[list["Star"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    answers: Mapped[list["ApplicationAnswer"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# resumes — uploaded resume OR cover letter, plus extracted plain text
# ---------------------------------------------------------------------------
class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # "resume" or "cover_letter"
    kind: Mapped[str] = mapped_column(String(20))
    filename: Mapped[str] = mapped_column(String(255))
    raw_text: Mapped[str] = mapped_column(Text, default="")
    # Claude/OpenAI-extracted structured profile (BUILD_SPEC). Resume-derived
    # FACTS only (skills, titles, seniority, years, locations, domains) — never
    # preferences. NULL until parsed; populated on upload + via `manage.py parse-resume`.
    parsed_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # AI resume grade: overall 0-100, four 0-25 category scores, headline and
    # prioritized suggestions (see assist.grade_resume). NULL until graded;
    # populated in the background after upload.
    grade_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Builder: a cached structured "paper" of THIS resume (name/summary/sections),
    # so the builder can preview it in any look instantly without re-parsing, and
    # the chosen template look this doc was saved with (NULL = never picked one).
    paper_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    look: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="resumes")


# ---------------------------------------------------------------------------
# preferences — one row per user (their search filters + alert settings)
# Every filter is optional; NULL/empty means "any" (no filtering on it).
# ---------------------------------------------------------------------------
class Preference(Base):
    __tablename__ = "preferences"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    country: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)  # USPS/province abbr
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    radius_miles: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # list[str], e.g. ["Remote", "Hybrid"]
    work_types: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    posted_within_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # list[str] of keywords / role titles
    keywords: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Job must mention ALL of these (AND), vs keywords which is ANY (OR).
    must_have_keywords: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # Company names to never show (substring match), and a flag to skip
    # staffing/recruiter listings.
    block_companies: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    exclude_staffing: Mapped[bool] = mapped_column(Boolean, default=False)
    # list[str] of terms that DISQUALIFY a job if found in its title/description
    exclude_keywords: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    salary_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    employment_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    seniority: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    # only alert above this resume-match score (0-100). Default 0 = no minimum.
    match_threshold: Mapped[int] = mapped_column(Integer, default=0)
    # list[str], e.g. ["email", "dashboard", "slack"]
    alert_channels: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # "instant" or "digest"
    digest_mode: Mapped[str] = mapped_column(String(20), default="digest")
    # Per-user Slack "Incoming Webhook" URL — only this user's matches are sent
    # to it, so people's alerts never mix. Blank = the Slack channel is skipped.
    slack_webhook: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    # When we last sent this user a digest (so digests fire at most once a day).
    # NULL until their first digest. Instant alerts don't use this.
    last_digest_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="preferences")


# ---------------------------------------------------------------------------
# jobs — normalized postings fetched from any source (shared "Job" shape)
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# companies — an employer whose ATS job board we ingest (BUILD_SPEC)
# ---------------------------------------------------------------------------
class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("ats_provider", "ats_id", name="uq_company_ats"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    # greenhouse | lever | ashby | aggregator
    ats_provider: Mapped[str] = mapped_column(String(20))
    # the company's board slug/id on that ATS
    ats_id: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    jobs: Mapped[list["Job"]] = relationship(back_populates="company_rec")


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (
        # The same job from the same source should only be stored once.
        UniqueConstraint("source", "external_id", name="uq_source_external_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(40), index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    title: Mapped[str] = mapped_column(String(300))
    company: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # "Remote" / "Hybrid" / "In-person"
    work_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    salary: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    posted_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # normalized title+company+location, used to dedupe across DIFFERENT sources
    dedupe_key: Mapped[str] = mapped_column(String(500), index=True)

    # --- BUILD_SPEC ATS fields (additive; the legacy columns above are still
    # populated so the existing UI + matching keep working unchanged). ----------
    company_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # spec remote_type: remote | hybrid | onsite (legacy work_type kept in parallel)
    remote_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    salary_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    salary_currency: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    # description normalized to Markdown (legacy `description` kept as plain text)
    description_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # heuristic 0..1, higher = more likely a stale/ghost posting
    ghost_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    company_rec: Mapped[Optional["Company"]] = relationship(back_populates="jobs")
    matches: Mapped[list["Match"]] = relationship(
        back_populates="job", cascade="all, delete-orphan"
    )


# ---------------------------------------------------------------------------
# matches — a (user, job) pairing with a resume-match score
# ---------------------------------------------------------------------------
class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (
        # One match row per user+job (so we never alert the same match twice).
        UniqueConstraint("user_id", "job_id", name="uq_user_job_match"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    score: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100
    # One-sentence AI explanation of the fit (NULL when scored by TF-IDF only).
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # NULL until we send an alert; set once so we never notify twice.
    notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    user: Mapped["User"] = relationship(back_populates="matches")
    job: Mapped["Job"] = relationship(back_populates="matches")


# ---------------------------------------------------------------------------
# llm_scores — cache of AI fit scores, so a resume/job pair is only ever
# scored once. Keyed by content hashes: a new resume or an edited job
# description misses the cache and gets re-scored; unchanged pairs are free.
# ---------------------------------------------------------------------------
class ApplicationKit(Base):
    """A generated, per-user-per-job application package: tailored structured
    resume, complete cover letter, drafted portal answers and a tailored
    summary (see assist.build_application_kit / tailor_resume_structured).
    Stored so viewing/downloading never re-spends AI calls; regenerating
    overwrites in place."""

    __tablename__ = "application_kits"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_kit_user_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE", name="fk_kit_user"), index=True
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE", name="fk_kit_job"), index=True
    )
    # {"summary", "cover_letter", "answers": [{"q","a"}...], "resume": {...}, "model"}
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LlmUsage(Base):
    """One row per calendar month: how many AI-scoring API calls were made.

    The monthly cap (JOBBOT_LLM_MONTHLY_CAP) is enforced against this counter
    so public signups can't run up the OpenAI bill — see app/llm_budget.py.
    """

    __tablename__ = "llm_usage"

    month: Mapped[str] = mapped_column(String(7), primary_key=True)  # "2026-07"
    calls: Mapped[int] = mapped_column(Integer, default=0)


class SourceUsage(Base):
    """Per-service, per-calendar-month API call counter, so metered job
    sources (e.g. JSearch's ~200 req/mo free tier) can enforce a hard cap and
    never run up a bill. See app/source_budget.py."""

    __tablename__ = "source_usage"
    __table_args__ = (
        UniqueConstraint("service", "month", name="uq_source_usage_service_month"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    service: Mapped[str] = mapped_column(String(40), index=True)  # "jsearch"
    month: Mapped[str] = mapped_column(String(7))  # "2026-07"
    calls: Mapped[int] = mapped_column(Integer, default=0)


class LlmScore(Base):
    __tablename__ = "llm_scores"
    __table_args__ = (
        UniqueConstraint("resume_hash", "job_id", name="uq_llmscore_resume_job"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE", name="fk_llmscore_job"), index=True
    )
    resume_hash: Mapped[str] = mapped_column(String(64), index=True)
    job_hash: Mapped[str] = mapped_column(String(64))  # hash of the text scored
    score: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100
    reason: Mapped[str] = mapped_column(Text, default="")
    model: Mapped[str] = mapped_column(String(80), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# stars — jobs a user flagged to act on (tailor resume / answer questions)
# ---------------------------------------------------------------------------
class Star(Base):
    __tablename__ = "stars"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id", name="uq_user_job_star"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    # e.g. "interested", "applied", "rejected"
    status: Mapped[str] = mapped_column(String(30), default="interested")
    # When the post-apply follow-up nudge was sent (NULL = not yet; only
    # meaningful while status == "applied"). See app/followups.py.
    followup_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="stars")


# ---------------------------------------------------------------------------
# inbox_events — one row per actionable email the inbox watcher handled
# (application confirmation / rejection / interview / offer). The unique
# (user, message_id) pair guarantees a message can never trigger twice, even
# if the incremental UID cursor is ever reset.
# ---------------------------------------------------------------------------
class InboxEvent(Base):
    __tablename__ = "inbox_events"
    __table_args__ = (
        UniqueConstraint("user_id", "message_id", name="uq_inbox_user_message"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    message_id: Mapped[str] = mapped_column(String(255))
    # "application_confirmation" | "rejection" | "interview" | "offer"
    kind: Mapped[str] = mapped_column(String(30))
    job_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    subject: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------------------------------------------------------------------------
# application_answers — drafted answers to a job's application questions
# ---------------------------------------------------------------------------
class ApplicationAnswer(Base):
    __tablename__ = "application_answers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    question: Mapped[str] = mapped_column(Text)
    draft_answer: Mapped[str] = mapped_column(Text, default="")
    final_answer: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="answers")


# ---------------------------------------------------------------------------
# invites — one-time tokens an admin creates so a new person can register
# ---------------------------------------------------------------------------
class Invite(Base):
    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    # optional: pre-fill / restrict which email may use this invite
    email: Mapped[Optional[str]] = mapped_column(String(320), nullable=True)
    created_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    used_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def is_used(self) -> bool:
        return self.used_at is not None


# ---------------------------------------------------------------------------
# login_codes — short-lived 6-digit codes for passwordless login + SMS 2FA
# The plaintext code is NEVER stored; only a bcrypt hash. Codes expire and are
# attempt-capped (enforced in app/web/login_codes.py).
# ---------------------------------------------------------------------------
class LoginCode(Base):
    __tablename__ = "login_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stored lowercased; not unique (a person can request several over time).
    email: Mapped[str] = mapped_column(String(320), index=True)
    # bcrypt hash of the 6-digit code — never the plaintext.
    code_hash: Mapped[str] = mapped_column(String(255))
    # "login" (emailed code) or "sms" (second-factor code).
    purpose: Mapped[str] = mapped_column(String(20))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    # Set once the code is used or invalidated; NULL while still usable.
    consumed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
