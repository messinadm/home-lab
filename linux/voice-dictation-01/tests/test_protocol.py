import io

import pytest

from whisper_dictate import protocol


def test_roundtrip_keeps_unicode():
    message = {"ok": True, "text": "héllo “world”"}
    assert protocol.decode(protocol.encode(message)) == message


def test_encode_is_exactly_one_line_even_with_newlines_in_text():
    data = protocol.encode({"text": "a\nb"})
    assert data.count(b"\n") == 1
    assert data.endswith(b"\n")


@pytest.mark.parametrize("line", [b"[1, 2]\n", b"\"text\"\n", b"42\n"])
def test_decode_rejects_non_objects(line):
    with pytest.raises(ValueError, match="JSON object"):
        protocol.decode(line)


def test_decode_rejects_bad_json():
    with pytest.raises(ValueError):
        protocol.decode(b"{nope\n")


def test_decode_rejects_bad_utf8():
    with pytest.raises(ValueError):
        protocol.decode(b"\xff\xfe\n")


def test_decode_rejects_oversized_messages():
    with pytest.raises(ValueError, match="too long"):
        protocol.decode(b"x" * (protocol.MAX_LINE + 1))


def test_read_message_reads_one_line():
    reader = io.BytesIO(b'{"command": "stop"}\n{"command": "start"}\n')
    assert protocol.read_message(reader) == {"command": "stop"}


def test_read_message_rejects_empty_input():
    with pytest.raises(ValueError, match="empty"):
        protocol.read_message(io.BytesIO(b""))
