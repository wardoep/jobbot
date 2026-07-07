"""The curated list of companies whose public ATS job boards we ingest.

Each entry is (display_name, ats_provider, ats_id/slug). All slugs below were
verified to return live postings at build time. The ingester upserts each into the
`companies` table, fetches its board via the matching adapter, and skips any feed
that 404s or errors so one dead company never breaks the run.
"""

from __future__ import annotations

# (name, ats_provider, ats_id)  — ~15 real companies across Greenhouse/Lever/Ashby
ATS_COMPANIES: list[tuple[str, str, str]] = [
    # --- Greenhouse ---
    ("Stripe", "greenhouse", "stripe"),
    ("Airbnb", "greenhouse", "airbnb"),
    ("Datadog", "greenhouse", "datadog"),
    ("Figma", "greenhouse", "figma"),
    ("GitLab", "greenhouse", "gitlab"),
    ("Brex", "greenhouse", "brex"),
    ("Reddit", "greenhouse", "reddit"),
    ("Anthropic", "greenhouse", "anthropic"),
    # --- Ashby ---
    ("Notion", "ashby", "notion"),
    ("Ramp", "ashby", "ramp"),
    ("Linear", "ashby", "linear"),
    ("OpenAI", "ashby", "openai"),
    # --- Lever ---
    ("Spotify", "lever", "spotify"),
    ("Mistral AI", "lever", "mistral"),
    ("Match Group", "lever", "matchgroup"),
]
