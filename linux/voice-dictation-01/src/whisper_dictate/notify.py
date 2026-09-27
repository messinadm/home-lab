"""Desktop notifications through the freedesktop notification service."""

from __future__ import annotations

import subprocess
from collections.abc import Callable

GDBUS = "/usr/bin/gdbus"

Runner = Callable[..., subprocess.CompletedProcess]


def gvariant_string(value: str) -> str:
    """Quote a string as a GVariant text literal, as gdbus expects."""
    escaped = value.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def notify_command(summary: str, body: str, timeout_ms: int = 8000) -> list[str]:
    return [
        GDBUS, "call", "--session",
        "--dest", "org.freedesktop.Notifications",
        "--object-path", "/org/freedesktop/Notifications",
        "--method", "org.freedesktop.Notifications.Notify",
        gvariant_string("Dictation"), "0",
        gvariant_string("audio-input-microphone"),
        gvariant_string(summary), gvariant_string(body),
        "[]", "{}", str(timeout_ms),
    ]


def notify(summary: str, body: str, run: Runner = subprocess.run) -> bool:
    """Show a notification. Returns whether the service accepted it."""
    try:
        result = run(
            notify_command(summary, body),
            capture_output=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0
