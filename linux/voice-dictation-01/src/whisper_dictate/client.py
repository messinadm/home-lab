"""Talk to the service over its Unix socket."""

from __future__ import annotations

import socket
from pathlib import Path
from typing import Any

from . import protocol


class ServiceError(Exception):
    pass


def request(path: Path, command: str, timeout: float = 60.0) -> dict[str, Any]:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.settimeout(timeout)
            conn.connect(str(path))
            conn.sendall(protocol.encode({"command": command}))
            with conn.makefile("rb") as reader:
                return protocol.read_message(reader)
    except (FileNotFoundError, ConnectionRefusedError) as error:
        raise ServiceError("the dictation service is not running") from error
    except TimeoutError as error:
        raise ServiceError(f"no reply to {command} after {timeout:g}s") from error
    except (OSError, ValueError) as error:
        raise ServiceError(f"bad reply to {command}: {error}") from error
