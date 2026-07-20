"""Base types and protocol for voice transcription."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VoiceTranscriptionError(Exception):
    """Safe error raised when transcription fails at the provider boundary."""


class VoiceCleanupError(Exception):
    """Safe error raised when a temporary file cannot be removed after transcription."""


class TranscriptResult(BaseModel):
    """Typed result from a voice transcription provider."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str
    language: str | None = None
    confidence: float | None = None

    @field_validator("text", mode="before")
    @classmethod
    def _validate_text(cls, value: Any) -> str:
        if isinstance(value, bool):
            raise ValueError("text must not be a bool")
        if not isinstance(value, str):
            raise ValueError("text must be a string")
        return value

    @field_validator("language", mode="before")
    @classmethod
    def _normalize_language(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("language must be a string or None")
        normalized = value.strip().lower()
        return normalized if normalized else None

    @field_validator("confidence", mode="before")
    @classmethod
    def _validate_confidence(cls, value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, bool):
            raise ValueError("confidence must not be a bool")
        if not isinstance(value, (int, float)):
            raise ValueError("confidence must be a number")
        if not 0 <= value <= 1:
            raise ValueError("confidence must be between 0 and 1")
        return float(value)


class VoicePreview(BaseModel):
    """Safe preview of a voice transcription result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    transcript: str
    language: str | None = None
    confidence: float | None = None
    sha256: str
    size: int = Field(ge=0)

    @field_validator("size", mode="before")
    @classmethod
    def _validate_size(cls, value: Any) -> int:
        if isinstance(value, bool):
            raise ValueError("size must not be a bool")
        if not isinstance(value, int):
            raise TypeError("size must be an integer")
        if value < 0:
            raise ValueError("size must be non-negative")
        return value


class VoiceTranscriber(Protocol):
    """Protocol for voice transcription providers."""

    async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
        """Transcribe the audio file at ``path`` and return a typed result."""
        ...
