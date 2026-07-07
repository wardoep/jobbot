"""
Central settings for JobBot.

Every secret/knob the app needs is read here from the ``.env`` file (or real
environment variables). Nothing else in the codebase reads ``.env`` directly —
that keeps secrets in ONE place and out of the source code.

Usage anywhere in the app:
    from app.config import settings
    settings.database_url        # the DB connection string actually used
    settings.anthropic_api_key   # may be empty until you fill it in
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Folder that contains this project (where .env and jobbot.db live).
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    # Pydantic reads these from .env (case-insensitive) or the environment.
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # ignore unrelated env vars instead of crashing
    )

    # --- Database -------------------------------------------------------------
    # Read from the env var DATABASE_URL. Blank means "use local SQLite"
    # (handled by the database_url property below).
    raw_database_url: str = Field(default="", validation_alias="DATABASE_URL")

    # --- App ------------------------------------------------------------------
    secret_key: str = Field(default="", validation_alias="SECRET_KEY")
    # Public URL of the app, used to build "view your matches" links inside
    # alert emails/messages. Locally this is the dev server; in the cloud
    # (Phase 9) set it to your real domain.
    app_base_url: str = Field(
        default="http://localhost:8000", validation_alias="APP_BASE_URL"
    )
    # Where the web server listens (Phase 9). 127.0.0.1 = this machine only (safe
    # default); set WEB_HOST=0.0.0.0 to expose it on the network (put it behind a
    # reverse proxy + firewall if you do).
    web_host: str = Field(default="127.0.0.1", validation_alias="WEB_HOST")
    web_port: int = Field(default=8000, validation_alias="WEB_PORT")

    # --- DataImpulse proxy ----------------------------------------------------
    proxy_url: str = Field(default="", validation_alias="PROXY_URL")
    proxy_host: str = Field(default="gw.dataimpulse.com", validation_alias="PROXY_HOST")
    proxy_port: str = Field(default="823", validation_alias="PROXY_PORT")
    proxy_user: str = Field(default="", validation_alias="PROXY_USER")
    proxy_pass: str = Field(default="", validation_alias="PROXY_PASS")

    # --- Job source API keys --------------------------------------------------
    adzuna_app_id: str = Field(default="", validation_alias="ADZUNA_APP_ID")
    adzuna_app_key: str = Field(default="", validation_alias="ADZUNA_APP_KEY")
    usajobs_api_key: str = Field(default="", validation_alias="USAJOBS_API_KEY")
    usajobs_email: str = Field(default="", validation_alias="USAJOBS_EMAIL")
    # JSearch (RapidAPI) — Google-for-Jobs feed: LinkedIn/Indeed/Glassdoor/ZipRecruiter.
    jsearch_api_key: str = Field(default="", validation_alias="JSEARCH_API_KEY")
    # Hard monthly request cap for JSearch (its free tier is ~200/mo). 0 = unlimited.
    jsearch_monthly_cap: int = Field(default=180, validation_alias="JSEARCH_MONTHLY_CAP")

    # --- AI match scoring knobs (layer three) --------------------------------
    llm_scoring_enabled: bool = Field(default=True, validation_alias="JOBBOT_LLM_SCORING")
    llm_top_k: int = Field(default=120, validation_alias="JOBBOT_LLM_TOP_K")
    # Max AI-scoring API calls per calendar month (0 = unlimited).
    llm_monthly_cap: int = Field(default=1000, validation_alias="JOBBOT_LLM_MONTHLY_CAP")

    # --- Telegram (alert channel + notifications) ------------------------------
    telegram_bot_token: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_bot_username: str = Field(
        default="", validation_alias="TELEGRAM_BOT_USERNAME"
    )

    # --- Automation: auto-kits + follow-up nudges ------------------------------
    # Build an Application Kit automatically for new matches at/above this score…
    auto_kit_threshold: int = Field(default=80, validation_alias="JOBBOT_AUTO_KIT_THRESHOLD")
    # …capped per user per day (0 turns auto-kits off).
    auto_kits_per_day: int = Field(default=3, validation_alias="JOBBOT_AUTO_KITS_PER_DAY")
    # Nudge with a drafted follow-up N days after "applied" (0 turns it off).
    followup_days: int = Field(default=7, validation_alias="JOBBOT_FOLLOWUP_DAYS")

    # --- LLM: resume tailoring + application Q&A (Phase 6) --------------------
    # The provider is swappable (the same idea as the matching scorer): pick the
    # implementation by name and read its key/model from .env. Default: OpenAI.
    llm_provider: str = Field(default="openai", validation_alias="LLM_PROVIDER")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    # A sensible low-cost default; override in .env with OPENAI_MODEL.
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")
    # Kept for a future Anthropic provider (not wired up — we default to OpenAI).
    anthropic_api_key: str = Field(default="", validation_alias="ANTHROPIC_API_KEY")

    @property
    def llm_configured(self) -> bool:
        """True when the chosen LLM provider has the key it needs."""
        if self.llm_provider.strip().lower() == "openai":
            return bool(self.openai_api_key.strip())
        return False

    @property
    def proxy_for_requests(self) -> str:
        """Full proxy URL the Tier B scrapers route through (Phase 7).

        Prefer the ready-made PROXY_URL; otherwise assemble one from the
        host/port/user/pass parts. Empty string means "no proxy configured".
        """
        if self.proxy_url.strip():
            return self.proxy_url.strip()
        if self.proxy_user and self.proxy_pass:
            return (
                f"http://{self.proxy_user}:{self.proxy_pass}"
                f"@{self.proxy_host}:{self.proxy_port}"
            )
        return ""

    @property
    def proxy_configured(self) -> bool:
        return bool(self.proxy_for_requests)

    # --- Email alerts (Phase 5) ----------------------------------------------
    # Two ways to send email; JobBot picks the first one that's filled in:
    #   1. SMTP  — works with Gmail, Fastmail, your own mail server, etc.
    #   2. SendGrid API — if you'd rather use their HTTP API + key.
    # If NEITHER is configured, JobBot runs in "dry-run" mode: it prints the
    # email to the log instead of sending, so the whole pipeline is testable
    # before you set up a mail account.
    smtp_host: str = Field(default="", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=587, validation_alias="SMTP_PORT")
    smtp_user: str = Field(default="", validation_alias="SMTP_USER")
    smtp_password: str = Field(default="", validation_alias="SMTP_PASSWORD")
    # TLS: True = STARTTLS (port 587, the common case). Set False only for an
    # unencrypted local relay.
    smtp_use_tls: bool = Field(default=True, validation_alias="SMTP_USE_TLS")
    sendgrid_api_key: str = Field(default="", validation_alias="SENDGRID_API_KEY")
    # Resend (https://resend.com) transactional email API. When RESEND_API_KEY is
    # set it becomes the active transport (preferred over SMTP/SendGrid), so login
    # codes + alerts go out from your verified domain instead of a personal inbox.
    resend_api_key: str = Field(default="", validation_alias="RESEND_API_KEY")
    # The verified no-reply "From" used by Resend. Accepts "Name <addr>" form.
    resend_from: str = Field(
        default="JobBot <codes@example.com>", validation_alias="RESEND_FROM"
    )
    # The "From" address alerts are sent as. Defaults to SMTP_USER if blank.
    email_from: str = Field(default="", validation_alias="EMAIL_FROM")

    # --- Scheduler (Phase 5) --------------------------------------------------
    # How often the always-on loop polls sources + re-matches + alerts.
    scheduler_interval_minutes: int = Field(
        default=30, validation_alias="SCHEDULER_INTERVAL_MINUTES"
    )
    # Digest users get at most one digest per this many hours (default daily).
    digest_interval_hours: int = Field(
        default=24, validation_alias="DIGEST_INTERVAL_HOURS"
    )

    @property
    def email_sender(self) -> str:
        """The address outgoing alerts are 'From'. Falls back to SMTP_USER."""
        return (self.email_from or self.smtp_user or "jobbot@localhost").strip()

    @property
    def email_mode(self) -> str:
        """Which transport send_email() uses: 'resend', 'smtp', 'sendgrid', or 'dry-run'.

        Resend wins when its key is set, so adding RESEND_API_KEY swaps delivery to
        the verified domain without removing the SMTP fallback config.
        """
        if self.resend_api_key.strip():
            return "resend"
        if self.smtp_host.strip():
            return "smtp"
        if self.sendgrid_api_key.strip():
            return "sendgrid"
        return "dry-run"

    # --- SMS 2FA via Twilio (Phase 2; dormant until a user opts in) -----------
    # Optional second-factor codes. If all three are set, send_sms() uses the
    # Twilio REST API; otherwise it runs in "dry-run" mode (logs the message)
    # so the login flow is fully testable with no Twilio account.
    twilio_account_sid: str = Field(default="", validation_alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", validation_alias="TWILIO_AUTH_TOKEN")
    twilio_from: str = Field(default="", validation_alias="TWILIO_FROM")

    @property
    def sms_mode(self) -> str:
        """Which transport send_sms() will use: 'twilio' or 'dry-run'."""
        if (
            self.twilio_account_sid.strip()
            and self.twilio_auth_token.strip()
            and self.twilio_from.strip()
        ):
            return "twilio"
        return "dry-run"

    @property
    def database_url(self) -> str:
        """The connection string SQLAlchemy actually uses.

        If DATABASE_URL is blank we default to a local SQLite file so the app
        runs with zero database setup during development.
        """
        if self.raw_database_url.strip():
            return self.raw_database_url.strip()
        return f"sqlite:///{PROJECT_ROOT / 'jobbot.db'}"

    @property
    def using_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


settings = Settings()
