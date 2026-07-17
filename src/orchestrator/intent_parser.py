"""Intent parser with rule-based fast path and optional LLM fallback."""

from __future__ import annotations

import re
from typing import Any

from src.config import settings
from src.models.task import UserRequest


class ParsedIntent:
    """Result of intent parsing."""

    def __init__(
        self,
        intent: str,
        confidence: float,
        payload: dict[str, Any],
    ) -> None:
        self.intent = intent
        self.confidence = confidence
        self.payload = payload


class IntentParser:
    """Rule-based parser with an optional LLM fallback.

    The LLM fallback is a pluggable hook. By default it uses lightweight
    keyword heuristics so tests pass without an API key. In production it
    can be replaced with a real LLM call.
    """

    # Mapping of regex patterns to intents and default payload keys.
    PATTERNS: list[tuple[str, str, dict[str, Any]]] = [
        (r"^/audit\s+(ozon|wb|wildberries)", "audit", {}),
        (r"^/report", "report", {}),
        (r"^/status", "status", {}),
        (r"^/help", "help", {}),
        (r"аудит\s+(озон|ozon)", "audit", {"marketplace": "ozon"}),
        (r"аудит\s+(вб|wildberries|wb)", "audit", {"marketplace": "wb"}),
        (r"отч[ёе]т", "report", {}),
        (r"статус", "status", {}),
    ]

    def __init__(self, llm_enabled: bool | None = None) -> None:
        """Initialize parser. llm_enabled=None reads from config."""
        self.llm_enabled = settings.llm_enabled if llm_enabled is None else llm_enabled

    async def parse(self, request: UserRequest) -> ParsedIntent:
        """Parse raw user text into intent and payload."""
        text = request.raw_text.strip().lower()

        # Fast path: rules first (Ponytail token-saving pattern).
        for pattern, intent, defaults in self.PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                payload = dict(defaults)
                # If the regex has a capture group, use it as marketplace.
                if match.groups():
                    captured = match.group(1).lower()
                    if intent == "audit":
                        payload["marketplace"] = "wb" if captured in {"wb", "wildberries", "вб"} else captured
                return ParsedIntent(intent=intent, confidence=1.0, payload=payload)

        # Fallback path: only if LLM is enabled.
        if self.llm_enabled:
            return await self._llm_fallback(request)

        return ParsedIntent(intent="unknown", confidence=0.0, payload={"raw_text": request.raw_text})

    async def _llm_fallback(self, request: UserRequest) -> ParsedIntent:
        """Fallback intent recognition via LLM or heuristics.

        Override this method to plug in a real LLM.
        """
        text = request.raw_text.lower()

        # Lightweight heuristic fallback (no external call).
        if "аудит" in text or "audit" in text:
            return ParsedIntent(intent="audit", confidence=0.7, payload={"marketplace": "unknown"})
        if "отчёт" in text or "report" in text:
            return ParsedIntent(intent="report", confidence=0.7, payload={})
        if "статус" in text or "status" in text:
            return ParsedIntent(intent="status", confidence=0.7, payload={})

        return ParsedIntent(intent="unknown", confidence=0.0, payload={"raw_text": request.raw_text})
