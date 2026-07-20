"""Voice preview service."""

from __future__ import annotations

import asyncio
import hashlib
import tempfile
from pathlib import Path

from .base import (
    TranscriptResult,
    VoiceCleanupError,
    VoicePreview,
    VoiceTranscriber,
    VoiceTranscriptionError,
)


class VoicePreviewService:
    """Prepare a safe preview of a voice transcription.

    The service does not download files, create TaskContracts, or start workers.
    It accepts already-authorized, size-limited audio bytes, writes a temporary
    file inside an injected temp root, calls a ``VoiceTranscriber``, and returns
    a ``VoicePreview``. Any temporary file that has been created is removed on
    success, provider failure, or cancellation. Cleanup failures are surfaced
    as safe errors without leaking temp paths or provider exceptions.
    """

    def __init__(
        self,
        transcriber: VoiceTranscriber,
        temp_root: Path,
        max_bytes: int,
        max_transcript_length: int,
        cancellation_drain_timeout: float = 5.0,
    ) -> None:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes <= 0:
            raise ValueError("max_bytes must be a positive integer")
        if (
            isinstance(max_transcript_length, bool)
            or not isinstance(max_transcript_length, int)
            or max_transcript_length <= 0
        ):
            raise ValueError("max_transcript_length must be a positive integer")
        if (
            isinstance(cancellation_drain_timeout, bool)
            or not isinstance(cancellation_drain_timeout, (int, float))
            or cancellation_drain_timeout <= 0
        ):
            raise ValueError("cancellation_drain_timeout must be positive")
        self._transcriber = transcriber
        self._temp_root = Path(temp_root)
        self._max_bytes = max_bytes
        self._max_transcript_length = max_transcript_length
        self._cancellation_drain_timeout = float(cancellation_drain_timeout)
        self._cleanup_tasks: set[asyncio.Task[None]] = set()

    async def preview_from_bytes(self, audio: bytes) -> VoicePreview:
        """Create a preview from audio bytes."""
        if not isinstance(audio, bytes):
            raise TypeError("audio must be bytes")
        if len(audio) == 0:
            raise ValueError("audio is empty")
        if len(audio) > self._max_bytes:
            raise ValueError("audio exceeds max bytes")
        return await self._process(audio)

    def _prepare_temp_file(self, audio: bytes) -> Path:
        """Atomically create a temp file inside ``temp_root`` and write ``audio``.

        Any OSError during directory creation, file creation, write, flush or
        close is converted into a safe error. If the file was created, it is
        removed on failure. Safe errors are raised outside the active ``except``
        block so that no original exception remains in ``__context__`` or
        ``__cause__``.
        """
        temp_path: Path | None = None
        safe_exc: VoiceTranscriptionError | VoiceCleanupError | None = None
        try:
            self._temp_root.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                dir=self._temp_root, suffix=".tmp", delete=False
            ) as temp_file:
                temp_path = Path(temp_file.name)
                temp_file.write(audio)
                temp_file.flush()
            return temp_path
        except OSError:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    safe_exc = VoiceCleanupError(
                        "audio preparation failed; cleanup also failed"
                    )
            if safe_exc is None:
                safe_exc = VoiceTranscriptionError("audio preparation failed")

        if safe_exc is not None:
            raise safe_exc
        raise RuntimeError("unreachable")  # pragma: no cover

    async def _process(self, audio: bytes) -> VoicePreview:
        sha256_hash = hashlib.sha256(audio).hexdigest()
        size = len(audio)
        temp_path = self._prepare_temp_file(audio)

        cancelled = False
        cancelled_cleanup_failed = False
        safe_exc: VoiceTranscriptionError | VoiceCleanupError | None = None
        transcript_result: TranscriptResult | None = None

        transcription_task = asyncio.create_task(
            self._transcriber.transcribe(
                temp_path, max_chars=self._max_transcript_length
            )
        )
        try:
            transcript_result = await asyncio.shield(transcription_task)
        except asyncio.CancelledError:
            cancelled = True
            drained = await self._drain_cancelled(transcription_task)
            if drained:
                cancelled_cleanup_failed = self._unlink_failed(temp_path)
            else:
                self._defer_cleanup(transcription_task, temp_path)
        except Exception:
            if self._unlink_failed(temp_path):
                safe_exc = VoiceTranscriptionError(
                    "transcription failed; cleanup also failed"
                )
            else:
                safe_exc = VoiceTranscriptionError("transcription failed")

        if cancelled:
            if cancelled_cleanup_failed:
                raise asyncio.CancelledError("cancelled; cleanup failed")
            raise asyncio.CancelledError()
        if safe_exc is not None:
            raise safe_exc
        assert transcript_result is not None

        try:
            data = transcript_result.model_dump(warnings=False)
            validated_result = TranscriptResult.model_validate(data)
        except Exception:
            if self._unlink_failed(temp_path):
                safe_exc = VoiceTranscriptionError(
                    "transcription result is malformed; cleanup also failed"
                )
            else:
                safe_exc = VoiceTranscriptionError("transcription result is malformed")
        if safe_exc is not None:
            raise safe_exc

        transcript_exc: Exception | None = None
        try:
            transcript = self._normalize_transcript(validated_result.text)
            if len(transcript) == 0:
                raise ValueError("transcript is empty")
            if len(transcript) > self._max_transcript_length:
                raise ValueError("transcript exceeds max length")
            preview = VoicePreview(
                transcript=transcript,
                language=validated_result.language,
                confidence=validated_result.confidence,
                sha256=sha256_hash,
                size=size,
            )
        except Exception as exc:
            if self._unlink_failed(temp_path):
                safe_exc = VoiceCleanupError("cleanup failed after transcription")
            else:
                transcript_exc = exc
        if safe_exc is not None:
            raise safe_exc
        if transcript_exc is not None:
            raise transcript_exc

        if self._unlink_failed(temp_path):
            raise VoiceCleanupError("cleanup failed after successful transcription")
        return preview

    async def _drain_cancelled(self, task: asyncio.Task[TranscriptResult]) -> bool:
        """Wait a bounded time for provider work despite repeated cancellation."""
        deadline = asyncio.get_running_loop().time() + self._cancellation_drain_timeout
        while not task.done():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                return False
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=remaining)
            except asyncio.CancelledError:
                continue
            except TimeoutError:
                return False
            except Exception:
                break
        if task.done() and not task.cancelled():
            try:
                task.result()
            except Exception:
                pass
        return task.done()

    def _defer_cleanup(
        self, task: asyncio.Task[TranscriptResult], temp_path: Path
    ) -> None:
        """Keep the temp file until non-cancellable provider work actually stops."""

        async def finalize() -> None:
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                # A cancelled finalizer cannot prove that underlying sync work
                # stopped, so fail closed and leave the file in the private root.
                return
            except Exception:
                pass
            self._unlink_failed(temp_path)

        cleanup_task = asyncio.create_task(finalize())
        self._cleanup_tasks.add(cleanup_task)
        cleanup_task.add_done_callback(self._cleanup_tasks.discard)

    def _normalize_transcript(self, text: str) -> str:
        """Collapse whitespace and strip edges."""
        return " ".join(text.split())

    def _unlink_failed(self, temp_path: Path) -> bool:
        """Try to remove ``temp_path``; return ``True`` if removal failed."""
        try:
            temp_path.unlink(missing_ok=True)
            return False
        except OSError:
            return True
