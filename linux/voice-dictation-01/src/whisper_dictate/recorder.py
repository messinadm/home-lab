"""Record the default microphone with PipeWire's pw-record."""

from __future__ import annotations

import signal
import subprocess
from collections.abc import Callable
from pathlib import Path

PW_RECORD = "/usr/bin/pw-record"
PACTL = "/usr/bin/pactl"
WAV_HEADER_BYTES = 44


class RecorderError(Exception):
    pass


def default_source(run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> str:
    """Name of the default input, or "" if it can't be read."""
    try:
        result = run(
            [PACTL, "get-default-source"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def is_microphone(source: str) -> bool:
    """A ".monitor" source records speaker output, which is what PipeWire
    falls back to when the only microphone (say, a headset) is switched off."""
    return bool(source) and not source.endswith(".monitor")


class Recorder:
    def __init__(
        self,
        path: Path,
        popen: Callable[..., subprocess.Popen] = subprocess.Popen,
        source_lookup: Callable[[], str] = default_source,
    ) -> None:
        self.path = path
        self._popen = popen
        self._source_lookup = source_lookup
        self._process: subprocess.Popen | None = None

    @property
    def recording(self) -> bool:
        return self._process is not None

    def start(self) -> None:
        if self._process is not None:
            return
        source = self._source_lookup()
        if not is_microphone(source):
            raise RecorderError(
                f"input is {source or 'unknown'}, not a microphone. Is your headset on?"
            )
        self.path.unlink(missing_ok=True)
        process = self._popen(
            [PW_RECORD, "--rate", "16000", "--channels", "1", "--format", "s16",
             str(self.path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        if process.poll() is not None:
            detail = process.stderr.read().decode(errors="replace").strip() if process.stderr else ""
            raise RecorderError(f"pw-record exited at once: {detail or process.returncode}")
        self._process = process

    def stop(self, timeout: float = 5.0) -> Path:
        process, self._process = self._process, None
        if process is None:
            raise RecorderError("not recording")
        process.send_signal(signal.SIGINT)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise RecorderError("pw-record did not stop") from None
        if not self.path.exists() or self.path.stat().st_size <= WAV_HEADER_BYTES:
            raise RecorderError("nothing was recorded")
        return self.path
