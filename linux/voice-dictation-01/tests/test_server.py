import socket
import stat
import threading

from fakes import FakeRecorder, FakeTranscriber

from whisper_dictate import client, protocol
import os

from whisper_dictate.server import Service, bind, handle_connection, sd_notify, serve


def make_service(tmp_path, clock=None, **options):
    recorder = FakeRecorder(tmp_path / "rec.wav", start_error=options.pop("start_error", None))
    engine = FakeTranscriber(**options)
    kwargs = {"clock": clock} if clock else {}
    return Service(recorder, engine, info={"model": "m", "device": "d"}, **kwargs), recorder, engine


def test_status_reports_state_and_info(tmp_path):
    service, recorder, _ = make_service(tmp_path)
    assert service.handle({"command": "status"}) == {
        "ok": True, "state": "idle", "model": "m", "device": "d"}
    recorder.recording = True
    assert service.handle({"command": "status"})["state"] == "recording"


def test_start_begins_recording(tmp_path):
    service, recorder, _ = make_service(tmp_path)
    assert service.handle({"command": "start"}) == {"ok": True}
    assert recorder.recording


def test_second_start_is_harmless(tmp_path):
    service, _, _ = make_service(tmp_path)
    service.handle({"command": "start"})
    assert service.handle({"command": "start"}) == {"ok": True, "already": True}


def test_start_reports_recorder_errors(tmp_path):
    service, _, _ = make_service(tmp_path, start_error="input is x.monitor")
    assert service.handle({"command": "start"}) == {"ok": False, "error": "input is x.monitor"}


def test_stop_returns_text_and_deletes_the_audio(tmp_path):
    clock = iter([10.0, 13.0, 13.0, 13.4]).__next__
    service, _, engine = make_service(tmp_path, clock=clock, text="hi there")
    service.handle({"command": "start"})
    reply = service.handle({"command": "stop"})
    assert reply == {"ok": True, "text": "hi there", "audio_seconds": 3.0,
                     "transcribe_seconds": 0.4}
    assert engine.seen == [str(tmp_path / "rec.wav")]
    assert not (tmp_path / "rec.wav").exists()


def test_stop_without_a_start_time_still_works(tmp_path):
    service, recorder, _ = make_service(tmp_path)
    recorder.recording = True
    assert service.handle({"command": "stop"})["ok"] is True


def test_stop_when_idle_is_an_error(tmp_path):
    service, _, _ = make_service(tmp_path)
    assert service.handle({"command": "stop"}) == {"ok": False, "error": "not recording"}


def test_transcription_failure_is_reported_and_audio_deleted(tmp_path):
    service, _, _ = make_service(tmp_path, error=RuntimeError("CUDA out of memory"))
    service.handle({"command": "start"})
    reply = service.handle({"command": "stop"})
    assert reply["ok"] is False
    assert "CUDA out of memory" in reply["error"]
    assert not (tmp_path / "rec.wav").exists()


def test_unknown_command(tmp_path):
    service, _, _ = make_service(tmp_path)
    assert service.handle({"command": "explode"})["ok"] is False
    assert service.handle({})["ok"] is False


def exchange(service, payload):
    ours, theirs = socket.socketpair()
    with ours, theirs:
        theirs.sendall(payload)
        handle_connection(service, ours)
        with theirs.makefile("rb") as reader:
            return protocol.read_message(reader)


def test_connection_with_bad_json_gets_an_error_reply(tmp_path):
    service, _, _ = make_service(tmp_path)
    reply = exchange(service, b"not json\n")
    assert reply["ok"] is False
    assert "bad request" in reply["error"]


def test_connection_with_a_request_is_answered(tmp_path):
    service, _, _ = make_service(tmp_path)
    assert exchange(service, protocol.encode({"command": "status"}))["state"] == "idle"


def test_a_client_that_hangs_up_does_not_crash_the_service(tmp_path):
    service, _, _ = make_service(tmp_path)
    ours, theirs = socket.socketpair()
    with ours:
        theirs.sendall(protocol.encode({"command": "status"}))
        theirs.close()
        handle_connection(service, ours)


def test_bind_replaces_a_stale_socket_and_is_private(tmp_path):
    path = tmp_path / "s"
    path.write_text("stale")
    server = bind(path)
    try:
        assert stat.S_ISSOCK(path.stat().st_mode)
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    finally:
        server.close()


def test_serve_end_to_end_over_a_real_socket(tmp_path):
    service, _, _ = make_service(tmp_path, text="typed words")
    path = tmp_path / "s"
    stop, ready = threading.Event(), threading.Event()
    thread = threading.Thread(target=serve, args=(service, path, stop, ready.set))
    thread.start()
    try:
        assert ready.wait(5)
        assert client.request(path, "start", timeout=5) == {"ok": True}
        assert client.request(path, "stop", timeout=5)["text"] == "typed words"
    finally:
        stop.set()
        thread.join(5)
    assert not thread.is_alive()
    assert not path.exists()


def test_serve_works_without_a_ready_callback(tmp_path):
    service, _, _ = make_service(tmp_path)
    path = tmp_path / "s"
    stop = threading.Event()
    thread = threading.Thread(target=serve, args=(service, path, stop))
    thread.start()
    try:
        for _ in range(100):
            if path.exists():
                break
            threading.Event().wait(0.02)
        assert client.request(path, "status", timeout=5)["state"] == "idle"
    finally:
        stop.set()
        thread.join(5)


def test_sd_notify_without_systemd_does_nothing():
    assert sd_notify("READY=1", env={}) is False


def test_sd_notify_sends_to_a_filesystem_socket(tmp_path):
    path = tmp_path / "notify"
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as listener:
        listener.bind(str(path))
        assert sd_notify("READY=1", env={"NOTIFY_SOCKET": str(path)}) is True
        assert listener.recv(64) == b"READY=1"


def test_sd_notify_handles_abstract_sockets():
    name = f"whisper-dictate-test-{os.getpid()}"
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as listener:
        listener.bind("\0" + name)
        assert sd_notify("READY=1", env={"NOTIFY_SOCKET": "@" + name}) is True
        assert listener.recv(64) == b"READY=1"


def test_sd_notify_survives_a_missing_socket(tmp_path):
    assert sd_notify("READY=1", env={"NOTIFY_SOCKET": str(tmp_path / "gone")}) is False
