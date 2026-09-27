"""Settings, read from the environment with defaults for a desktop session."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MODEL = "distil-large-v3"
# The snapshot of Systran/faster-distil-whisper-large-v3 this was tested with.
DEFAULT_MODEL_REVISION = "c3058b475261292e64a0412df1d2681c06260fab"


@dataclass(frozen=True)
class Settings:
    runtime_dir: Path
    models_dir: Path
    model: str = DEFAULT_MODEL
    model_revision: str | None = DEFAULT_MODEL_REVISION
    device: str = "cuda"
    compute_type: str = "float16"
    language: str = "en"

    @property
    def socket_path(self) -> Path:
        return self.runtime_dir / "whisper-dictate.sock"

    @property
    def lock_path(self) -> Path:
        return self.runtime_dir / "whisper-dictate.lock"

    @property
    def recording_path(self) -> Path:
        return self.runtime_dir / "whisper-dictate.wav"

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if env is None else env
        runtime = env.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
        home = env.get("HOME") or str(Path.home())
        data = env.get("XDG_DATA_HOME") or os.path.join(home, ".local", "share")
        models = env.get("WHISPER_DICTATE_MODELS_DIR") or os.path.join(
            data, "whisper-dictate", "models"
        )
        model = env.get("WHISPER_DICTATE_MODEL", DEFAULT_MODEL)
        # Only the default model has a tested revision to pin.
        revision = env.get("WHISPER_DICTATE_MODEL_REVISION") or (
            DEFAULT_MODEL_REVISION if model == DEFAULT_MODEL else None
        )
        return cls(
            runtime_dir=Path(runtime),
            models_dir=Path(models),
            model=model,
            model_revision=revision,
            device=env.get("WHISPER_DICTATE_DEVICE", cls.device),
            compute_type=env.get("WHISPER_DICTATE_COMPUTE_TYPE", cls.compute_type),
            language=env.get("WHISPER_DICTATE_LANGUAGE", cls.language),
        )
