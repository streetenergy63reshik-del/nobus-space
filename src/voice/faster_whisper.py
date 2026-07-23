"""Faster-Whisper transcription provider."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .base import TranscriptResult, VoiceTranscriptionError


class FasterWhisperTranscriber:
    """Lazy faster-whisper transcriber.

    Importing this module does not require ``faster-whisper`` to be installed.
    The package is imported only when ``transcribe`` is first called, the
    model is loaded lazily, and the whole synchronous pipeline (model load,
    ``transcribe``, full segment iteration and result assembly) runs in a
    worker thread via ``asyncio.to_thread``.
    """

    def __init__(
        self,
        model_size: str = "base",
        device: str = "cpu",
        compute_type: str = "int8",
        download_root: str | Path | None = None,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._download_root = (
            str(Path(download_root).resolve()) if download_root is not None else None
        )
        self._model: Any | None = None
        self._model_lock = threading.Lock()

    def _load_model(self) -> None:
        import_failed = False
        try:
            import faster_whisper
        except ImportError:
            import_failed = True
        if import_failed:
            raise VoiceTranscriptionError(
                "faster-whisper is not available; "
                "install it to use FasterWhisperTranscriber"
            ) from None
        options: dict[str, object] = {
            "device": self._device,
            "compute_type": self._compute_type,
        }
        if self._download_root is not None:
            options["download_root"] = self._download_root
        self._model = faster_whisper.WhisperModel(self._model_size, **options)

    def _transcribe_sync(self, path: Path, max_chars: int) -> TranscriptResult:
        """Synchronous transcription pipeline; runs entirely in a worker thread."""
        with self._model_lock:
            if self._model is None:
                self._load_model()
            model = self._model

        segments, info = model.transcribe(str(path))
        parts: list[str] = []
        length = 0
        for segment in segments:
            part = segment.text
            if not isinstance(part, str):
                raise VoiceTranscriptionError("transcription result is malformed")
            length += len(part)
            if length > max_chars:
                raise VoiceTranscriptionError("transcription result exceeds max length")
            parts.append(part)
        text = "".join(parts)
        language = getattr(info, "language", None)
        confidence = getattr(info, "language_probability", None)

        malformed = False
        try:
            return TranscriptResult(text=text, language=language, confidence=confidence)
        except ValidationError:
            malformed = True
        if malformed:
            raise VoiceTranscriptionError("transcription result is malformed") from None
        raise RuntimeError("unreachable")  # pragma: no cover

    async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
        """Transcribe the audio file at ``path``."""
        if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars <= 0:
            raise VoiceTranscriptionError("transcription limit is invalid")
        return await asyncio.to_thread(self._transcribe_sync, path, max_chars)
