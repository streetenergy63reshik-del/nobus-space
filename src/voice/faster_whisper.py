"""Faster-Whisper transcription provider."""

from __future__ import annotations

import asyncio
import math
import threading
import io
import importlib.metadata
from pathlib import Path
from typing import Any

import numpy as np
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
        local_files_only: bool = False,
        language: str | None = None,
        beam_size: int = 5,
        patience: float = 1.0,
        vad_filter: bool = False,
        condition_on_previous_text: bool = True,
        initial_prompt: str | None = None,
        hotwords: str | None = None,
    ) -> None:
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type
        self._download_root = (
            str(Path(download_root).resolve()) if download_root is not None else None
        )
        if not isinstance(local_files_only, bool):
            raise ValueError("local_files_only must be a boolean")
        self._local_files_only = local_files_only
        if language is not None and (
            not isinstance(language, str) or not language.strip()
        ):
            raise ValueError("language must be a non-empty string or None")
        if (
            isinstance(beam_size, bool)
            or not isinstance(beam_size, int)
            or beam_size <= 0
        ):
            raise ValueError("beam_size must be a positive integer")
        if (
            isinstance(patience, bool)
            or not isinstance(patience, (int, float))
            or not math.isfinite(patience)
            or not 1.0 <= patience <= 2.0
        ):
            raise ValueError("patience must be between 1.0 and 2.0")
        if not isinstance(vad_filter, bool):
            raise ValueError("vad_filter must be a boolean")
        if not isinstance(condition_on_previous_text, bool):
            raise ValueError("condition_on_previous_text must be a boolean")
        for name, value in (
            ("initial_prompt", initial_prompt),
            ("hotwords", hotwords),
        ):
            if value is not None and (
                not isinstance(value, str) or not value.strip()
            ):
                raise ValueError(f"{name} must be a non-empty string or None")
        self._language = language.strip().lower() if language is not None else None
        self._beam_size = beam_size
        self._patience = float(patience)
        self._vad_filter = vad_filter
        self._condition_on_previous_text = condition_on_previous_text
        self._initial_prompt = (
            initial_prompt.strip() if initial_prompt is not None else None
        )
        self._hotwords = hotwords.strip() if hotwords is not None else None
        self._model: Any | None = None
        self._model_lock = threading.Lock()
        self._inference_lock = threading.Lock()

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
            "local_files_only": self._local_files_only,
        }
        if self._download_root is not None:
            options["download_root"] = self._download_root
        self._model = faster_whisper.WhisperModel(self._model_size, **options)

    def _model_instance(self) -> Any:
        with self._model_lock:
            if self._model is None:
                self._load_model()
            return self._model

    def _transcribe_sync(self, path: Path, max_chars: int) -> TranscriptResult:
        """Synchronous transcription pipeline; runs entirely in a worker thread."""
        return self._transcribe_input(str(path), max_chars)

    def _transcribe_input(self, source: Any, max_chars: int) -> TranscriptResult:
        model = self._model_instance()

        segments, info = model.transcribe(
            source,
            language=self._language,
            beam_size=self._beam_size,
            patience=self._patience,
            vad_filter=self._vad_filter,
            condition_on_previous_text=self._condition_on_previous_text,
            initial_prompt=self._initial_prompt,
            hotwords=self._hotwords,
        )
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
        language_confidence = getattr(info, "language_probability", None)

        malformed = False
        try:
            return TranscriptResult(text=text, language=language, language_confidence=language_confidence)
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

    def _audio_sync(self, audio: bytes, max_chars: int, cancelled: threading.Event) -> TranscriptResult:
        import av

        # Serialize the non-cancellable local worker, including decode. Cancellation
        # cannot start a second inference while the first still uses the model.
        if not self._inference_lock.acquire(blocking=False):
            raise ValueError('voice recognizer is busy')
        try:
            if cancelled.is_set():
                raise ValueError('voice recognition cancelled')
            parts: list[np.ndarray] = []
            count = 0
            resampler = av.AudioResampler(format='s16', layout='mono', rate=16000)
            with av.open(io.BytesIO(audio), mode='r') as container:
                if container.format.name not in {'ogg','wav'} or len(container.streams.audio) != 1 or container.streams.video:
                    raise ValueError('voice media is invalid')
                for frame in container.decode(audio=0):
                    if cancelled.is_set():
                        raise ValueError('voice recognition cancelled')
                    if (not 8000 <= frame.sample_rate <= 192000 or len(frame.layout.channels) > 2
                        or frame.samples > frame.sample_rate * 2):
                        raise ValueError('voice frame exceeds limits')
                    for converted in resampler.resample(frame):
                        count += converted.samples
                        if count > 300 * 16000:
                            raise ValueError('voice duration exceeds limit')
                        parts.append(converted.to_ndarray().reshape(-1))
                for converted in resampler.resample(None):
                    count += converted.samples
                    if count > 300 * 16000:
                        raise ValueError('voice duration exceeds limit')
                    parts.append(converted.to_ndarray().reshape(-1))
            if count == 0:
                raise ValueError('voice audio is empty')
            samples = np.concatenate(parts).astype(np.float32) / 32768.0
            if np.max(np.abs(samples)) <= 1e-5:
                raise ValueError('voice contains no speech')
            if cancelled.is_set():
                raise ValueError('voice recognition cancelled')
            result = self._transcribe_input(samples, max_chars)
            if cancelled.is_set():
                raise ValueError('voice recognition cancelled')
            return result.model_copy(update={'provider':'faster-whisper', 'model':Path(self._model_size).name,
                'provider_version':importlib.metadata.version('faster-whisper'), 'duration_seconds':count/16000})
        finally:
            self._inference_lock.release()

    async def transcribe_audio(self, audio: bytes, *, max_chars: int) -> TranscriptResult:
        if type(audio) is not bytes or not 0 < len(audio) <= 10*1024*1024 or type(max_chars) is not int or max_chars <= 0:
            raise VoiceTranscriptionError('voice input is invalid')
        cancelled = threading.Event()
        task = asyncio.create_task(asyncio.to_thread(self._audio_sync, audio, max_chars, cancelled))
        failed = False
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled.set()
            # Consume late errors; a bounded in-memory worker owns no temp file.
            task.add_done_callback(lambda done: done.exception() if not done.cancelled() else None)
            raise
        except Exception:
            failed = True
        if failed:
            raise VoiceTranscriptionError('voice recognition failed')
        raise RuntimeError('unreachable')

    def _warmup_sync(self) -> None:
        """Load the model and execute one in-memory encoder inference."""
        failed = False
        try:
            model = self._model_instance()
            samples = np.zeros(16_000, dtype=np.float32)
            features = model.feature_extractor(samples)
            model.encode(features)
        except Exception:
            failed = True
        if failed:
            raise VoiceTranscriptionError("voice model warmup failed") from None

    async def warmup(self) -> None:
        """Prove local model inference before the bot announces readiness."""
        await asyncio.to_thread(self._warmup_sync)
