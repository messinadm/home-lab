# Voice dictation on Linux

Press a key, talk, press another key, and your words type into whatever app has focus. Transcription runs locally on the GPU. Nothing goes to the cloud.

## Goal

Dictate into any app on Linux, especially AI agents like Claude Code in a terminal, using native tools instead of paying for Wispr Flow, which has no Linux version.

## What it uses

| Piece | Role |
|---|---|
| [Speech Note](https://flathub.org/apps/net.mkiol.SpeechNote) 4.8.4 (Flatpak) | Records and transcribes |
| FasterWhisper Distil Large-v3 | The speech model (English only), run on the GPU |
| Speech Note NVIDIA add-on | CUDA acceleration |
| [wtype](https://github.com/atx/wtype) 0.4 | Types text into the focused Wayland window |
| [`dictate`](dictate) | Starts and stops recording, and types the result |
| COSMIC custom shortcuts | Alt+D to start, Alt+Shift+D to stop and type |

Tested on Pop!_OS 24.04 with the COSMIC desktop (Wayland) and an NVIDIA RTX 5070 Ti on driver 580.

## How it works

1. **Alt+D** runs `dictate start`, which snapshots Speech Note's note and tells it to start listening.
2. Speech Note appends each transcript to its note and saves the note in its `settings.conf`.
3. **Alt+Shift+D** runs `dictate stop`, which stops listening, waits until Speech Note is idle and the note has settled, then types everything added since the snapshot into the focused window with `wtype`.

The text appears a second or two after you press stop. Like Wispr Flow, it arrives when you finish, not word by word. Line breaks are typed as spaces, so a long dictation never presses Enter and sends a half-finished prompt. The clipboard isn't touched.

## Setup

### 1. Install Speech Note and the GPU add-on

```bash
flatpak install flathub net.mkiol.SpeechNote net.mkiol.SpeechNote.Addon.nvidia
```

The add-on is a multi-GB download. Without an NVIDIA GPU, skip it and pick a smaller model in step 2.

### 2. Download the model

Open Speech Note, download **English (FasterWhisper Distil Large-v3)**, and make it the active speech-to-text model.

Distil Large-v3 is close to full Large-v3 accuracy at several times the speed, and speed is what you feel when you're waiting for text. Avoid the **CrisperWhisper** variants for dictation: they're tuned for verbatim transcripts and keep every "um".

### 3. Allow outside actions

In Speech Note's settings, enable the option that lets other programs invoke actions. The shortcuts do nothing without it. Once it's on, this line appears in `~/.var/app/net.mkiol.SpeechNote/config/net.mkiol/dsnote/settings.conf`:

```ini
actions_api_enabled=true
```

### 4. Install wtype

```bash
sudo apt install wtype
```

### 5. Install the script

```bash
install -m 0755 dictate ~/.local/bin/dictate
```

It also needs `python3`, `gdbus`, and `flock`, which Pop!_OS ships by default.

### 6. Add the shortcuts

In COSMIC Settings, under Keyboard, add two custom shortcuts:

| Shortcut | Command |
|---|---|
| Alt+D | `/home/<you>/.local/bin/dictate start` |
| Alt+Shift+D | `/home/<you>/.local/bin/dictate stop` |

Give the script's full path. The shortcuts work immediately, no logout needed.

### 7. Try it

With Speech Note open, click into a text editor, press Alt+D, say a sentence, and press Alt+Shift+D.

## Daily use

- Open Speech Note once after you log in. It can sit in the background.
- Alt+D, talk, Alt+Shift+D.
- Speech Note keeps every transcript in its note, saved as plain text in `settings.conf`. Clear the note in the app when you want them gone.
- If a long dictation gets cut off at a pause, check Speech Note's listening mode in its settings and choose the one that keeps listening until you stop it.
- While bound, Alt+D no longer does its usual jobs (delete-word in terminals, focus the address bar in browsers). Pick another key if you rely on those.

## Things we struggled with

**Wispr Flow has no Linux build.** An unofficial port repackages the Windows app, but it installs a udev rule giving your session read access to every input device, downloads its helper binary without a checksum, has no COSMIC support, and still needs the subscription and cloud transcription.

**Speech Note's "type into active window" mode doesn't work on COSMIC.** It types through ydotool, and Ubuntu 24.04 ships ydotool 0.1.8 from 2021. The daemon runs and reports success, but COSMIC never delivers the keystrokes. `wtype` uses Wayland's virtual-keyboard protocol instead, and COSMIC accepts that.

**Speech Note's clipboard mode returned empty text.** Plain `start-listening` works, so `dictate` reads the transcript from the saved note rather than the clipboard.

**Speech Note sometimes saves the transcript before you press stop.** If the script only looked for changes after stop, it would miss text that was already saved, and dictation would work or fail depending on timing. That's why `dictate start` takes the snapshot, and `dictate stop` types everything added since then.

**If Speech Note isn't running, Alt+D opens it instead of recording.** Actions only reach a running instance. Running it headless (`dsnote --service`) isn't an option while the app is open: it fails with `dbus service registration failed`.

**A headset that's switched off fails silently.** The default input falls back to a "monitor" source that records speaker output, so you get the start and stop sounds and an empty transcript. Check the input with:

```bash
pactl info | grep 'Default Source'
```

It should name a microphone, not something ending in `.monitor`.

**COSMIC can launch the script without the session environment,** and `wtype` then fails without an error. `dictate` restores the Wayland and D-Bus addresses itself when they're missing.

## Troubleshooting

`dictate` logs each dictation to `$XDG_RUNTIME_DIR/dictate.log`, usually `/run/user/1000/dictate.log`. The log shows when listening started and stopped, and how many characters were typed. It doesn't record the text.
