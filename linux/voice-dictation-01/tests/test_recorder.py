import io
import signal
import subprocess
from pathlib import Path

import pytest

from whisper_dictate import recorder
from whisper_dictate.recorder import Recorder, RecorderError


class FakeProcess:
    def __init__(self, path, write=b"R" * 100, exits_at_once=False, returncode=0,
                 stderr=b"", hangs=False):
        self.path = Path(path)
        self.write = write
        self.exited = exits_at_once
        self.returncode = returncode
        self.stderr = io.BytesIO(stderr) if stderr is not None else None
        self.hangs = hangs
        self.signals = []
        self.killed = False

    def poll(self):
        return self.returncode if self.exited else None

    def send_signal(self, sig):
        self.signals.append(sig)

    def wait(self, timeout=None):
        if self.hangs and not self.killed:
            raise subprocess.TimeoutExpired("pw-record", timeout)
        if self.write is not None:
            self.path.write_bytes(self.write)
        return self.returncode

    def kill(self):
        self.killed = True


def make(tmp_path, source="bluez_input.mic", **process_options):
    wav = tmp_path / "rec.wav"
    calls = []

    def popen(argv, **kwargs):
        calls.append(argv)
        popen.process = FakeProcess(wav, **process_options)
        return popen.process

    return Recorder(wav, popen=popen, source_lookup=lambda: source), popen, calls, wav


def test_start_runs_pw_record_at_16khz_mono(tmp_path):
    rec, _popen, calls, wav = make(tmp_path)
    rec.start()
    assert calls == [[recorder.PW_RECORD, "--rate", "16000", "--channels", "1",
                      "--format", "s16", str(wav)]]
    assert rec.recording


def test_start_twice_records_once(tmp_path):
    rec, _popen, calls, _wav = make(tmp_path)
    rec.start()
    rec.start()
    assert len(calls) == 1


@pytest.mark.parametrize(("source", "shown"), [
    ("alsa_output.pci.iec958-stereo.monitor", "iec958-stereo.monitor"),
    ("", "unknown"),
])
def test_start_refuses_anything_but_a_microphone(tmp_path, source, shown):
    rec, _popen, calls, _wav = make(tmp_path, source=source)
    with pytest.raises(RecorderError, match=shown):
        rec.start()
    assert calls == []
    assert not rec.recording


def test_start_clears_a_stale_recording(tmp_path):
    rec, _popen, _calls, wav = make(tmp_path)
    wav.write_bytes(b"old")
    rec.start()
    assert not wav.exists()


def test_start_reports_pw_record_dying_at_once(tmp_path):
    rec, _popen, _calls, _wav = make(tmp_path, exits_at_once=True, returncode=1,
                                    stderr=b"no PipeWire\n")
    with pytest.raises(RecorderError, match="no PipeWire"):
        rec.start()
    assert not rec.recording


def test_start_reports_exit_code_when_there_is_no_stderr(tmp_path):
    rec, _popen, _calls, _wav = make(tmp_path, exits_at_once=True, returncode=3, stderr=None)
    with pytest.raises(RecorderError, match="3"):
        rec.start()


def test_stop_sends_sigint_so_the_wav_is_finalized(tmp_path):
    rec, popen, _calls, wav = make(tmp_path)
    rec.start()
    assert rec.stop() == wav
    assert popen.process.signals == [signal.SIGINT]
    assert not rec.recording


def test_stop_when_idle_is_an_error(tmp_path):
    rec, _popen, _calls, _wav = make(tmp_path)
    with pytest.raises(RecorderError, match="not recording"):
        rec.stop()


def test_stop_kills_a_recorder_that_ignores_sigint(tmp_path):
    rec, popen, _calls, _wav = make(tmp_path, hangs=True)
    rec.start()
    with pytest.raises(RecorderError, match="did not stop"):
        rec.stop(timeout=0.01)
    assert popen.process.killed
    assert not rec.recording


@pytest.mark.parametrize("write", [None, b"H" * recorder.WAV_HEADER_BYTES])
def test_stop_rejects_an_empty_recording(tmp_path, write):
    rec, _popen, _calls, _wav = make(tmp_path, write=write)
    rec.start()
    with pytest.raises(RecorderError, match="nothing was recorded"):
        rec.stop()


def fake_run(stdout="", returncode=0, error=None):
    def run(argv, **kwargs):
        if error is not None:
            raise error
        return subprocess.CompletedProcess(argv, returncode, stdout=stdout)
    return run


def test_default_source_reads_pactl():
    assert recorder.default_source(fake_run("bluez_input.X\n")) == "bluez_input.X"


def test_default_source_is_empty_when_pactl_fails():
    assert recorder.default_source(fake_run("junk", returncode=1)) == ""


@pytest.mark.parametrize("error", [FileNotFoundError(), subprocess.TimeoutExpired("pactl", 5)])
def test_default_source_is_empty_when_pactl_cannot_run(error):
    assert recorder.default_source(fake_run(error=error)) == ""


@pytest.mark.parametrize(("source", "expected"), [
    ("bluez_input.00:11:22:33:44:55", True),
    ("alsa_input.pci-0000_71_00.6.analog-stereo", True),
    ("alsa_output.pci-0000_71_00.6.iec958-stereo.monitor", False),
    ("", False),
])
def test_is_microphone(source, expected):
    assert recorder.is_microphone(source) is expected
