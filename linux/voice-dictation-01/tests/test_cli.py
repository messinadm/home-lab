import io
import os
import socket
import subprocess

import pytest

from whisper_dictate import cli, client
from whisper_dictate.config import Settings


class Harness:
    def __init__(self, tmp_path, replies=None, error=None, typed=True, copied=True,
                 source="bluez_input.mic", executable=True, alerted=True, env=None):
        self.replies = replies or {}
        self.error = error
        self.requests, self.alerts, self.typed, self.copied = [], [], [], []
        self.out = io.StringIO()
        self.settings = Settings(runtime_dir=tmp_path, models_dir=tmp_path / "models")
        self.app = cli.App(
            self.settings,
            request=self.request,
            alert=lambda summary, body: self.alerts.append((summary, body)) or alerted,
            type_text=lambda text: self.typed.append(text) or typed,
            copy_text=lambda text: self.copied.append(text) or copied,
            source_lookup=lambda: source,
            is_executable=lambda path: executable,
            env=env if env is not None else {},
            out=self.out,
        )

    def request(self, path, command, timeout):
        self.requests.append(command)
        if self.error is not None:
            raise self.error
        return self.replies[command]


DOWN = client.ServiceError("the dictation service is not running")


def test_start_ok(tmp_path):
    h = Harness(tmp_path, replies={"start": {"ok": True}})
    assert h.app.start() == 0
    assert h.alerts == []


def test_start_with_the_service_down_alerts(tmp_path):
    h = Harness(tmp_path, error=DOWN)
    assert h.app.start() == 1
    assert h.alerts[0][0] == "Dictation service is not running"
    assert "systemctl --user start whisper-dictate" in h.alerts[0][1]


def test_start_refused_alerts_with_the_reason(tmp_path):
    h = Harness(tmp_path, replies={"start": {"ok": False, "error": "input is x.monitor"}})
    assert h.app.start() == 1
    assert h.alerts == [("Could not start recording", "input is x.monitor")]


def test_stop_types_the_cleaned_text(tmp_path):
    h = Harness(tmp_path, replies={"stop": {"ok": True, "text": "one\ntwo\r\n"}})
    assert h.app.stop() == 0
    assert h.typed == ["one two"]
    assert h.alerts == []


def test_stop_with_nothing_heard_alerts(tmp_path):
    h = Harness(tmp_path, replies={"stop": {"ok": True, "text": "  \n"}})
    assert h.app.stop() == 0
    assert h.typed == []
    assert h.alerts[0][0] == "Nothing was transcribed"


def test_stop_refused_alerts(tmp_path):
    h = Harness(tmp_path, replies={"stop": {"ok": False, "error": "not recording"}})
    assert h.app.stop() == 1
    assert h.alerts == [("Nothing was recorded", "not recording")]


def test_stop_with_the_service_down_alerts(tmp_path):
    h = Harness(tmp_path, error=DOWN)
    assert h.app.stop() == 1
    assert h.alerts[0][0] == "Dictation service is not running"


def test_stop_falls_back_to_the_clipboard(tmp_path):
    h = Harness(tmp_path, replies={"stop": {"ok": True, "text": "keep me"}}, typed=False)
    assert h.app.stop() == 1
    assert h.copied == ["keep me"]
    assert "clipboard" in h.alerts[0][1]


def test_stop_reports_when_the_clipboard_fails_too(tmp_path):
    h = Harness(tmp_path, replies={"stop": {"ok": True, "text": "x"}}, typed=False, copied=False)
    assert h.app.stop() == 1
    assert "failed too" in h.alerts[0][1]


def test_a_second_stop_while_one_is_running_does_nothing(tmp_path):
    h = Harness(tmp_path, replies={"stop": {"ok": True, "text": "x"}})
    with cli.try_lock(h.settings.lock_path) as locked:
        assert locked
        assert h.app.stop() == 0
    assert h.requests == []


def wayland_env(tmp_path):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(tmp_path / "wayland-1"))
    return sock, {"WAYLAND_DISPLAY": "wayland-1", "XDG_RUNTIME_DIR": str(tmp_path)}


def test_check_passes_when_everything_is_in_place(tmp_path):
    sock, env = wayland_env(tmp_path)
    with sock:
        status = {"ok": True, "state": "idle", "model": "distil-large-v3",
                  "revision": "c3058b475261292e", "device": "cuda",
                  "cublas": ["/nv/libcublas.so.12"]}
        h = Harness(tmp_path, replies={"status": status}, env=env)
        assert h.app.check() == 0
    output = h.out.getvalue()
    assert "FAIL" not in output
    assert "distil-large-v3 @ c3058b4 on cuda, idle" in output
    assert "/nv/libcublas.so.12" in output
    assert "all checks passed" in output


def test_check_names_every_failure(tmp_path):
    h = Harness(tmp_path, error=DOWN, source="x.monitor", executable=False, alerted=False)
    assert h.app.check() == 1
    output = h.out.getvalue()
    assert output.count("FAIL") == 5
    assert "tools missing" in output
    assert "no Wayland display" in output
    assert "not running" in output
    assert "x.monitor" in output
    assert "alert rejected" in output
    assert "5 check(s) failed" in output


def test_check_reports_when_no_cublas_is_loaded(tmp_path):
    h = Harness(tmp_path, replies={"status": {"ok": True, "cublas": []}})
    h.app.check()
    assert "cuBLAS: none loaded" in h.out.getvalue()


def test_restore_session_env_finds_the_wayland_socket(tmp_path):
    (tmp_path / "wayland-0").write_text("not a socket")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.bind(str(tmp_path / "wayland-1"))
        env = cli.restore_session_env({"XDG_RUNTIME_DIR": str(tmp_path)})
    assert env["WAYLAND_DISPLAY"] == "wayland-1"
    assert env["DBUS_SESSION_BUS_ADDRESS"] == f"unix:path={tmp_path}/bus"


def test_restore_session_env_keeps_what_is_already_set(tmp_path):
    env = cli.restore_session_env({
        "XDG_RUNTIME_DIR": str(tmp_path), "WAYLAND_DISPLAY": "wayland-9",
        "DBUS_SESSION_BUS_ADDRESS": "unix:path=/custom"})
    assert env["WAYLAND_DISPLAY"] == "wayland-9"
    assert env["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=/custom"


def test_restore_session_env_defaults_the_runtime_dir(monkeypatch):
    monkeypatch.setattr(os, "getuid", lambda: 4321)
    env = cli.restore_session_env({})
    assert env["XDG_RUNTIME_DIR"] == "/run/user/4321"
    assert "WAYLAND_DISPLAY" not in env


def fake_run(returncode=0, error=None):
    def run(argv, **kwargs):
        run.argv, run.input = argv, kwargs["input"]
        if error is not None:
            raise error
        return subprocess.CompletedProcess(argv, returncode)
    return run


def test_type_text_pipes_utf8_to_wtype():
    run = fake_run()
    assert cli.type_text("héllo", run=run) is True
    assert run.argv == [cli.WTYPE, "-"]
    assert run.input == "héllo".encode()


def test_copy_text_uses_wl_copy():
    run = fake_run()
    assert cli.copy_text("x", run=run) is True
    assert run.argv == [cli.WL_COPY]


@pytest.mark.parametrize("run", [
    fake_run(returncode=1),
    fake_run(error=FileNotFoundError()),
    fake_run(error=subprocess.TimeoutExpired("wtype", 30)),
])
def test_type_text_failures(run):
    assert cli.type_text("x", run=run) is False


def test_try_lock_is_exclusive(tmp_path):
    with cli.try_lock(tmp_path / "lock") as first:
        with cli.try_lock(tmp_path / "lock") as second:
            assert (first, second) == (True, False)


@pytest.mark.parametrize("command", ["start", "stop", "check"])
def test_main_dispatches(monkeypatch, tmp_path, command):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/x")
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-1")

    class FakeApp:
        def __init__(self, settings):
            assert settings.runtime_dir == tmp_path

        def start(self):
            return 11

        def stop(self):
            return 12

        def check(self):
            return 13

    assert cli.main([command], app_factory=FakeApp) == {"start": 11, "stop": 12, "check": 13}[command]


def test_main_rejects_unknown_commands():
    with pytest.raises(SystemExit):
        cli.main(["dance"])
