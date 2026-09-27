"""whisper-dictate: start | stop | check | serve | fetch-model."""

from __future__ import annotations

import argparse
import fcntl
import logging
import os
import signal
import subprocess
import sys
import threading
from collections.abc import Callable, Iterator, MutableMapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TextIO

from . import client, notify, recorder, text, transcriber
from .config import Settings

WTYPE = "/usr/bin/wtype"
WL_COPY = "/usr/bin/wl-copy"
TOOLS = (recorder.PW_RECORD, recorder.PACTL, WTYPE, WL_COPY, notify.GDBUS)
SERVICE_HINT = "Start it with: systemctl --user start whisper-dictate"


def restore_session_env(env: MutableMapping[str, str]) -> MutableMapping[str, str]:
    """Fill in what a desktop shortcut may not pass: without WAYLAND_DISPLAY,
    wtype fails silently; without the bus address, alerts go nowhere."""
    runtime = env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime}/bus")
    if not env.get("WAYLAND_DISPLAY"):
        for candidate in sorted(Path(runtime).glob("wayland-[0-9]*")):
            if candidate.is_socket():
                env["WAYLAND_DISPLAY"] = candidate.name
                break
    return env


def _run_with_input(argv: list[str], data: str,
                    run: Callable[..., subprocess.CompletedProcess]) -> bool:
    try:
        result = run(argv, input=data.encode("utf-8"), capture_output=True,
                     timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def type_text(data: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> bool:
    return _run_with_input([WTYPE, "-"], data, run)


def copy_text(data: str, run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> bool:
    return _run_with_input([WL_COPY], data, run)


@contextmanager
def try_lock(path: Path) -> Iterator[bool]:
    """Yield True if we got the lock. The shortcut has been seen firing twice."""
    fd = os.open(path, os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        yield True
    finally:
        os.close(fd)


class App:
    def __init__(
        self,
        settings: Settings,
        request: Callable[..., dict[str, Any]] = client.request,
        alert: Callable[[str, str], bool] = notify.notify,
        type_text: Callable[[str], bool] = type_text,
        copy_text: Callable[[str], bool] = copy_text,
        source_lookup: Callable[[], str] = recorder.default_source,
        is_executable: Callable[[str], bool] = lambda p: os.access(p, os.X_OK),
        env: MutableMapping[str, str] | None = None,
        out: TextIO = sys.stdout,
    ) -> None:
        self.settings = settings
        self.request = request
        self.alert = alert
        self.type_text = type_text
        self.copy_text = copy_text
        self.source_lookup = source_lookup
        self.is_executable = is_executable
        self.env = os.environ if env is None else env
        self.out = out

    def start(self) -> int:
        try:
            reply = self.request(self.settings.socket_path, "start", timeout=10)
        except client.ServiceError as error:
            self.alert("Dictation service is not running", f"{error}. {SERVICE_HINT}")
            return 1
        if not reply.get("ok"):
            self.alert("Could not start recording", str(reply.get("error", "unknown error")))
            return 1
        return 0

    def stop(self) -> int:
        with try_lock(self.settings.lock_path) as locked:
            if not locked:
                return 0
            try:
                reply = self.request(self.settings.socket_path, "stop", timeout=60)
            except client.ServiceError as error:
                self.alert("Dictation service is not running", f"{error}. {SERVICE_HINT}")
                return 1
            if not reply.get("ok"):
                self.alert("Nothing was recorded", str(reply.get("error", "unknown error")))
                return 1
            cleaned = text.clean(str(reply.get("text", "")))
            if not cleaned:
                self.alert("Nothing was transcribed", "Check that your microphone is on.")
                return 0
            if self.type_text(cleaned):
                return 0
            if self.copy_text(cleaned):
                self.alert("Could not type the text",
                           "It is on your clipboard. Paste it where you want it.")
            else:
                self.alert("Could not type the text", "Copying it to the clipboard failed too.")
            return 1

    def check(self) -> int:
        failures = 0

        def ok(message: str) -> None:
            print(f"  ok    {message}", file=self.out)

        def bad(message: str, hint: str) -> None:
            nonlocal failures
            failures += 1
            print(f"  FAIL  {message}\n        {hint}", file=self.out)

        missing = [tool for tool in TOOLS if not self.is_executable(tool)]
        if missing:
            bad("tools missing: " + " ".join(missing), "Install them with apt.")
        else:
            ok("tools installed")

        display = self.env.get("WAYLAND_DISPLAY", "")
        runtime = self.env.get("XDG_RUNTIME_DIR", "")
        if display and Path(runtime, display).is_socket():
            ok(f"Wayland display: {display}")
        else:
            bad("no Wayland display", "Run this from your desktop session.")

        try:
            status = self.request(self.settings.socket_path, "status", timeout=5)
        except client.ServiceError as error:
            bad(str(error), SERVICE_HINT)
        else:
            ok(f"service running: {status.get('model', '?')} on "
               f"{status.get('device', '?')}, {status.get('state', '?')}")
            cublas = status.get("cublas") or []
            ok(f"cuBLAS: {cublas[0] if cublas else 'none loaded'}")

        source = self.source_lookup()
        if recorder.is_microphone(source):
            ok(f"microphone: {source}")
        else:
            bad(f"input is {source or 'unknown'}",
                "That is a speaker monitor, not a mic. Is your headset on?")

        if self.alert("Dictation check", "If you can see this, alerts work."):
            ok("alert accepted (you should see a notification)")
        else:
            bad("alert rejected", "Failures will only show in the journal.")

        print("\nall checks passed" if failures == 0 else f"\n{failures} check(s) failed",
              file=self.out)
        return 0 if failures == 0 else 1


def run_service(settings: Settings) -> int:  # pragma: no cover - needs the GPU
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    log = logging.getLogger("whisper_dictate")
    os.umask(0o077)
    cublas_dir = transcriber.preload_pip_cublas()
    log.info("cuBLAS from %s", cublas_dir or "the system")
    engine = transcriber.Transcriber(transcriber.load_model(settings), settings.language)
    engine.warm_up()
    info = {"model": settings.model, "device": settings.device,
            "cublas": transcriber.loaded_cublas()}
    log.info("ready: %s", info)
    from .server import Service, sd_notify, serve

    service = Service(recorder.Recorder(settings.recording_path), engine, info)
    stop = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    serve(service, settings.socket_path, stop, on_ready=lambda: sd_notify("READY=1"))
    return 0


def main(argv: list[str] | None = None, app_factory: Callable[[Settings], App] = App) -> int:
    parser = argparse.ArgumentParser(prog="whisper-dictate", description=__doc__)
    parser.add_argument("command", choices=["start", "stop", "check", "serve", "fetch-model"])
    args = parser.parse_args(argv)
    restore_session_env(os.environ)
    settings = Settings.from_env()
    if args.command == "serve":  # pragma: no cover - needs the GPU
        return run_service(settings)
    if args.command == "fetch-model":  # pragma: no cover - network
        print(transcriber.fetch_model(settings))
        return 0
    app = app_factory(settings)
    return {"start": app.start, "stop": app.stop, "check": app.check}[args.command]()


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
