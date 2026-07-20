"""Unit tests for the voice preview service."""

from __future__ import annotations

import asyncio
import builtins
import hashlib
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ConfigDict, ValidationError

from src.voice import (
    FasterWhisperTranscriber,
    TranscriptResult,
    VoiceCleanupError,
    VoicePreview,
    VoicePreviewService,
    VoiceTranscriptionError,
)
from src.voice.service import VoicePreviewService as VoicePreviewServiceCls


def make_service(
    tmp_voice: Path,
    transcriber: Any,
    max_bytes: int = 1000,
    max_transcript_length: int = 100,
    cancellation_drain_timeout: float = 5.0,
) -> VoicePreviewService:
    """Build a VoicePreviewService with the given transcriber and limits."""
    return VoicePreviewService(
        transcriber=transcriber,
        temp_root=tmp_voice,
        max_bytes=max_bytes,
        max_transcript_length=max_transcript_length,
        cancellation_drain_timeout=cancellation_drain_timeout,
    )


class FakeTranscriber:
    """In-memory transcriber for tests; never touches the filesystem."""

    def __init__(
        self,
        text: str = "hello world",
        language: str | None = "en",
        confidence: float | None = 0.95,
    ) -> None:
        self.text = text
        self.language = language
        self.confidence = confidence
        self.calls: list[Path] = []
        self.limits: list[int] = []

    async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
        self.calls.append(path)
        self.limits.append(max_chars)
        return TranscriptResult(
            text=self.text, language=self.language, confidence=self.confidence
        )


class FailingTranscriber:
    """Transcriber that raises a provider error."""

    async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
        raise RuntimeError("provider failed")


class CancelingTranscriber:
    """Transcriber that raises asyncio.CancelledError."""

    async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
        raise asyncio.CancelledError("canceled")


class RecordingFakeTranscriber:
    """Transcriber that records paths and yields to test concurrency."""

    def __init__(self) -> None:
        self.paths: list[Path] = []

    async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
        self.paths.append(path)
        await asyncio.sleep(0)
        return TranscriptResult(text="hello", language="en", confidence=0.9)


class SlowThreadTranscriber:
    """Transcriber that does work in a worker thread so cancellation races can be tested."""

    def __init__(self, delay: float = 0.2) -> None:
        self.delay = delay
        self.worker_thread: threading.Thread | None = None

    def _sync_work(self, path: Path) -> TranscriptResult:
        self.worker_thread = threading.current_thread()
        assert path.exists()
        time.sleep(self.delay)
        return TranscriptResult(text="ok", language="en", confidence=0.9)

    async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
        return await asyncio.to_thread(self._sync_work, path)


class LateFailingTranscriber:
    """Transcriber that fails after a delay, simulating a late provider error."""

    def __init__(self, delay: float = 0.2) -> None:
        self.delay = delay

    async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
        await asyncio.sleep(self.delay)
        raise RuntimeError("provider failed after cancel window")


class MalformedResultTranscriber:
    """Transcriber that returns an object which is not a valid TranscriptResult."""

    async def transcribe(self, path: Path, *, max_chars: int) -> Any:  # type: ignore[override]
        class BadResult:
            text = 123
            language = None
            confidence = None

        return BadResult()


class DeletingTranscriber:
    """Transcriber that deletes the temp file itself and returns a valid result."""

    async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
        path.unlink()
        return TranscriptResult(text="deleted", language="en", confidence=0.9)


@pytest.fixture
def tmp_voice(tmp_path: Path) -> Path:
    path = tmp_path / "voice"
    path.mkdir()
    return path


@pytest.fixture
def service(tmp_voice: Path) -> VoicePreviewService:
    return make_service(tmp_voice, FakeTranscriber())


@pytest.mark.asyncio
async def test_success_returns_preview_and_deletes_temp(
    service: VoicePreviewService, tmp_voice: Path
) -> None:
    audio = b"fake audio bytes"
    result = await service.preview_from_bytes(audio)
    assert isinstance(result, VoicePreview)
    assert result.transcript == "hello world"
    assert result.language == "en"
    assert result.confidence == 0.95
    assert result.sha256 == hashlib.sha256(audio).hexdigest()
    assert result.size == len(audio)
    assert list(tmp_voice.iterdir()) == []


def test_service_exposes_bytes_only_boundary(service: VoicePreviewService) -> None:
    assert not hasattr(service, "preview_from_stream")


@pytest.mark.asyncio
async def test_service_passes_early_transcript_limit_to_provider(
    tmp_voice: Path,
) -> None:
    transcriber = FakeTranscriber()
    service = make_service(tmp_voice, transcriber, max_transcript_length=17)
    await service.preview_from_bytes(b"audio")
    assert transcriber.limits == [17]


@pytest.mark.asyncio
async def test_provider_exception_deletes_temp(tmp_voice: Path) -> None:
    service = make_service(tmp_voice, FailingTranscriber())
    with pytest.raises(VoiceTranscriptionError, match="transcription failed"):
        await service.preview_from_bytes(b"audio")
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_cancellation_deletes_temp(tmp_voice: Path) -> None:
    service = make_service(tmp_voice, CancelingTranscriber())
    with pytest.raises(asyncio.CancelledError):
        await service.preview_from_bytes(b"audio")
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_oversize_audio_rejected_before_provider(tmp_voice: Path) -> None:
    transcriber = FakeTranscriber()
    service = make_service(tmp_voice, transcriber, max_bytes=10)
    with pytest.raises(ValueError, match="audio exceeds max bytes"):
        await service.preview_from_bytes(b"x" * 11)
    assert transcriber.calls == []
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_empty_audio_rejected(tmp_voice: Path) -> None:
    service = make_service(tmp_voice, FakeTranscriber())
    with pytest.raises(ValueError, match="audio is empty"):
        await service.preview_from_bytes(b"")
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_empty_whitespace_transcript_rejected(tmp_voice: Path) -> None:
    service = make_service(tmp_voice, FakeTranscriber(text="   "))
    with pytest.raises(ValueError, match="transcript is empty"):
        await service.preview_from_bytes(b"audio")
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_oversize_transcript_rejected_after_normalization(
    tmp_voice: Path,
) -> None:
    service = make_service(tmp_voice, FakeTranscriber(text="x " * 100), max_transcript_length=10)
    with pytest.raises(ValueError, match="transcript exceeds max length"):
        await service.preview_from_bytes(b"audio")
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_confidence_out_of_range_rejected(tmp_voice: Path) -> None:
    service = make_service(tmp_voice, FakeTranscriber(confidence=1.5))
    with pytest.raises(VoiceTranscriptionError, match="transcription failed"):
        await service.preview_from_bytes(b"audio")
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_bool_confidence_rejected(tmp_voice: Path) -> None:
    service = make_service(
        tmp_voice, FakeTranscriber(confidence=True)  # type: ignore[arg-type]
    )
    with pytest.raises(VoiceTranscriptionError, match="transcription failed"):
        await service.preview_from_bytes(b"audio")
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_parallel_requests_use_different_temp_paths(tmp_voice: Path) -> None:
    transcriber = RecordingFakeTranscriber()
    service = make_service(tmp_voice, transcriber)
    await asyncio.gather(
        service.preview_from_bytes(b"audio1"),
        service.preview_from_bytes(b"audio2"),
    )
    assert len(transcriber.paths) == 2
    assert transcriber.paths[0] != transcriber.paths[1]
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_raw_audio_not_in_result_or_error(service: VoicePreviewService) -> None:
    audio = b"secret audio content"
    result = await service.preview_from_bytes(audio)
    dumped = result.model_dump_json().encode()
    assert audio not in dumped

    failing_service = make_service(service._temp_root, FailingTranscriber())
    with pytest.raises(VoiceTranscriptionError, match="transcription failed") as exc_info:
        await failing_service.preview_from_bytes(audio)
    assert audio not in str(exc_info.value).encode()


@pytest.mark.asyncio
async def test_temp_path_not_in_safe_errors(tmp_voice: Path) -> None:
    service = make_service(tmp_voice, FakeTranscriber(), max_bytes=5)
    with pytest.raises(ValueError, match="audio exceeds max bytes") as exc_info:
        await service.preview_from_bytes(b"too big")
    assert str(tmp_voice) not in str(exc_info.value)


def test_import_voice_without_faster_whisper() -> None:
    import src.voice as voice

    assert hasattr(voice, "VoicePreviewService")
    assert hasattr(voice, "FasterWhisperTranscriber")
    assert hasattr(voice, "TranscriptResult")
    assert hasattr(voice, "VoicePreview")
    assert hasattr(voice, "VoiceTranscriptionError")
    assert hasattr(voice, "VoiceCleanupError")


@pytest.mark.asyncio
async def test_missing_faster_whisper_safe_error(
    tmp_voice: Path, monkeypatch: Any
) -> None:
    original_import = builtins.__import__

    def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "faster_whisper":
            raise ModuleNotFoundError("No module named 'faster_whisper'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    transcriber = FasterWhisperTranscriber()
    with pytest.raises(VoiceTranscriptionError, match="faster-whisper is not available"):
        await transcriber.transcribe(tmp_voice / "dummy.ogg", max_chars=100)


@pytest.mark.asyncio
async def test_transcriber_not_called_on_validation_failure(tmp_voice: Path) -> None:
    transcriber = FakeTranscriber()
    service = make_service(tmp_voice, transcriber, max_bytes=5)
    with pytest.raises(ValueError, match="audio exceeds max bytes"):
        await service.preview_from_bytes(b"too big")
    assert transcriber.calls == []


@pytest.mark.asyncio
async def test_no_files_left_after_success_or_error(tmp_voice: Path) -> None:
    success_service = make_service(tmp_voice, FakeTranscriber())
    await success_service.preview_from_bytes(b"audio")
    assert list(tmp_voice.iterdir()) == []

    error_service = make_service(tmp_voice, FakeTranscriber(text="   "))
    with pytest.raises(ValueError, match="transcript is empty"):
        await error_service.preview_from_bytes(b"audio")
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_language_normalized_or_none(tmp_voice: Path) -> None:
    service = make_service(tmp_voice, FakeTranscriber(language="  EN  "))
    result = await service.preview_from_bytes(b"audio")
    assert result.language == "en"


@pytest.mark.asyncio
async def test_transcript_normalized(tmp_voice: Path) -> None:
    service = make_service(tmp_voice, FakeTranscriber(text="  hello   world  "))
    result = await service.preview_from_bytes(b"audio")
    assert result.transcript == "hello world"


def test_constructor_rejects_bool_max_bytes(tmp_voice: Path) -> None:
    with pytest.raises(ValueError, match="max_bytes must be a positive integer"):
        make_service(tmp_voice, FakeTranscriber(), max_bytes=True)  # type: ignore[arg-type]


def test_constructor_rejects_non_positive_max_bytes(tmp_voice: Path) -> None:
    with pytest.raises(ValueError, match="max_bytes must be a positive integer"):
        make_service(tmp_voice, FakeTranscriber(), max_bytes=0)


def test_constructor_rejects_bool_max_transcript_length(tmp_voice: Path) -> None:
    with pytest.raises(
        ValueError, match="max_transcript_length must be a positive integer"
    ):
        make_service(
            tmp_voice, FakeTranscriber(), max_transcript_length=True  # type: ignore[arg-type]
        )


def test_constructor_rejects_non_positive_max_transcript_length(tmp_voice: Path) -> None:
    with pytest.raises(
        ValueError, match="max_transcript_length must be a positive integer"
    ):
        make_service(tmp_voice, FakeTranscriber(), max_transcript_length=-1)


def test_voice_preview_service_class_importable() -> None:
    """Ensure the concrete service class is importable from the package."""
    assert VoicePreviewServiceCls is VoicePreviewService


# Regression tests for REWORK-1


class _FakeFasterWhisperModel:
    """Stub faster-whisper model that records which thread performed each step."""

    instances: list[_FakeFasterWhisperModel] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.load_thread = threading.current_thread()
        self.instances.append(self)

    def transcribe(self, path: str) -> tuple[Any, Any]:
        self.transcribe_thread = threading.current_thread()

        def _segments() -> Any:
            self.iterate_thread = threading.current_thread()
            yield type("Segment", (), {"text": "hello"})()
            yield type("Segment", (), {"text": " world"})()

        info = type("Info", (), {"language": "en", "language_probability": 0.9})()
        return _segments(), info

    @classmethod
    def reset(cls) -> None:
        cls.instances.clear()


def _fake_faster_whisper_import(
    original_import: Any, bad_info: bool = False
) -> Any:
    def _import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "faster_whisper":
            if bad_info:
                class BadModel:
                    def __init__(self, *args: Any, **kwargs: Any) -> None:
                        pass

                    def transcribe(self, path: str) -> tuple[Any, Any]:
                        def _segments() -> Any:
                            yield type("Segment", (), {"text": "ok"})()

                        info = type(
                            "Info", (), {"language": 123, "language_probability": None}
                        )()
                        return _segments(), info

                return type("Module", (), {"WhisperModel": BadModel})()
            return type(
                "Module", (), {"WhisperModel": _FakeFasterWhisperModel}
            )()
        return original_import(name, *args, **kwargs)

    return _import


@pytest.mark.asyncio
async def test_model_load_runs_in_worker_thread(
    tmp_voice: Path, monkeypatch: Any
) -> None:
    _FakeFasterWhisperModel.reset()
    original_import = builtins.__import__
    monkeypatch.setattr(
        builtins, "__import__", _fake_faster_whisper_import(original_import)
    )
    transcriber = FasterWhisperTranscriber()
    result = await transcriber.transcribe(tmp_voice / "dummy.ogg", max_chars=100)
    assert result.text == "hello world"
    assert len(_FakeFasterWhisperModel.instances) == 1
    assert _FakeFasterWhisperModel.instances[0].load_thread != threading.main_thread()


@pytest.mark.asyncio
async def test_segment_iteration_runs_in_worker_thread(
    tmp_voice: Path, monkeypatch: Any
) -> None:
    _FakeFasterWhisperModel.reset()
    original_import = builtins.__import__
    monkeypatch.setattr(
        builtins, "__import__", _fake_faster_whisper_import(original_import)
    )
    transcriber = FasterWhisperTranscriber()
    await transcriber.transcribe(tmp_voice / "dummy.ogg", max_chars=100)
    model = _FakeFasterWhisperModel.instances[0]
    assert model.iterate_thread != threading.main_thread()
    assert model.iterate_thread == model.transcribe_thread


@pytest.mark.asyncio
async def test_parallel_first_call_loads_model_once(
    tmp_voice: Path, monkeypatch: Any
) -> None:
    _FakeFasterWhisperModel.reset()
    original_import = builtins.__import__
    monkeypatch.setattr(
        builtins, "__import__", _fake_faster_whisper_import(original_import)
    )
    transcriber = FasterWhisperTranscriber()
    await asyncio.gather(
        transcriber.transcribe(tmp_voice / "a.ogg", max_chars=100),
        transcriber.transcribe(tmp_voice / "b.ogg", max_chars=100),
    )
    assert len(_FakeFasterWhisperModel.instances) == 1


@pytest.mark.asyncio
async def test_provider_exception_does_not_leak_temp_path_or_audio(
    tmp_voice: Path,
) -> None:
    audio = b"secret-audio-marker"

    class LeakyFailingTranscriber:
        async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
            raise RuntimeError(
                f"provider failed on {path} with {audio!r}"
            )

    service = make_service(tmp_voice, LeakyFailingTranscriber())
    with pytest.raises(VoiceTranscriptionError, match="transcription failed") as exc_info:
        await service.preview_from_bytes(audio)
    error_text = str(exc_info.value)
    assert str(tmp_voice) not in error_text
    assert str(audio) not in error_text
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_unlink_failure_after_success_is_not_success(tmp_voice: Path) -> None:
    service = make_service(tmp_voice, FakeTranscriber())
    with patch.object(Path, "unlink", side_effect=OSError("denied")):
        with pytest.raises(
            VoiceCleanupError, match="cleanup failed after successful transcription"
        ):
            await service.preview_from_bytes(b"audio")

    files = list(tmp_voice.iterdir())
    assert len(files) == 1
    files[0].unlink()


@pytest.mark.asyncio
async def test_provider_failure_with_unlink_failure_keeps_safe_info(
    tmp_voice: Path,
) -> None:
    audio = b"secret-audio-marker"

    class LeakyFailingTranscriber:
        async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
            raise RuntimeError(
                f"provider failed on {path} with {audio!r}"
            )

    service = make_service(tmp_voice, LeakyFailingTranscriber())
    with patch.object(Path, "unlink", side_effect=OSError("denied")):
        with pytest.raises(
            VoiceTranscriptionError, match="transcription failed; cleanup also failed"
        ) as exc_info:
            await service.preview_from_bytes(audio)

    error_text = str(exc_info.value)
    assert str(tmp_voice) not in error_text
    assert str(audio) not in error_text

    files = list(tmp_voice.iterdir())
    assert len(files) == 1
    files[0].unlink()


@pytest.mark.asyncio
async def test_controlled_cancellation_waits_for_worker_thread(tmp_voice: Path) -> None:
    transcriber = SlowThreadTranscriber(delay=0.2)
    service = make_service(tmp_voice, transcriber)
    task = asyncio.create_task(service.preview_from_bytes(b"audio"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert transcriber.worker_thread is not None
    assert transcriber.worker_thread != threading.main_thread()
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_non_string_language_rejected(tmp_voice: Path) -> None:
    service = make_service(
        tmp_voice, FakeTranscriber(language=123)  # type: ignore[arg-type]
    )
    with pytest.raises(VoiceTranscriptionError, match="transcription failed"):
        await service.preview_from_bytes(b"audio")
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_malformed_provider_result_rejected_at_service_boundary(
    tmp_voice: Path,
) -> None:
    service = make_service(tmp_voice, MalformedResultTranscriber())
    with pytest.raises(
        VoiceTranscriptionError, match="transcription result is malformed"
    ):
        await service.preview_from_bytes(b"audio")
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_malformed_provider_result_rejected_at_provider_boundary(
    tmp_voice: Path, monkeypatch: Any
) -> None:
    original_import = builtins.__import__
    monkeypatch.setattr(
        builtins, "__import__", _fake_faster_whisper_import(original_import, bad_info=True)
    )
    transcriber = FasterWhisperTranscriber()
    with pytest.raises(VoiceTranscriptionError, match="transcription result is malformed"):
        await transcriber.transcribe(tmp_voice / "dummy.ogg", max_chars=100)


# Regression tests for REWORK-2


@pytest.mark.asyncio
async def test_cancellation_preserved_when_provider_fails_after_cancel(
    tmp_voice: Path,
) -> None:
    service = make_service(tmp_voice, LateFailingTranscriber(delay=0.2))
    task = asyncio.create_task(service.preview_from_bytes(b"audio"))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_partial_temp_write_is_cleaned(tmp_voice: Path, monkeypatch: Any) -> None:
    audio = b"secret-audio-marker"

    class FailingTempFile:
        def __init__(self, dir: str, suffix: str, delete: bool) -> None:
            self.dir = dir

        def __enter__(self) -> "FailingTempFile":
            self.path = Path(self.dir) / "partial.tmp"
            self.path.write_bytes(b"ab")
            self._fh = open(self.path, "wb")
            return self

        def write(self, data: bytes) -> None:
            self._fh.write(data[:2])
            raise OSError("write failed")

        def flush(self) -> None:
            pass

        @property
        def name(self) -> str:
            return str(self.path)

        def __exit__(self, *args: Any) -> Any:
            self._fh.close()
            return False

    monkeypatch.setattr(
        "src.voice.service.tempfile.NamedTemporaryFile", FailingTempFile
    )
    service = make_service(tmp_voice, FakeTranscriber())
    with pytest.raises(
        VoiceTranscriptionError, match="audio preparation failed"
    ) as exc_info:
        await service.preview_from_bytes(audio)

    error_text = str(exc_info.value)
    assert str(tmp_voice) not in error_text
    assert str(audio) not in error_text
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", 123),
        ("language", 123),
        ("confidence", 1.5),
    ],
)
@pytest.mark.asyncio
async def test_mutable_transcript_result_revalidated(
    tmp_voice: Path, field: str, value: Any
) -> None:
    class MutableTranscriber:
        async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
            class MutableResult(TranscriptResult):
                model_config = ConfigDict(validate_assignment=False, frozen=False)

            result = MutableResult(text="hello", language="en", confidence=0.9)
            setattr(result, field, value)
            return result

    service = make_service(tmp_voice, MutableTranscriber())
    with pytest.raises(
        VoiceTranscriptionError, match="transcription result is malformed"
    ):
        await service.preview_from_bytes(b"audio")
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_provider_deletes_temp_file_succeeds(tmp_voice: Path) -> None:
    service = make_service(tmp_voice, DeletingTranscriber())
    result = await service.preview_from_bytes(b"audio")
    assert result.transcript == "deleted"
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_model_dump_exception_does_not_leak(tmp_voice: Path) -> None:
    audio = b"SECRET_AUDIO"

    class ExplodingModelDumpResult:
        def __init__(self, path: Path) -> None:
            self._path = path

        def model_dump(self, **kwargs: Any) -> Any:
            raise RuntimeError(
                f"malformed result at {self._path}; raw={audio.decode()}"
            )

    class ExplodingTranscriber:
        def __init__(self) -> None:
            self.calls: list[Path] = []

        async def transcribe(self, path: Path, *, max_chars: int) -> Any:
            self.calls.append(path)
            return ExplodingModelDumpResult(path)

    transcriber = ExplodingTranscriber()
    service = make_service(tmp_voice, transcriber)
    with pytest.raises(
        VoiceTranscriptionError, match="transcription result is malformed"
    ) as exc_info:
        await service.preview_from_bytes(audio)

    error_text = str(exc_info.value)
    assert str(tmp_voice) not in error_text
    assert str(transcriber.calls[0]) not in error_text
    assert audio.decode() not in error_text
    assert len(transcriber.calls) == 1
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_provider_exception_chain_is_clean(tmp_voice: Path) -> None:
    audio = b"secret-audio-marker"

    class LeakyFailingTranscriber:
        async def transcribe(self, path: Path, *, max_chars: int) -> TranscriptResult:
            raise RuntimeError(
                f"provider failed on {path} with {audio!r}"
            )

    service = make_service(tmp_voice, LeakyFailingTranscriber())
    with pytest.raises(VoiceTranscriptionError, match="transcription failed") as exc_info:
        await service.preview_from_bytes(audio)

    exc = exc_info.value
    assert exc.__cause__ is None
    assert exc.__context__ is None
    assert str(tmp_voice) not in str(exc)
    assert audio.decode() not in str(exc)
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_model_dump_exception_chain_is_clean(tmp_voice: Path) -> None:
    audio = b"SECRET_AUDIO"

    class ExplodingModelDumpResult:
        def __init__(self, path: Path) -> None:
            self._path = path

        def model_dump(self, **kwargs: Any) -> Any:
            raise RuntimeError(
                f"malformed result at {self._path}; raw={audio.decode()}"
            )

    class ExplodingTranscriber:
        async def transcribe(self, path: Path, *, max_chars: int) -> Any:
            return ExplodingModelDumpResult(path)

    service = make_service(tmp_voice, ExplodingTranscriber())
    with pytest.raises(
        VoiceTranscriptionError, match="transcription result is malformed"
    ) as exc_info:
        await service.preview_from_bytes(audio)

    exc = exc_info.value
    assert exc.__cause__ is None
    assert exc.__context__ is None
    assert str(tmp_voice) not in str(exc)
    assert audio.decode() not in str(exc)
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_preparation_failure_chain_is_clean(
    tmp_voice: Path, monkeypatch: Any
) -> None:
    audio = b"secret-audio-marker"

    class BrokenNamedTemporaryFile:
        def __init__(self, dir: str, suffix: str, delete: bool) -> None:
            self.dir = dir

        def __enter__(self) -> "BrokenNamedTemporaryFile":
            self.path = Path(self.dir) / "partial.tmp"
            self.path.write_bytes(b"ab")
            self._fh = open(self.path, "wb")
            return self

        def write(self, data: bytes) -> None:
            self._fh.write(data[:2])
            raise OSError("write failed")

        def flush(self) -> None:
            pass

        @property
        def name(self) -> str:
            return str(self.path)

        def __exit__(self, *args: Any) -> Any:
            self._fh.close()
            return False

    monkeypatch.setattr(
        "src.voice.service.tempfile.NamedTemporaryFile", BrokenNamedTemporaryFile
    )
    service = make_service(tmp_voice, FakeTranscriber())
    with pytest.raises(
        VoiceTranscriptionError, match="audio preparation failed"
    ) as exc_info:
        await service.preview_from_bytes(audio)

    exc = exc_info.value
    assert exc.__cause__ is None
    assert exc.__context__ is None
    assert str(tmp_voice) not in str(exc)
    assert audio.decode() not in str(exc)
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_missing_faster_whisper_chain_is_clean(
    tmp_voice: Path, monkeypatch: Any
) -> None:
    original_import = builtins.__import__

    def mock_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "faster_whisper":
            raise ModuleNotFoundError("No module named 'faster_whisper'")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)
    transcriber = FasterWhisperTranscriber()
    with pytest.raises(
        VoiceTranscriptionError, match="faster-whisper is not available"
    ) as exc_info:
        await transcriber.transcribe(tmp_voice / "dummy.ogg", max_chars=100)

    exc = exc_info.value
    assert exc.__cause__ is None
    assert exc.__context__ is None


@pytest.mark.asyncio
async def test_cancellation_chain_is_clean(tmp_voice: Path) -> None:
    service = make_service(tmp_voice, CancelingTranscriber())
    with pytest.raises(asyncio.CancelledError) as exc_info:
        await service.preview_from_bytes(b"audio")

    exc = exc_info.value
    assert exc.__cause__ is None
    assert exc.__context__ is None
    assert list(tmp_voice.iterdir()) == []


# Regression tests for the independent Telegram/voice integration audit.


@pytest.mark.asyncio
async def test_faster_whisper_stops_segment_iteration_at_limit(tmp_voice: Path) -> None:
    class OversizeModel:
        def __init__(self) -> None:
            self.yielded = 0

        def transcribe(self, path: str) -> tuple[Any, Any]:
            def segments() -> Any:
                for _ in range(1000):
                    self.yielded += 1
                    yield type("Segment", (), {"text": "xxxx"})()

            info = type("Info", (), {"language": "en", "language_probability": 1.0})()
            return segments(), info

    model = OversizeModel()
    transcriber = FasterWhisperTranscriber()
    transcriber._model = model
    with pytest.raises(
        VoiceTranscriptionError, match="transcription result exceeds max length"
    ):
        await transcriber.transcribe(tmp_voice / "dummy.ogg", max_chars=5)
    assert model.yielded == 2


@pytest.mark.asyncio
async def test_repeated_cancellation_never_unlinks_active_provider_file(
    tmp_voice: Path,
) -> None:
    service = make_service(tmp_voice, SlowThreadTranscriber(delay=0.2))
    task = asyncio.create_task(service.preview_from_bytes(b"audio"))
    await asyncio.sleep(0.03)
    task.cancel()
    await asyncio.sleep(0.03)
    assert list(tmp_voice.iterdir())
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert list(tmp_voice.iterdir()) == []


@pytest.mark.asyncio
async def test_cancellation_drain_is_bounded_and_cleanup_is_deferred(
    tmp_voice: Path,
) -> None:
    service = make_service(
        tmp_voice,
        SlowThreadTranscriber(delay=0.2),
        cancellation_drain_timeout=0.03,
    )
    task = asyncio.create_task(service.preview_from_bytes(b"audio"))
    await asyncio.sleep(0.02)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert list(tmp_voice.iterdir())
    await asyncio.sleep(0.25)
    assert list(tmp_voice.iterdir()) == []


def test_voice_models_forbid_extra_and_are_frozen() -> None:
    result = TranscriptResult(text="hello", language="en", confidence=0.9)
    with pytest.raises(ValidationError):
        TranscriptResult(text="hello", unexpected="no")  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        result.text = "changed"  # type: ignore[misc]

    preview = VoicePreview(
        transcript="hello",
        language="en",
        confidence=0.9,
        sha256="a" * 64,
        size=1,
    )
    with pytest.raises(ValidationError):
        preview.size = 2  # type: ignore[misc]


@pytest.mark.parametrize("value", [True, 0, -1, "1"])
def test_constructor_rejects_invalid_cancellation_timeout(
    tmp_voice: Path, value: Any
) -> None:
    with pytest.raises(ValueError, match="cancellation_drain_timeout must be positive"):
        make_service(
            tmp_voice,
            FakeTranscriber(),
            cancellation_drain_timeout=value,  # type: ignore[arg-type]
        )
