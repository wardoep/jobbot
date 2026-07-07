"""
OpenAI implementation of the LLMProvider interface.

We call OpenAI's Chat Completions REST API directly with httpx — the same
lightweight approach app/alerts/email.py uses for SendGrid — so Phase 6 adds no
new Python dependency.

Privacy (spec section 12): we never log prompt or reply text, because it contains
the user's resume content. Only high-level errors are surfaced.
"""

from __future__ import annotations

from typing import Optional

import httpx

from app.config import settings
from app.llm.base import LLMError, LLMProvider

API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        key = api_key if api_key is not None else settings.openai_api_key
        self._api_key = (key or "").strip()
        self.model = (model or settings.openai_model or "gpt-4o-mini").strip()

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        max_output_tokens: int = 800,
        temperature: float = 0.4,
    ) -> str:
        if not self.is_configured():
            raise LLMError(
                "OpenAI is not configured. Add OPENAI_API_KEY to your .env file."
            )

        # Note: gpt-4o-mini (the default) accepts `max_tokens` + `temperature`.
        # Some newer reasoning models want `max_completion_tokens` and fixed
        # temperature; if you override OPENAI_MODEL to one of those and see an
        # error, that's why.
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
            "max_tokens": max_output_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            resp = httpx.post(
                API_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=60,
            )
        except Exception as exc:  # network / DNS / timeout
            raise LLMError(f"Could not reach OpenAI: {exc}") from exc

        if resp.status_code >= 400:
            raise LLMError(
                f"OpenAI API error (HTTP {resp.status_code}): {_extract_error(resp)}"
            )

        try:
            data = resp.json()
            return data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError) as exc:
            raise LLMError(f"Unexpected response from OpenAI: {exc}") from exc


def _extract_error(resp: httpx.Response) -> str:
    """Pull a human-readable message out of an OpenAI error response."""
    try:
        msg = resp.json().get("error", {}).get("message")
        if msg:
            return msg
    except ValueError:
        pass
    return (resp.text or "")[:200]
