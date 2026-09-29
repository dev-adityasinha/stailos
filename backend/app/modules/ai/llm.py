"""Minimal LLM client for the AI module.

Talks to any OpenAI-compatible `/chat/completions` endpoint. The default
base URL is Groq's, because that is what the STAIL Realty OS agents
(`agents/shared/shared/base_agent.py`) use — same models, same wire format —
so a Groq key drops straight in. Point `AI_LLM_BASE_URL` elsewhere and it
works against any other OpenAI-compatible gateway.

Nothing here knows about CRM entities: callers hand over a system prompt and
a user message and get back text or parsed JSON. Every failure path raises
`LLMError` so the provider layer can fall back to deterministic output rather
than surfacing a broken widget.
"""
import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings

logger = logging.getLogger("crm.ai.llm")


class LLMError(RuntimeError):
    """Any failure talking to the model, or any unusable response."""


def parse_inr(text: str | None) -> int | None:
    """Parse Indian currency shorthand to whole rupees.

    Ported from STAIL's buyer agent (`_parse_inr`) and widened to tolerate the
    forms people actually type: "1.5Cr", "₹ 50 lakh", "2 crore", "8000000".
    """
    if not text:
        return None
    cleaned = str(text).strip().lower().replace(",", "").replace("₹", "").replace("rs.", "")
    cleaned = cleaned.replace("rs", "").replace(" ", "")
    match = re.match(r"^([\d.]+)(cr|crore|crores|l|lakh|lakhs|lac|lacs|k)$", cleaned)
    if match:
        value, unit = float(match.group(1)), match.group(2)
        if unit.startswith("cr"):
            return int(value * 10_000_000)
        if unit == "k":
            return int(value * 1_000)
        return int(value * 100_000)
    try:
        return int(float(cleaned))
    except (TypeError, ValueError):
        return None


def extract_json(text: str) -> dict[str, Any]:
    """Pull the first JSON object out of a model response.

    Models wrap JSON in prose or ```json fences even when told not to, so the
    braces are located rather than trusted — the same recovery STAIL's buyer
    agent does before `json.loads`.
    """
    candidate = (text or "").strip()
    if not candidate:
        raise LLMError("empty model response")
    match = re.search(r"\{.*\}", candidate, re.DOTALL)
    if match:
        candidate = match.group(0)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise LLMError(f"model did not return JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMError("model returned JSON but not an object")
    return parsed


class LLMClient:
    """Blocking chat-completions client.

    Blocking on purpose: every caller is inside a synchronous FastAPI route
    holding a SQLAlchemy session, so an async client would buy nothing and
    force the whole AI service layer to go async.
    """

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    @classmethod
    def from_settings(cls) -> "LLMClient":
        settings = get_settings()
        if not settings.ai_llm_api_key:
            raise LLMError("AI_LLM_API_KEY is not set")
        return cls(
            api_key=settings.ai_llm_api_key,
            base_url=settings.ai_llm_base_url,
            model=settings.ai_llm_model,
            timeout=settings.ai_llm_timeout_seconds,
        )

    def chat(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 700,
        temperature: float = 0.2,
        json_mode: bool = False,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as exc:
            # Body carries the actual reason (bad model name, quota, bad key).
            raise LLMError(
                f"LLM HTTP {exc.response.status_code}: {exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        except ValueError as exc:
            raise LLMError(f"LLM returned non-JSON body: {exc}") from exc

        choices = body.get("choices") or []
        if not choices:
            raise LLMError("LLM returned no choices")
        content = (choices[0].get("message") or {}).get("content") or ""
        if not content.strip():
            raise LLMError("LLM returned empty content")
        return content

    def chat_json(
        self,
        system: str,
        user: str,
        *,
        max_tokens: int = 700,
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        """Ask for JSON and parse it.

        `response_format` is requested first because Groq and OpenAI both honour
        it; gateways that reject the field fall back to a plain call plus brace
        extraction rather than failing the whole widget.
        """
        try:
            text = self.chat(
                system, user, max_tokens=max_tokens, temperature=temperature, json_mode=True
            )
        except LLMError as exc:
            if "HTTP 4" not in str(exc):
                raise
            logger.info("json_mode rejected by gateway, retrying without it: %s", exc)
            text = self.chat(system, user, max_tokens=max_tokens, temperature=temperature)
        return extract_json(text)


def mentions_any(text: str, needles: list[str | None]) -> bool:
    """Hallucination guard, ported from STAIL's recommendation agent.

    A generated blurb about a specific property must name something real about
    it (project, city, locality). If it names nothing, it is discarded in
    favour of a template.
    """
    haystack = (text or "").lower()
    return any(n and str(n).strip() and str(n).lower() in haystack for n in needles)
