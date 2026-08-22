"""Pluggable LLM provider abstraction — all free.

Providers (in priority order):
  GroqProvider   — free API, 30 req/min, Llama 3.3 70B (RECOMMENDED)
  GeminiProvider — free API, 15 req/min, Gemini 2.0 Flash
  OllamaProvider — local, unlimited, offline
  MockProvider   — deterministic, no downloads, instant (DEFAULT fallback)

Every provider implements generate() for text and generate_json() for
structured output. All have automatic retry with exponential backoff.
"""
from __future__ import annotations

import json
import re
import time
import logging
from abc import ABC, abstractmethod

import httpx

from app.config import settings

logger = logging.getLogger("lifepilot.llm")


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, prompt: str, *, system: str | None = None) -> str:
        ...

    def generate_json(self, prompt: str, *, system: str | None = None) -> dict:
        """Generate structured JSON output. Extracts JSON from the response."""
        raw = self.generate(prompt, system=system)
        return _extract_json(raw)

    def available(self) -> bool:
        return True


def _extract_json(text: str) -> dict:
    """Best-effort JSON extraction from LLM output."""
    # Try direct parse first
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass
    # Try extracting from markdown code block
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:
            pass
    # Try finding any JSON object/array in the text
    for pattern in [r"\{[\s\S]*\}", r"\[[\s\S]*\]"]:
        m = re.search(pattern, text)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                continue
    logger.warning("Could not extract JSON from LLM response, returning empty dict")
    return {}


def _retry(fn, max_retries: int = 3, base_delay: float = 1.0):
    """Execute fn with exponential backoff retries."""
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if attempt == max_retries - 1:
                logger.error(f"All {max_retries} retries failed: {e}")
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(f"Attempt {attempt + 1} failed ({e}), retrying in {delay}s...")
            time.sleep(delay)


# ─────────────────────────────────────────────────────────────
# Groq — FREE, fast, Llama 3.3 70B
# ─────────────────────────────────────────────────────────────
class GroqProvider(LLMProvider):
    """Groq Cloud (free tier). Fast inference on Llama/Qwen/Gemma models."""

    name = "groq"

    def __init__(self) -> None:
        self.api_key = settings.groq_api_key
        self.model = settings.groq_model
        self._fallback = MockProvider()

    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        if not self.available():
            return self._fallback.generate(prompt, system=system)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        def _call():
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": 0.4,
                        "max_tokens": 4096,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()

        try:
            return _retry(_call)
        except Exception as e:
            logger.error(f"Groq failed: {e}")
            return self._fallback.generate(prompt, system=system)


# ─────────────────────────────────────────────────────────────
# Gemini — FREE, Google AI
# ─────────────────────────────────────────────────────────────
class GeminiProvider(LLMProvider):
    """Google Gemini (free tier). Gemini 2.0 Flash."""

    name = "gemini"

    def __init__(self) -> None:
        self.api_key = settings.gemini_api_key
        self.model = settings.gemini_model
        self._fallback = MockProvider()

    def available(self) -> bool:
        return bool(self.api_key)

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        if not self.available():
            return self._fallback.generate(prompt, system=system)

        contents = []
        if system:
            contents.append({"role": "user", "parts": [{"text": f"[System instruction]: {system}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will follow these instructions."}]})
        contents.append({"role": "user", "parts": [{"text": prompt}]})

        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )

        def _call():
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(
                    url,
                    json={"contents": contents, "generationConfig": {"temperature": 0.4, "maxOutputTokens": 4096}},
                )
                resp.raise_for_status()
                data = resp.json()
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()

        try:
            return _retry(_call)
        except Exception as e:
            logger.error(f"Gemini failed: {e}")
            return self._fallback.generate(prompt, system=system)


# ─────────────────────────────────────────────────────────────
# Ollama — local, free, offline
# ─────────────────────────────────────────────────────────────
class OllamaProvider(LLMProvider):
    """Local Ollama. Falls back to mock if unreachable."""

    name = "ollama"

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self._fallback = MockProvider()

    def available(self) -> bool:
        try:
            with httpx.Client(timeout=2.0) as client:
                resp = client.get(f"{self.base_url}/api/tags")
                return resp.status_code == 200
        except Exception:
            return False

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        if not self.available():
            return self._fallback.generate(prompt, system=system)
        try:
            def _call():
                with httpx.Client(timeout=120.0) as client:
                    resp = client.post(
                        f"{self.base_url}/api/generate",
                        json={"model": self.model, "prompt": prompt, "system": system or "", "stream": False},
                    )
                    resp.raise_for_status()
                    return resp.json().get("response", "").strip()
            return _retry(_call) or self._fallback.generate(prompt)
        except Exception:
            return self._fallback.generate(prompt, system=system)


# ─────────────────────────────────────────────────────────────
# Mock — deterministic offline fallback
# ─────────────────────────────────────────────────────────────
class MockProvider(LLMProvider):
    """Deterministic offline engine. Returns structured template responses."""

    name = "mock"

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        return prompt.strip()

    def generate_json(self, prompt: str, *, system: str | None = None) -> dict:
        """Return a sensible default dict for offline mode."""
        return {"status": "mock", "message": "Running in offline mode — connect an LLM for real AI."}


# ─────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────
_PROVIDERS: dict[str, type[LLMProvider]] = {
    "groq": GroqProvider,
    "gemini": GeminiProvider,
    "ollama": OllamaProvider,
    "mock": MockProvider,
}

_instance: LLMProvider | None = None


def get_provider() -> LLMProvider:
    """Get the configured LLM provider (singleton)."""
    global _instance
    if _instance is None:
        factory = _PROVIDERS.get(settings.llm_provider.lower(), MockProvider)
        _instance = factory()
        if not _instance.available():
            logger.warning(f"{_instance.name} not available, falling back to mock")
            _instance = MockProvider()
        logger.info(f"LLM provider: {_instance.name}")
    return _instance


def reset_provider() -> None:
    """Reset the singleton (useful for testing or config changes)."""
    global _instance
    _instance = None
