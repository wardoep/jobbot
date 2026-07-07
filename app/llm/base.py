"""
The LLM provider interface — JobBot's swappable "writer".

Phase 6 (resume tailoring + application Q&A) needs a large language model. We hide
the specific vendor behind ONE small interface, exactly the way the matching
scorer hides TF-IDF-vs-embeddings (see app/matching/scorer.py). The rest of the
app calls `provider.complete(system, user)` and never cares which company runs the
model.

To add another provider later (e.g. Anthropic), implement `complete()` in a new
class and register it in app/llm/__init__.py — nothing else in the app changes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class LLMError(Exception):
    """A user-friendly LLM failure (not configured, network, or API error)."""


class LLMProvider(ABC):
    #: short id, handy for logging / showing which engine produced the text
    name: str = "base"
    #: the concrete model id in use (e.g. "gpt-4o-mini")
    model: str = ""

    @abstractmethod
    def is_configured(self) -> bool:
        """True when this provider has the key/settings it needs to run."""
        raise NotImplementedError

    @abstractmethod
    def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        max_output_tokens: int = 800,
        temperature: float = 0.4,
    ) -> str:
        """Return the model's text reply to a system + user prompt.

        `json_mode` asks the model to reply with a single JSON object.
        Raises `LLMError` on any problem (not configured, network, API error).
        """
        raise NotImplementedError
