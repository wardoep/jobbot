"""
LLM providers for resume tailoring + application Q&A (Phase 6).

Swappable by design, defaulting to OpenAI:

    from app.llm import get_default_provider
    provider = get_default_provider()
    reply = provider.complete("You are helpful.", "Say hi.")

Change vendors by setting LLM_PROVIDER in .env (only "openai" ships today; add a
class + one registry line to support another).
"""

from __future__ import annotations

from typing import Optional

from app.config import settings
from app.llm.base import LLMError, LLMProvider
from app.llm.openai_provider import OpenAIProvider

#: known providers by name; add new ones here
_PROVIDERS: dict[str, type[LLMProvider]] = {
    "openai": OpenAIProvider,
}


def get_provider(name: Optional[str] = None) -> LLMProvider:
    """Build a provider by name (default: LLM_PROVIDER from .env, else openai)."""
    key = (name or settings.llm_provider or "openai").strip().lower()
    provider_cls = _PROVIDERS.get(key)
    if provider_cls is None:
        known = ", ".join(sorted(_PROVIDERS))
        raise LLMError(f"Unknown LLM provider {key!r}. Available: {known}.")
    return provider_cls()


def get_default_provider() -> LLMProvider:
    """The active provider. Swap LLM_PROVIDER in .env to change vendors later."""
    return get_provider()


__all__ = [
    "LLMProvider",
    "LLMError",
    "OpenAIProvider",
    "get_provider",
    "get_default_provider",
]
