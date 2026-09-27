"""Runs the real model on the real GPU. Skipped unless WHISPER_DICTATE_GPU_TEST=1."""

import os

import numpy as np
import pytest

from whisper_dictate import transcriber
from whisper_dictate.config import Settings

pytestmark = [
    pytest.mark.gpu,
    pytest.mark.skipif(os.environ.get("WHISPER_DICTATE_GPU_TEST") != "1",
                       reason="set WHISPER_DICTATE_GPU_TEST=1 to use the real GPU"),
]


def test_real_model_loads_offline_and_ignores_silence():
    transcriber.preload_pip_cublas()
    settings = Settings.from_env()
    engine = transcriber.Transcriber(transcriber.load_model(settings), settings.language)
    engine.warm_up()
    assert engine.transcribe(np.zeros(16000 * 2, dtype=np.float32)) == ""
    assert transcriber.loaded_cublas()
