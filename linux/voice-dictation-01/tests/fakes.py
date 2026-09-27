"""Fakes shared by the server, client and CLI tests."""

from whisper_dictate.recorder import RecorderError


class FakeRecorder:
    def __init__(self, path, start_error=None):
        self.path = path
        self.recording = False
        self.start_error = start_error

    def start(self):
        if self.start_error:
            raise RecorderError(self.start_error)
        self.recording = True

    def stop(self):
        if not self.recording:
            raise RecorderError("not recording")
        self.recording = False
        self.path.write_bytes(b"audio")
        return self.path


class FakeTranscriber:
    def __init__(self, text="hello world", error=None):
        self.text = text
        self.error = error
        self.seen = []

    def transcribe(self, audio):
        self.seen.append(audio)
        if self.error:
            raise self.error
        return self.text
