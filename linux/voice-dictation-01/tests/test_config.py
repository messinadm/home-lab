import os
from pathlib import Path

from whisper_dictate.config import Settings


def test_defaults_for_a_desktop_session():
    settings = Settings.from_env({"XDG_RUNTIME_DIR": "/run/user/42", "HOME": "/home/u"})
    assert settings.runtime_dir == Path("/run/user/42")
    assert settings.models_dir == Path("/home/u/.local/share/whisper-dictate/models")
    assert settings.model == "distil-large-v3"
    assert settings.device == "cuda"
    assert settings.compute_type == "float16"
    assert settings.language == "en"


def test_runtime_paths_live_in_the_runtime_dir():
    settings = Settings.from_env({"XDG_RUNTIME_DIR": "/run/user/42", "HOME": "/h"})
    assert settings.socket_path == Path("/run/user/42/whisper-dictate.sock")
    assert settings.lock_path == Path("/run/user/42/whisper-dictate.lock")
    assert settings.recording_path == Path("/run/user/42/whisper-dictate.wav")


def test_xdg_data_home_moves_the_models():
    settings = Settings.from_env({"XDG_RUNTIME_DIR": "/r", "XDG_DATA_HOME": "/data"})
    assert settings.models_dir == Path("/data/whisper-dictate/models")


def test_every_setting_can_be_overridden():
    settings = Settings.from_env({
        "XDG_RUNTIME_DIR": "/r",
        "HOME": "/h",
        "WHISPER_DICTATE_MODELS_DIR": "/models",
        "WHISPER_DICTATE_MODEL": "small.en",
        "WHISPER_DICTATE_DEVICE": "cpu",
        "WHISPER_DICTATE_COMPUTE_TYPE": "int8",
        "WHISPER_DICTATE_LANGUAGE": "de",
    })
    assert settings.models_dir == Path("/models")
    assert (settings.model, settings.device, settings.compute_type, settings.language) == (
        "small.en", "cpu", "int8", "de"
    )


def test_missing_runtime_dir_falls_back_to_the_uid(monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: 1234)
    assert Settings.from_env({"HOME": "/h"}).runtime_dir == Path("/run/user/1234")


def test_reads_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("WHISPER_DICTATE_MODEL", "tiny.en")
    assert Settings.from_env().model == "tiny.en"
