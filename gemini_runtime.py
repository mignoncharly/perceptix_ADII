"""
Gemini Runtime Utilities

Centralizes Gemini calls with:
- Per-cycle call budgeting
- Simple response caching
- Structured JSON generation support

This keeps "more Gemini calls" safe (no runaway cost) while still enabling a richer
reasoning trace for demos and audits.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional, Tuple

try:
    from google import genai
    from google.genai import types

    GEMINI_AVAILABLE = True
except Exception:  # pragma: no cover
    genai = None
    types = None
    GEMINI_AVAILABLE = False

logger = logging.getLogger("GeminiRuntime")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class GeminiBudget:
    max_calls: int = 8
    max_prompt_chars: int = 140_000


@dataclass
class GeminiSession:
    trace_id: str
    model_name: str
    provider: str = "google-genai"
    budget: GeminiBudget = field(default_factory=GeminiBudget)
    call_count: int = 0
    cache_hits: int = 0

    def check_call_allowed(self) -> None:
        if self.call_count >= self.budget.max_calls:
            raise RuntimeError(f"Gemini call budget exceeded (max_calls={self.budget.max_calls})")


class GeminiRuntime:
    def __init__(self, api_key: Optional[str], model_name: str, enable_cache: bool = True, cache_max_entries: int = 2048):
        self.api_key = api_key
        self.model_name = model_name
        self.enable_cache = bool(enable_cache)
        self.cache_max_entries = int(cache_max_entries)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._client = None

        if api_key and GEMINI_AVAILABLE:
            self._client = genai.Client(api_key=api_key)

    @property
    def available(self) -> bool:
        return self._client is not None

    def _cache_get(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.enable_cache:
            return None
        return self._cache.get(key)

    def _cache_put(self, key: str, value: Dict[str, Any]) -> None:
        if not self.enable_cache:
            return
        if len(self._cache) >= self.cache_max_entries:
            # Drop an arbitrary entry to cap memory; good enough for hackathon scale.
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = value

    def generate_json(
        self,
        *,
        session: GeminiSession,
        stage: str,
        prompt: str,
        mock_fn: Callable[[], Dict[str, Any]],
        timeout_s: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        """
        Returns (payload_json, trace_meta).
        """
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("prompt must be a non-empty string")

        if len(prompt) > session.budget.max_prompt_chars:
            raise RuntimeError(f"prompt too large for budget (len={len(prompt)} chars)")

        prompt_hash = _sha256(session.model_name + "\n" + stage + "\n" + prompt)
        cached = self._cache_get(prompt_hash)
        if cached is not None:
            session.cache_hits += 1
            return cached["payload"], {
                "timestamp": _utc_now_iso(),
                "trace_id": session.trace_id,
                "stage": stage,
                "provider": session.provider,
                "model_name": session.model_name,
                "api_used": bool(self.available),
                "cache_hit": True,
                "prompt_hash": prompt_hash,
                "latency_ms": 0.0,
            }

        session.check_call_allowed()
        session.call_count += 1

        started = time.time()
        if self.available:
            try:
                cfg = None
                if types is not None:
                    cfg = types.GenerateContentConfig(response_mime_type="application/json")
                response = self._client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=cfg,
                )
                text = getattr(response, "text", None)
                if not text:
                    raise RuntimeError("empty response from Gemini")
                payload = json.loads(text)
            except Exception as e:
                logger.warning("Gemini stage=%s failed, falling back to mock. error=%s", stage, e)
                payload = mock_fn()
        else:
            payload = mock_fn()

        latency_ms = (time.time() - started) * 1000
        meta = {
            "timestamp": _utc_now_iso(),
            "trace_id": session.trace_id,
            "stage": stage,
            "provider": session.provider if self.available else "mock",
            "model_name": session.model_name if self.available else None,
            "api_used": bool(self.available),
            "cache_hit": False,
            "prompt_hash": prompt_hash,
            "latency_ms": round(latency_ms, 2),
        }

        self._cache_put(prompt_hash, {"payload": payload})
        return payload, meta

