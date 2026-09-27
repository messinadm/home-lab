"""The background service: keeps the model loaded, records between start and stop."""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from . import protocol
from .recorder import Recorder, RecorderError
from .transcriber import Transcriber

log = logging.getLogger(__name__)


class Service:
    def __init__(
        self,
        recorder: Recorder,
        transcriber: Transcriber,
        info: dict[str, Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.recorder = recorder
        self.transcriber = transcriber
        self.info = dict(info or {})
        self._clock = clock
        self._started_at: float | None = None

    def close(self) -> None:
        """Stop any recording in progress and delete its audio."""
        if self.recorder.recording:
            try:
                self.recorder.stop()
            except RecorderError:
                pass
        self.recorder.discard()

    def handle(self, request: dict[str, Any]) -> dict[str, Any]:
        command = request.get("command")
        if command == "start":
            return self._start()
        if command == "stop":
            return self._stop()
        if command == "status":
            state = "recording" if self.recorder.recording else "idle"
            return {"ok": True, "state": state, **self.info}
        return {"ok": False, "error": f"unknown command: {command!r}"}

    def _start(self) -> dict[str, Any]:
        if self.recorder.recording:
            return {"ok": True, "already": True}
        try:
            self.recorder.start()
        except RecorderError as error:
            return {"ok": False, "error": str(error)}
        self._started_at = self._clock()
        log.info("recording")
        return {"ok": True}

    def _stop(self) -> dict[str, Any]:
        try:
            path = self.recorder.stop()
        except RecorderError as error:
            return {"ok": False, "error": str(error)}
        started = self._started_at if self._started_at is not None else self._clock()
        audio_seconds = self._clock() - started
        begun = self._clock()
        try:
            text = self.transcriber.transcribe(str(path))
        except Exception as error:  # an engine failure must not kill the service
            log.exception("transcription failed")
            return {"ok": False, "error": f"transcription failed: {error}"}
        finally:
            path.unlink(missing_ok=True)
        seconds = self._clock() - begun
        # Durations and lengths only: the text itself is never logged.
        log.info("transcribed %.1fs of audio in %.2fs: %d chars",
                 audio_seconds, seconds, len(text))
        return {"ok": True, "text": text,
                "audio_seconds": round(audio_seconds, 1),
                "transcribe_seconds": round(seconds, 2)}


def handle_connection(service: Service, conn: socket.socket) -> None:
    conn.settimeout(5)
    try:
        with conn.makefile("rb") as reader:
            request = protocol.read_message(reader)
        reply = service.handle(request)
    except (ValueError, OSError) as error:
        reply = {"ok": False, "error": f"bad request: {error}"}
    try:
        conn.sendall(protocol.encode(reply))
    except OSError:
        pass


def bind(path: Path) -> socket.socket:
    """Listen on a Unix socket only this user can connect to."""
    path.unlink(missing_ok=True)
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    old_umask = os.umask(0o177)
    try:
        server.bind(str(path))
    finally:
        os.umask(old_umask)
    server.listen(4)
    return server


def sd_notify(message: str, env: Mapping[str, str] | None = None) -> bool:
    """Send a status message to systemd, as Type=notify services do.

    Returns False when not run by systemd or when the socket can't be reached.
    """
    env = os.environ if env is None else env
    address = env.get("NOTIFY_SOCKET", "")
    if not address:
        return False
    if address.startswith("@"):
        address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as conn:
            conn.connect(address)
            conn.sendall(message.encode())
    except OSError:
        return False
    return True


def serve(service: Service, path: Path, stop: threading.Event,
          on_ready: Callable[[], object] | None = None) -> None:
    """Handle one connection at a time until `stop` is set."""
    server = bind(path)
    server.settimeout(1.0)
    if on_ready is not None:
        on_ready()
    try:
        while not stop.is_set():
            try:
                conn, _address = server.accept()
            except TimeoutError:
                continue
            with conn:
                handle_connection(service, conn)
    finally:
        server.close()
        path.unlink(missing_ok=True)
