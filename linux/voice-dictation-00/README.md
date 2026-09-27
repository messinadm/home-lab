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
| [`dictate`](dictate) | Starts and stops recording, types the result, and checks the setup |
| COSMIC custom shortcuts | Alt+D to start, Alt+Shift+D to stop and type |

## How it works

1. **Alt+D** runs `dictate start`. It checks that Speech Note is running and that a real microphone is selected, snapshots Speech Note's note, and tells Speech Note to start listening.
2. Speech Note appends each transcript to its note and saves the note in its `settings.conf`.
3. **Alt+Shift+D** runs `dictate stop`. It tells Speech Note to stop, waits until Speech Note reports it's idle and the note is saved, then types everything added since the snapshot into the focused window with `wtype`.

Text appears about two seconds after you press stop, most of it Speech Note transcribing. Like Wispr Flow, it arrives when you finish, not word by word.

- Line breaks and other control characters are typed as spaces, so a dictation never presses Enter and sends a half-finished prompt.
- If anything goes wrong, a desktop notification says what.
- The clipboard is only a fallback: if typing fails, the text goes there so it isn't lost.

## Requirements

| Need | Tested with | Check |
|---|---|---|
| Operating system | Pop!_OS 24.04 LTS | `grep PRETTY_NAME /etc/os-release` |
| Desktop session | COSMIC on Wayland | `echo $XDG_CURRENT_DESKTOP $XDG_SESSION_TYPE` prints `COSMIC wayland` |
| Flatpak with Flathub | Preinstalled on Pop!_OS | `flatpak remotes` lists `flathub` |
| NVIDIA GPU (optional) | RTX 5070 Ti, driver 580 | `nvidia-smi` |
| Microphone | Bluetooth headset | `pactl get-default-source` names a mic, not a `.monitor` |

Other distributions and desktops are untested. The typing step needs a Wayland compositor that supports the virtual-keyboard protocol, which COSMIC does.

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

### 4. Install wtype and wl-clipboard

```bash
sudo apt install wtype wl-clipboard
```

`wl-clipboard` is only used when typing fails, and may already be installed.

### 5. Install the script

```bash
install -m 0755 dictate ~/.local/bin/dictate
```

It also uses `python3`, `gdbus`, `pactl`, and `flock`, which Pop!_OS ships by default.

### 6. Add the shortcuts

In COSMIC Settings, under Keyboard, add two custom shortcuts:

| Shortcut | Command |
|---|---|
| Alt+D | `/home/<you>/.local/bin/dictate start` |
| Alt+Shift+D | `/home/<you>/.local/bin/dictate stop` |

Give the script's full path. The shortcuts work immediately, no logout needed.

### 7. Check the setup

With Speech Note open:

```bash
~/.local/bin/dictate check
```

Every line should say `ok`, and a "Dictation check" notification should appear.

### 8. Try it

Click into a text editor, press Alt+D, say a sentence, and press Alt+Shift+D.

## Daily use

- Open Speech Note once after you log in. It can sit in the background. If you forget, Alt+D tells you.
- Alt+D, talk, Alt+Shift+D.
- Speech Note keeps every transcript in its note, saved as plain text in `settings.conf`. Clear the note in the app when you want them gone.
- If a long dictation gets cut off at a pause, check Speech Note's listening mode in its settings and choose the one that keeps listening until you stop it.
- While bound, Alt+D no longer does its usual jobs (delete-word in terminals, focus the address bar in browsers). Pick another key if you rely on those.

## Things we struggled with

**Wispr Flow has no Linux build.** An unofficial port repackages the Windows app, but it installs a udev rule giving your session read access to every input device, downloads its helper binary without a checksum, has no COSMIC support, and still needs the subscription and cloud transcription.

**Speech Note's "type into active window" mode doesn't work on COSMIC.** It types through ydotool, and Ubuntu 24.04 ships ydotool 0.1.8 from 2021. The daemon runs and reports success, but COSMIC never delivers the keystrokes. `wtype` uses Wayland's virtual-keyboard protocol instead, and COSMIC accepts that.

**Speech Note's clipboard mode returned empty text.** Plain `start-listening` works, so `dictate` reads the transcript from the saved note rather than the clipboard.

**Speech Note sometimes saves the transcript before you press stop.** If the script only looked for changes after stop, it would miss text that was already saved, and dictation would work or fail depending on timing. That's why `dictate start` takes the snapshot, and `dictate stop` types everything added since then.

**Failures were silent.** Speech Note not running, a headset that was off, and an empty transcript all looked the same: the start and stop sounds played and nothing appeared. `dictate` now checks for these and sends a notification, and `dictate check` tests the whole setup.

**Anything addressed to Speech Note by name launches it.** Its actions and its D-Bus name both start the app when it isn't running, which opens its window instead of recording. `dictate` checks first, and talks to the running instance's unique bus name, which can't launch anything. Running Speech Note headless (`dsnote --service`) isn't an option while the app is open: it fails with `dbus service registration failed`.

**A headset that's switched off leaves no microphone.** The default input falls back to a "monitor" source that records speaker output. `dictate start` refuses to record from a monitor and tells you.

**COSMIC can launch the script without the session environment,** and `wtype` then fails without an error. `dictate` restores the Wayland and D-Bus addresses itself when they're missing.

## Troubleshooting

Run `~/.local/bin/dictate check`. It tests each thing the script relies on and names the one that failed.

For a specific dictation, read `$XDG_RUNTIME_DIR/dictate.log`, usually `/run/user/1000/dictate.log`. It covers the most recent dictation: when listening started, Speech Note's state changes and note saves after stop (in milliseconds), and how many characters were typed. It never records the text.

| Notification | Meaning |
|---|---|
| Speech Note is not running | Open Speech Note and try again. |
| No microphone | The input is a speaker monitor, usually because the headset is off. |
| Speech Note refused to start | Outside actions are off, or Speech Note changed. Run `dictate check`. |
| Nothing was transcribed | Speech Note heard nothing. Check the microphone. |
| Dictation timed out | No text after 15 seconds, so nothing was typed. |
| Could not type the text | Typing failed. The text is on your clipboard. |

## Limitations

`dictate` depends on three things in Speech Note that aren't documented interfaces: the note is saved as `note=` in `settings.conf`, the D-Bus `State` property is `3` when Speech Note is idle, and D-Bus `InvokeAction` accepts `start-listening` and `stop-listening`. A Speech Note update could change any of them, and `dictate check` will say which.

## Possible next steps

- **Drop Speech Note.** Record with PipeWire, transcribe with faster-whisper directly on the GPU, and type with `wtype`, so nothing depends on another app's internals. This would be its own project.
- **One key instead of two.** Make Alt+D a toggle: press to start, press again to stop and type. True hold-to-talk isn't possible here, because COSMIC shortcuts only fire when a key is pressed, not released.
- **Start Speech Note at login,** so the first dictation after a reboot works without opening it by hand.
- **Clear old transcripts.** Speech Note keeps every transcript in its note, and nothing prunes it.
