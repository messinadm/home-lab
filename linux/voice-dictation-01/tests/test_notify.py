import subprocess

from whisper_dictate import notify


def fake_run(returncode=0, error=None):
    def run(argv, **kwargs):
        run.argv = argv
        run.kwargs = kwargs
        if error is not None:
            raise error
        return subprocess.CompletedProcess(argv, returncode)
    return run


def test_gvariant_string_escapes_quotes_and_backslashes():
    assert notify.gvariant_string("it's") == "'it\\'s'"
    assert notify.gvariant_string("a\\b") == "'a\\\\b'"
    assert notify.gvariant_string("plain") == "'plain'"


def test_command_calls_the_freedesktop_notify_method():
    command = notify.notify_command("Title", "Body", timeout_ms=1234)
    assert command[0] == notify.GDBUS
    assert "org.freedesktop.Notifications.Notify" in command
    assert "'Title'" in command
    assert "'Body'" in command
    assert command[-1] == "1234"


def test_notify_reports_acceptance():
    run = fake_run(0)
    assert notify.notify("Title", "Body", run=run) is True
    assert run.kwargs["timeout"] == 5


def test_notify_reports_rejection():
    assert notify.notify("Title", "Body", run=fake_run(1)) is False


def test_notify_survives_missing_gdbus():
    assert notify.notify("Title", "Body", run=fake_run(error=FileNotFoundError())) is False


def test_notify_survives_a_hung_bus():
    error = subprocess.TimeoutExpired("gdbus", 5)
    assert notify.notify("Title", "Body", run=fake_run(error=error)) is False
