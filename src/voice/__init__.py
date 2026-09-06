"""Voice transcription subsystem for Nobus Space."""

from .base import (
    TranscriptResult,
    VoiceCleanupError,
    VoicePreview,
    VoiceTranscriber,
    VoiceTranscriptionError,
)
from .confirmation import (
    ConfirmedVoicePreview,
    InMemoryVoiceConfirmationStore,
    VoiceConfirmationChallenge,
    VoiceConfirmationResult,
    VoiceConfirmationStatus,
)
from .faster_whisper import FasterWhisperTranscriber
from .isolated import IsolatedFasterWhisperTranscriber
from .service import VoicePreviewService

__all__ = [
    "ConfirmedVoicePreview",
    "FasterWhisperTranscriber",
    "IsolatedFasterWhisperTranscriber",
    "InMemoryVoiceConfirmationStore",
    "TranscriptResult",
    "VoiceCleanupError",
    "VoiceConfirmationChallenge",
    "VoiceConfirmationResult",
    "VoiceConfirmationStatus",
    "VoicePreview",
    "VoicePreviewService",
    "VoiceTranscriber",
    "VoiceTranscriptionError",
]
