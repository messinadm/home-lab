# Transcribing audio and video on a Mac, for feeding to an AI

Point a command at a recording and get a text file back. Everything runs on the
laptop, so recordings that shouldn't leave it don't.

## Goal

Turn a recorded meeting or screen share into text an AI agent can read. Agents can't
listen to a `.m4a` or watch an `.mp4`, so a recording is invisible to them until
something transcribes it — and the obvious options either upload the audio to a
service or want a subscription.

The target is a one-liner that takes any file `ffmpeg` can open and writes a
transcript beside it, fast enough that a ten-minute recording isn't a coffee break.

This is the batch, file-at-a-time counterpart to
[voice-dictation-01](../../linux/voice-dictation-01/), which does live dictation on
Linux. Different problem, different machine, no shared code.

## What it uses

| Piece | Role |
|---|---|
| [whisper.cpp](https://github.com/ggerganov/whisper.cpp) 1.9 | Runs the model, on Metal |
| `ggml-medium.en.bin` | The speech model (English only), 1.5 GB on disk |
| ffmpeg 9 | Decodes any input to the one audio format the model accepts |
| ffprobe | Reports duration, so the script can say what it's working on |
| [`transcribe`](transcribe) | The wrapper that ties the three together |

Homebrew installs the first three. `whisper.cpp` picks up Metal on Apple Silicon with
no configuration.

## How it works

1. `ffprobe` reads the duration, just to print it.
2. `ffmpeg` decodes the input to 16 kHz mono 16-bit WAV in a temp file. This is the
   only format whisper.cpp accepts, and converting up front is why the input can be
   anything — `.m4a`, `.mp4`, `.mov`, `.wav`, a video with its audio buried in it.
3. `whisper-cli` runs the model over the WAV and writes the transcript using the
   source file's name.
4. The temp WAV is deleted, including when a step fails.

About **15x faster than real time** on an M3 Pro with `medium.en`: an 8-minute recording
transcribes in about 30 seconds. Smaller models are faster and noticeably worse at proper
nouns and technical terms, which is usually the part worth reading.

Nothing goes to the network except the one-time model download.

## Requirements

| Need | Tested with | Check |
|---|---|---|
| Operating system | macOS 27 | `sw_vers -productVersion` |
| Chip | Apple M3 Pro | `sysctl -n machdep.cpu.brand_string` |
| Homebrew | in `/opt/homebrew` | `brew --prefix` |
| Disk | ~1.6 GB for the model | `df -h ~` |

Intel Macs and other model sizes are untested. The script looks for the tools in the
Apple Silicon Homebrew prefix; on Intel, set `TRANSCRIBE_BREW_BIN=/usr/local/bin`.

## Setup

### 1. Install the tools

```bash
brew install ffmpeg whisper-cpp
```

### 2. Run the tests

```bash
brew install bats-core kcov
tests/run
```

All tests should pass, with at least 90% coverage. They use fake versions of ffmpeg,
whisper.cpp and curl, so they need no model and no network.

### 3. Install the command

```bash
mkdir -p ~/.local/bin
cp transcribe ~/.local/bin/
chmod +x ~/.local/bin/transcribe
```

Make sure `~/.local/bin` is on your `PATH`.

### 4. Download the model

```bash
transcribe fetch-model
```

About 1.5 GB, and the only step that touches the network. It lands in
`~/.local/share/transcribe/models`. Pass a name to get a different one:
`transcribe fetch-model small.en`.

### 5. Try it

```bash
transcribe some-recording.m4a
```

The transcript appears as `some-recording.txt` next to it.

## Daily use

```bash
transcribe recording.m4a                  # writes recording.txt beside it
transcribe -f srt talk.mp4                # subtitles with timestamps
transcribe -m small.en -o ~/notes *.m4a   # faster model, all into one folder
```

Zoom's local recordings live in `/Users/<you>/Documents/Zoom/<meeting>/`, as an
`.m4a` and an `.mp4` of the same thing. Transcribe the `.m4a` — same audio, a quarter
of the bytes to decode.

Environment variables, if the flags get repetitive:

| Variable | Does |
|---|---|
| `TRANSCRIBE_MODEL` | Default model instead of `medium.en` |
| `TRANSCRIBE_MODEL_DIR` | Where models live |
| `TRANSCRIBE_BREW_BIN` | Where Homebrew's tools are, instead of `/opt/homebrew/bin` |

## Things we struggled with

**Homebrew installs whisper.cpp with no model.** `brew install whisper-cpp` gives you
the binary and nothing to run, and the failure is a wall of usage text rather than
"there is no model." The caveats mention it; they scroll past. `fetch-model` exists
so this is one command rather than a trip to Hugging Face to work out which of ~30
files is the right one.

**The model download has to be interruptible safely.** 1.5 GB over a flaky connection
leaves a truncated `.bin` that the loader accepts and then fails strangely on. The
script downloads to `.part` and renames only on success, so a killed download leaves
nothing behind to be confused by later.

**whisper.cpp only accepts 16 kHz mono WAV.** Hand it an `.m4a` and it fails without
saying that's why. Converting unconditionally with `ffmpeg` first is what makes the
input format a non-issue.

**Whisper invents dialogue during silence,** usually "Thank you" or "[BLANK_AUDIO]".
Worth knowing before trusting a transcript of a recording with long gaps.

**`ffmpeg` without `-nostdin` swallows the terminal** when several files are
processed in a loop, because it reads stdin for keyboard controls and consumes the
rest of the input.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `missing /opt/homebrew/bin/…` | Tools not installed, or Intel Mac — set `TRANSCRIBE_BREW_BIN` |
| `model not found` | Run `transcribe fetch-model` |
| `could not decode audio from …` | No audio stream, or a format ffmpeg can't read. Check with `ffprobe <file>`. |
| Transcript is mostly "Thank you" | The recording is mostly silence |
| Proper nouns consistently wrong | Expected on the smaller models; try `medium.en` |
| Very slow | A `large` model, or an Intel Mac with no Metal |

## Limitations

- `medium.en` is **English only**. The multilingual models drop the `.en` suffix;
  `transcribe fetch-model medium` gets one, but it's untested here.
- **No speaker labels.** The output is one undifferentiated stream of text, so a
  conversation between several people reads as one voice. This is the biggest gap.
- Tested only on Apple Silicon. Intel Macs need `TRANSCRIBE_BREW_BIN`, and the
  tests run the script against fakes, not the real tools.
- The model loads and unloads per invocation, costing about a second each time.
  Irrelevant for one long file, wasteful across many short ones.

## Possible next steps

- **Speaker labels.** `whisper.cpp` has `--tinydiarize` with the matching model, or
  `pyannote` as a separate pass. This is the change that would most improve the
  output for meetings.
- **A summarising pass.** Pipe the transcript straight into a local or API model for
  notes and action items, so the raw text isn't the deliverable.
- **Watch a folder.** Point it at the Zoom recordings directory and transcribe new
  meetings as they land.
- **Keep timestamps in the text output.** `-f srt` has them, `-f txt` doesn't, and
  the useful thing is often plain text that can still be traced back to the moment.
