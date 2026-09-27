import ctypes
import types

import numpy as np

from whisper_dictate import transcriber
from whisper_dictate.transcriber import Transcriber


class Segment:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, texts=()):
        self.texts = texts
        self.calls = []

    def transcribe(self, audio, **options):
        self.calls.append((audio, options))
        return (Segment(text) for text in self.texts), object()


def test_transcribe_joins_and_trims_segments():
    model = FakeModel([" Hello there.", "  How are you? "])
    assert Transcriber(model).transcribe("a.wav") == "Hello there. How are you?"


def test_transcribe_uses_the_language_and_filters_silence():
    model = FakeModel(["x"])
    Transcriber(model, language="de").transcribe("a.wav")
    audio, options = model.calls[0]
    assert audio == "a.wav"
    assert options["language"] == "de"
    assert options["vad_filter"] is True


def test_transcribe_returns_empty_text_for_no_speech():
    assert Transcriber(FakeModel([])).transcribe("a.wav") == ""


def test_warm_up_runs_one_second_of_audio_through_the_model():
    model = FakeModel([" Thank you."])
    Transcriber(model).warm_up()
    audio, options = model.calls[0]
    assert isinstance(audio, np.ndarray)
    assert audio.dtype == np.float32
    assert audio.shape == (16000,)
    assert options["vad_filter"] is False


def test_preload_pip_cublas_does_nothing_when_not_installed(monkeypatch):
    def missing(name):
        raise ImportError(name)
    monkeypatch.setattr(transcriber.importlib, "import_module", missing)
    assert transcriber.preload_pip_cublas(load=lambda *a, **k: None) is None


def test_preload_pip_cublas_loads_lt_first_and_globally(monkeypatch, tmp_path):
    package = types.SimpleNamespace(__path__=[str(tmp_path)])
    monkeypatch.setattr(transcriber.importlib, "import_module", lambda name: package)
    loaded = []
    result = transcriber.preload_pip_cublas(
        load=lambda path, mode: loaded.append((path, mode)))
    assert result == str(tmp_path / "lib")
    assert [path.rsplit("/", 1)[1] for path, _ in loaded] == [
        "libcublasLt.so.12", "libcublas.so.12"]
    assert all(mode == ctypes.RTLD_GLOBAL for _, mode in loaded)


def test_loaded_cublas_lists_unique_libraries(tmp_path):
    maps = tmp_path / "maps"
    maps.write_text(
        "7f00 r-xp 0 0:0 1 /opt/nv/libcublas.so.12\n"
        "7f01 r--p 0 0:0 1 /opt/nv/libcublas.so.12\n"
        "7f02 r-xp 0 0:0 1 /opt/nv/libcublasLt.so.12\n"
        "7f03 r-xp 0 0:0 1 /usr/lib/libc.so.6\n"
    )
    assert transcriber.loaded_cublas(maps) == [
        "/opt/nv/libcublas.so.12", "/opt/nv/libcublasLt.so.12"]


def test_loaded_cublas_is_empty_without_proc(tmp_path):
    assert transcriber.loaded_cublas(tmp_path / "missing") == []
