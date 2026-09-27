"""Wire format between the command and the service: one JSON object per line."""

from __future__ import annotations

import json
from typing import Any, BinaryIO

MAX_LINE = 1 << 20


def encode(message: dict[str, Any]) -> bytes:
    return (json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8")


def decode(line: bytes) -> dict[str, Any]:
    if len(line) > MAX_LINE:
        raise ValueError("message too long")
    value = json.loads(line.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("message must be a JSON object")
    return value


def read_message(reader: BinaryIO) -> dict[str, Any]:
    line = reader.readline(MAX_LINE + 1)
    if not line:
        raise ValueError("empty message")
    return decode(line)
