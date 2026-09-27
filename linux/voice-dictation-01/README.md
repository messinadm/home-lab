# Voice dictation on Linux, without Speech Note

Press a key, talk, press another key, and your words type into whatever app has focus. A small background service keeps a Whisper model on the GPU. Nothing goes to the cloud.

This replaces [voice-dictation-00](../voice-dictation-00/), which drove the Speech Note app and depended on its undocumented internals.

## Goal

Dictate into any app on Linux, especially AI agents like Claude Code in a terminal, using native tools instead of paying for Wispr Flow, which has no Linux version. Every step is code in this project, covered by tests, with nothing depending on another app's internals.

## What it uses

| Piece | Role |
|---|---|
| [faster-whisper](https://github.com/SYSTRAN/faster-whisper) 1.2 on CTranslate2 4.8 | Runs the model on the GPU |
| distil-large-v3 | The speech model (English only), 1.5 GB on disk, pinned to the version this was tested with |
| `nvidia-cublas-cu12` 12.9 (the `cuda` extra) | NVIDIA's GPU math library, with code built for current cards |
| `pw-record` (PipeWire) | Records the microphone |
| [wtype](https://github.com/atx/wtype) 0.4 | Types into the focused Wayland window |
| [`whisper-dictate`](src/whisper_dictate/) | The service, and the command that starts, stops, types, and checks |
| systemd user service | Keeps the model loaded |
| COSMIC custom shortcuts | Alt+D to start, Alt+Shift+D to stop and type |

## How it works

1. At login, systemd starts `whisper-dictate serve`. It loads the model onto the GPU, runs it once to warm up, and listens on a socket only you can use. It only counts as started once it's ready, which takes about a second.
2. **Alt+D** runs `whisper-dictate start`. The service checks that the input is a real microphone and starts recording.
3. **Alt+Shift+D** runs `whisper-dictate stop`. The service stops recording, transcribes, deletes the audio, and returns the text, which the command types into the focused window with `wtype`.

Five seconds of speech transcribes in about 0.15 s on an RTX 5070 Ti, so the text appears almost as soon as you press stop. Like Wispr Flow, it arrives when you finish, not word by word.

- It records until you press stop, so pausing to think doesn't cut anything off.
- Newlines and other control characters are typed as spaces, so a dictation never presses Enter and sends a half-finished prompt.
- The service runs offline. The only network use is the one-time model download.
- Audio is kept in `$XDG_RUNTIME_DIR`, which lives in memory, and is deleted after each dictation, including one that fails or is cut short by a service restart. Logs record durations and character counts, never the text.
- If anything goes wrong, a desktop notification says what.
- The clipboard is only a fallback: if typing fails, the text goes there so it isn't lost.

## Requirements

| Need | Tested with | Check |
|---|---|---|
| Operating system | Pop!_OS 24.04 LTS | `grep PRETTY_NAME /etc/os-release` |
| Desktop session | COSMIC on Wayland | `echo $XDG_CURRENT_DESKTOP $XDG_SESSION_TYPE` prints `COSMIC wayland` |
| NVIDIA GPU | RTX 5070 Ti, driver 580 | `nvidia-smi` |
| Python | 3.12, the system Python | `/usr/bin/python3 --version` |
| uv | 0.12 | `uv --version` |
| Microphone | Bluetooth headset | `pactl get-default-source` names a mic, not a `.monitor` |

Other distributions and desktops are untested, and so is running without a GPU. The typing step needs a Wayland compositor that supports the virtual-keyboard protocol, which COSMIC does.

## Setup

Run these from `linux/voice-dictation-01` in a clone of this repo.

### 1. Install the desktop tools

```bash
sudo apt install wtype wl-clipboard
```

`pw-record` and `pactl` come with Pop!_OS. `wl-clipboard` is only used when typing fails.

### 2. Run the tests

```bash
uv run pytest
```

All tests should pass, with at least 90% coverage.

### 3. Install the command

```bash
uv tool install --python /usr/bin/python3 "whisper-dictate[cuda] @ file://$PWD"
```

This puts `whisper-dictate` in `~/.local/bin`, in its own environment. The `cuda` extra adds NVIDIA's cuBLAS, about 1.1 GB. It's pinned to the system Python, since other Pythons on your `PATH` (Homebrew's, for example) are untested.

### 4. Download the model

```bash
whisper-dictate fetch-model
```

This is the only step that uses the network. The model goes to `~/.local/share/whisper-dictate/models`.

### 5. Start the service

```bash
mkdir -p ~/.config/systemd/user
cp systemd/whisper-dictate.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now whisper-dictate
```

It starts now and at every login.

### 6. Add the shortcuts

In COSMIC Settings, under Keyboard, add two custom shortcuts:

| Shortcut | Command |
|---|---|
| Alt+D | `/home/<you>/.local/bin/whisper-dictate start` |
| Alt+Shift+D | `/home/<you>/.local/bin/whisper-dictate stop` |

Give the full path. The shortcuts work immediately, no logout needed.

### 7. Check the setup

```bash
whisper-dictate check
```

Every line should say `ok`, and a "Dictation check" notification should appear.

### 8. Try it

Click into a text editor, press Alt+D, say a sentence, and press Alt+Shift+D.

## Daily use

- Alt+D, talk, Alt+Shift+D. There's no app to open first.
- The service holds about 2.2 GB of GPU memory while it runs. `systemctl --user stop whisper-dictate` frees it, and `start` brings it back in about a second.
- While bound, Alt+D no longer does its usual jobs (delete-word in terminals, focus the address bar in browsers). Pick another key if you rely on those.
- To update after changing the code, run the tests, then reinstall and restart:

```bash
uv run pytest
uv tool install --reinstall --python /usr/bin/python3 "whisper-dictate[cuda] @ file://$PWD"
systemctl --user restart whisper-dictate
```

## Things we struggled with

**Existing dictation apps are hard to drive from outside.** Speech Note, the obvious local option on Flathub, has no stable interface for other programs: getting its text out meant reading its settings file and guessing at its internal state values. Running faster-whisper directly means every step is ours to test.

**ydotool doesn't type into COSMIC windows.** It's the usual tool for synthetic typing on Wayland, and Ubuntu 24.04 ships version 0.1.8 from 2021. Its daemon runs and reports success, but COSMIC never delivers the keystrokes. `wtype` uses Wayland's virtual-keyboard protocol instead, and COSMIC accepts that.

**The GPU was newer than the system's CUDA libraries.** With the CUDA 12.0 cuBLAS from Ubuntu's toolkit, the first transcription took 11 s while the driver compiled code for the RTX 5070 Ti, and later ones took 0.22 s. NVIDIA's cuBLAS 12.9 from PyPI ships that code ready-made: no compile, and 0.10 s. The service loads it ahead of the system copy, and `check` shows which one is in use.

**Whisper makes up words for silence,** typically "Thank you." Filtering out silence before transcribing (faster-whisper's VAD filter) stops it.

**`systemctl start` returned before the model was loaded.** The service now tells systemd when it's ready (`Type=notify`), so start waits, and a failed model load shows up as a failed start.

**A headset that's switched off leaves no microphone.** The default input falls back to a "monitor" source that records speaker output. The service refuses to record from a monitor and says so.

**COSMIC can launch the command without the session environment,** and `wtype` then fails without an error. The command restores the Wayland and D-Bus addresses itself when they're missing.

## Troubleshooting

Run `whisper-dictate check`. It tests each thing the setup relies on and names the one that failed.

The service log is `journalctl --user -u whisper-dictate`. It shows which cuBLAS was loaded and, for each dictation, how long the audio was, how long transcription took, and how many characters came back. It never records the text.

| Notification | Meaning |
|---|---|
| Dictation service is not running | Start it: `systemctl --user start whisper-dictate`. |
| Could not start recording | The reason is in the message. Usually the input is a speaker monitor because the headset is off. |
| Nothing was recorded | Stop was pressed without a start, or the recording failed. |
| Nothing was transcribed | The model heard no speech. Check the microphone. |
| Could not type the text | Typing failed. The text is on your clipboard. |

To run the real model on the real GPU, which the unit tests and CI can't:

```bash
WHISPER_DICTATE_GPU_TEST=1 uv run --extra cuda pytest -m gpu --no-cov
```

## Limitations

- It needs an NVIDIA GPU. `WHISPER_DICTATE_DEVICE=cpu` with a smaller model might work, but it's untested.
- The model, distil-large-v3, is English only. `WHISPER_DICTATE_MODEL` picks another model: set it for the service, run `fetch-model`, and restart. Only the default model is pinned to a tested version; `WHISPER_DICTATE_MODEL_REVISION` pins another.
- The model stays in GPU memory for as long as the service runs.

## Possible next steps

- **One key instead of two.** Make Alt+D a toggle. That's straightforward now, because the service knows whether it's recording.
- **Rewrite the command in Rust.** The part that runs on each keypress (talk to the socket, type, alert) is small and self-contained, and the Python version is the reference to test against.
- **Free GPU memory when idle.** Unload the model after a while without dictation, and reload it on start, which costs about a second.
- **Install the service from the command,** for example `whisper-dictate install-service`, instead of copying the unit by hand.
