import socket
import threading

import pytest

from whisper_dictate import client, protocol


def one_shot_server(path, reply=None):
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(path))
    server.listen(1)

    def answer():
        conn, _ = server.accept()
        with conn:
            conn.makefile("rb").readline()
            if reply is not None:
                conn.sendall(reply)
                return
            threading.Event().wait(1)

    thread = threading.Thread(target=answer, daemon=True)
    thread.start()
    return server


def test_request_returns_the_reply(tmp_path):
    path = tmp_path / "s"
    with one_shot_server(path, protocol.encode({"ok": True, "state": "idle"})):
        assert client.request(path, "status", timeout=5) == {"ok": True, "state": "idle"}


def test_missing_socket_means_the_service_is_not_running(tmp_path):
    with pytest.raises(client.ServiceError, match="not running"):
        client.request(tmp_path / "missing", "status")


def test_refused_connection_means_the_service_is_not_running(tmp_path):
    path = tmp_path / "s"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as bound_only:
        bound_only.bind(str(path))
        with pytest.raises(client.ServiceError, match="not running"):
            client.request(path, "status")


def test_silent_service_times_out(tmp_path):
    path = tmp_path / "s"
    with one_shot_server(path, reply=None):
        with pytest.raises(client.ServiceError, match="no reply to stop after 0.2s"):
            client.request(path, "stop", timeout=0.2)


def test_garbled_reply_is_an_error(tmp_path):
    path = tmp_path / "s"
    with one_shot_server(path, b"garbage\n"):
        with pytest.raises(client.ServiceError, match="bad reply"):
            client.request(path, "status", timeout=5)
