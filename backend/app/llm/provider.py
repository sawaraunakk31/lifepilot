"""Pluggable LLM provider abstraction.

Design goal: the prototype must run with ZERO paid keys and ZERO downloads.
- MockProvider: deterministic, template-based. Always available. (DEFAULT)
- OllamaProvider: local, free, offline models via Ollama. Used only if configured
  AND reachable; otherwise we gracefully fall back to the mock.

Networking uses only Python's standard library (urllib) against http://localhost,
so NO third-party HTTP client and NO certificate bundle (.pem) is ever pulled in.
Nothing here calls a paid API or fetches unknown remote resources.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod

from app.config import settings


class LLMProvider(ABC):
    name: str = "base"

    @abstractmethod
    def generate(self, prompt: str, *, system: str | None = None) -> str: ...

    def available(self) -> bool:  # pragma: no cover - trivial
        return True


class MockProvider(LLMProvider):
    """Deterministic offline "reasoning" engine.

    It does not pretend to be a real LLM; instead it produces clean, structured
    text from the prompt so the whole pipeline is demonstrable without any model.
    The agents pass already-computed facts, so the mock simply formats them.
    """

    name = "mock"

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        # The agents build fully-formed text; the mock just returns it verbatim.
        return prompt.strip()


class OllamaProvider(LLMProvider):
    """Local Ollama provider (free, offline). Falls back to mock if unreachable.

    Uses urllib against http://localhost — plain HTTP, no TLS, no certifi.
    """

    name = "ollama"

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self._fallback = MockProvider()

    def available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                return resp.status == 200
        except Exception:
            return False

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        if not self.available():
            return self._fallback.generate(prompt, system=system)
        try:
            body = json.dumps({
                "model": self.model,
                "prompt": prompt,
                "system": system or "",
                "stream": False,
            }).encode("utf-8")
            req = urllib.request.Request(
                f"{self.base_url}/api/generate",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=60.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return (data.get("response") or "").strip() or self._fallback.generate(prompt)
        except Exception:
            return self._fallback.generate(prompt, system=system)


_PROVIDERS = {
    "mock": MockProvider,
    "ollama": OllamaProvider,
}


def get_provider() -> LLMProvider:
    factory = _PROVIDERS.get(settings.llm_provider.lower(), MockProvider)
    return factory()
