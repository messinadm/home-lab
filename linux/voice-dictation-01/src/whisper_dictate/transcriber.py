"""Speech to text with faster-whisper, fully offline."""

from __future__ import annotations

import ctypes
import importlib
import os
from pathlib import Path
from typing import Any, Protocol

from .config import Settings

CUBLAS_LIBS = ("libcublasLt.so.12", "libcublas.so.12")


class Model(Protocol):
    def transcribe(self, audio: Any, **options: Any) -> tuple[Any, Any]: ...


def preload_pip_cublas(load: Any = ctypes.CDLL) -> str | None:
    """Load cuBLAS from the nvidia-cublas-cu12 package if it is installed.

    CTranslate2 opens libcublas.so.12 by name, so loading the package's copy
    first makes it win over an older system copy. Returns the library
    directory, or None if the package isn't installed.
    """
    try:
        package = importlib.import_module("nvidia.cublas")
    except ImportError:
        return None
    libdir = Path(list(package.__path__)[0]) / "lib"
    for name in CUBLAS_LIBS:
        load(str(libdir / name), mode=ctypes.RTLD_GLOBAL)
    return str(libdir)


def loaded_cublas(maps: Path = Path("/proc/self/maps")) -> list[str]:
    """cuBLAS libraries this process has loaded."""
    try:
        lines = maps.read_text().splitlines()
    except OSError:
        return []
    return sorted({line.split()[-1] for line in lines if "libcublas" in line})


def load_model(settings: Settings) -> Model:  # pragma: no cover - needs the GPU
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from faster_whisper import WhisperModel

    return WhisperModel(
        settings.model,
        device=settings.device,
        compute_type=settings.compute_type,
        download_root=str(settings.models_dir),
        local_files_only=True,
    )


def fetch_model(settings: Settings) -> str:  # pragma: no cover - network
    """Download the model once. The only step that uses the network."""
    from faster_whisper import download_model

    return download_model(settings.model, cache_dir=str(settings.models_dir))


class Transcriber:
    def __init__(self, model: Model, language: str = "en") -> None:
        self._model = model
        self._language = language

    def transcribe(self, audio: Any) -> str:
        # The VAD filter drops silence, which Whisper otherwise tends to
        # "transcribe" as stock phrases like "Thank you."
        segments, _info = self._model.transcribe(
            audio, language=self._language, vad_filter=True, beam_size=5
        )
        return " ".join(segment.text.strip() for segment in segments).strip()

    def warm_up(self) -> None:
        """Run the model once so the first dictation doesn't pay for GPU setup."""
        import numpy as np

        noise = (np.random.default_rng(0).standard_normal(16000) * 0.01).astype(np.float32)
        segments, _info = self._model.transcribe(
            noise, language=self._language, vad_filter=False, beam_size=1
        )
        for _segment in segments:
            pass
