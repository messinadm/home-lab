#!/usr/bin/env bats
# Unit tests for transcribe. Every outside tool is a fake from tests/fakes,
# so these run anywhere bash does, with no models and no network.

SCRIPT="$BATS_TEST_DIRNAME/../transcribe"
FAKES="$BATS_TEST_DIRNAME/fakes"

setup() {
	export TRANSCRIBE_BREW_BIN="$BATS_TEST_TMPDIR/bin"
	export TRANSCRIBE_CURL="$FAKES/curl"
	export TRANSCRIBE_MODEL_DIR="$BATS_TEST_TMPDIR/models"
	export TMPDIR="$BATS_TEST_TMPDIR/tmp"
	export FAKE_LOG="$BATS_TEST_TMPDIR/log"
	unset TRANSCRIBE_MODEL FAKE_FFPROBE_EMPTY FAKE_FFMPEG_FAIL FAKE_WHISPER_FAIL FAKE_CURL_FAIL

	mkdir -p "$TRANSCRIBE_BREW_BIN" "$TRANSCRIBE_MODEL_DIR" "$TMPDIR" "$BATS_TEST_TMPDIR/in"
	: > "$FAKE_LOG"
	local tool
	for tool in ffmpeg ffprobe whisper-cli; do
		ln -s "$FAKES/$tool" "$TRANSCRIBE_BREW_BIN/$tool"
	done
	printf 'model\n' > "$TRANSCRIBE_MODEL_DIR/ggml-medium.en.bin"
	printf 'audio\n' > "$BATS_TEST_TMPDIR/in/meeting.m4a"
	IN="$BATS_TEST_TMPDIR/in/meeting.m4a"
}

# The temp WAV must be gone after every run, success or failure.
assert_no_temp_files() {
	[[ -z "$(ls -A "$TMPDIR")" ]]
}

@test "no arguments prints usage" {
	run "$SCRIPT"
	[[ "$status" -eq 2 ]]
	[[ "$output" == *"Usage: transcribe"* ]]
}

@test "-h prints usage" {
	run "$SCRIPT" -h
	[[ "$status" -eq 2 ]]
	[[ "$output" == *"fetch-model [MODEL]"* ]]
}

@test "an unknown option prints usage" {
	run "$SCRIPT" -x "$IN"
	[[ "$status" -eq 2 ]]
	[[ "$output" == *"Usage: transcribe"* ]]
}

@test "an unknown format is refused" {
	run "$SCRIPT" -f doc "$IN"
	[[ "$status" -eq 1 ]]
	[[ "$output" == "transcribe: unknown format 'doc' (txt, srt, vtt, json)" ]]
}

@test "a missing tool names it and the fix" {
	rm "$TRANSCRIBE_BREW_BIN/whisper-cli"
	run "$SCRIPT" "$IN"
	[[ "$status" -eq 1 ]]
	[[ "$output" == *"missing $TRANSCRIBE_BREW_BIN/whisper-cli -- run: brew install ffmpeg whisper-cpp"* ]]
}

@test "a missing model says how to fetch it" {
	rm "$TRANSCRIBE_MODEL_DIR/ggml-medium.en.bin"
	run "$SCRIPT" "$IN"
	[[ "$status" -eq 1 ]]
	[[ "$output" == *"model not found"*"run: transcribe fetch-model medium.en"* ]]
}

@test "a missing input file is reported" {
	run "$SCRIPT" "$BATS_TEST_TMPDIR/in/nope.m4a"
	[[ "$status" -eq 1 ]]
	[[ "$output" == *"no such file: $BATS_TEST_TMPDIR/in/nope.m4a"* ]]
}

@test "transcribes to a text file beside the source" {
	run "$SCRIPT" "$IN"
	[[ "$status" -eq 0 ]]
	[[ "${lines[0]}" == "==> meeting.m4a (8s)" ]]
	[[ "${lines[1]}" == "    wrote $BATS_TEST_TMPDIR/in/meeting.txt" ]]
	[[ "$(cat "$BATS_TEST_TMPDIR/in/meeting.txt")" == "transcript" ]]
	assert_no_temp_files
}

@test "decodes to 16 kHz mono 16-bit WAV without reading stdin" {
	run "$SCRIPT" "$IN"
	[[ "$status" -eq 0 ]]
	grep -q -- "^ffmpeg -nostdin -y -loglevel error -i $IN -ar 16000 -ac 1 -c:a pcm_s16le $TMPDIR/transcribe\..*\.wav$" "$FAKE_LOG"
}

@test "runs whisper with the model, format and output prefix" {
	run "$SCRIPT" "$IN"
	[[ "$status" -eq 0 ]]
	grep -q -- "^whisper-cli -m $TRANSCRIBE_MODEL_DIR/ggml-medium.en.bin -f $TMPDIR/transcribe\..*\.wav -otxt -of $BATS_TEST_TMPDIR/in/meeting -pp$" "$FAKE_LOG"
}

@test "an unknown duration prints as zero" {
	export FAKE_FFPROBE_EMPTY=1
	run "$SCRIPT" "$IN"
	[[ "$status" -eq 0 ]]
	[[ "${lines[0]}" == "==> meeting.m4a (0s)" ]]
}

@test "-f picks the output format" {
	run "$SCRIPT" -f srt "$IN"
	[[ "$status" -eq 0 ]]
	[[ -f "$BATS_TEST_TMPDIR/in/meeting.srt" ]]
}

@test "-o writes into a directory it creates" {
	run "$SCRIPT" -o "$BATS_TEST_TMPDIR/out/notes" "$IN"
	[[ "$status" -eq 0 ]]
	[[ -f "$BATS_TEST_TMPDIR/out/notes/meeting.txt" ]]
	[[ ! -e "$BATS_TEST_TMPDIR/in/meeting.txt" ]]
}

@test "-o that can't be created is reported" {
	: > "$BATS_TEST_TMPDIR/file"
	run "$SCRIPT" -o "$BATS_TEST_TMPDIR/file/out" "$IN"
	[[ "$status" -eq 1 ]]
	[[ "$output" == *"could not create $BATS_TEST_TMPDIR/file/out"* ]]
}

@test "-m picks the model" {
	printf 'model\n' > "$TRANSCRIBE_MODEL_DIR/ggml-small.en.bin"
	run "$SCRIPT" -m small.en "$IN"
	[[ "$status" -eq 0 ]]
	grep -q -- "-m $TRANSCRIBE_MODEL_DIR/ggml-small.en.bin " "$FAKE_LOG"
}

@test "TRANSCRIBE_MODEL sets the default model" {
	export TRANSCRIBE_MODEL=small.en
	run "$SCRIPT" "$IN"
	[[ "$status" -eq 1 ]]
	[[ "$output" == *"ggml-small.en.bin"* ]]
}

@test "several files are transcribed in turn" {
	printf 'audio\n' > "$BATS_TEST_TMPDIR/in/talk.mp4"
	run "$SCRIPT" "$IN" "$BATS_TEST_TMPDIR/in/talk.mp4"
	[[ "$status" -eq 0 ]]
	[[ -f "$BATS_TEST_TMPDIR/in/meeting.txt" ]]
	[[ -f "$BATS_TEST_TMPDIR/in/talk.txt" ]]
	assert_no_temp_files
}

@test "a decode failure is reported and the temp WAV removed" {
	export FAKE_FFMPEG_FAIL=1
	run "$SCRIPT" "$IN"
	[[ "$status" -eq 1 ]]
	[[ "$output" == *"could not decode audio from meeting.m4a"* ]]
	assert_no_temp_files
}

@test "a transcription failure is reported and the temp WAV removed" {
	export FAKE_WHISPER_FAIL=1
	run "$SCRIPT" "$IN"
	[[ "$status" -eq 1 ]]
	[[ "$output" == *"transcription failed for meeting.m4a"* ]]
	assert_no_temp_files
}

@test "a temp file that can't be made is reported" {
	export TMPDIR="$BATS_TEST_TMPDIR/missing"
	run "$SCRIPT" "$IN"
	[[ "$status" -eq 1 ]]
	[[ "$output" == *"could not create temp file"* ]]
}

@test "fetch-model downloads the default model" {
	rm "$TRANSCRIBE_MODEL_DIR/ggml-medium.en.bin"
	run "$SCRIPT" fetch-model
	[[ "$status" -eq 0 ]]
	[[ "$output" == *"Saved $TRANSCRIBE_MODEL_DIR/ggml-medium.en.bin"* ]]
	grep -q "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-medium.en.bin$" "$FAKE_LOG"
	[[ "$(cat "$TRANSCRIBE_MODEL_DIR/ggml-medium.en.bin")" == "model" ]]
	[[ ! -e "$TRANSCRIBE_MODEL_DIR/ggml-medium.en.bin.part" ]]
}

@test "fetch-model takes a model name and creates the model directory" {
	export TRANSCRIBE_MODEL_DIR="$BATS_TEST_TMPDIR/new/models"
	run "$SCRIPT" fetch-model small.en
	[[ "$status" -eq 0 ]]
	[[ -f "$TRANSCRIBE_MODEL_DIR/ggml-small.en.bin" ]]
}

@test "fetch-model skips a model it already has" {
	run "$SCRIPT" fetch-model
	[[ "$status" -eq 0 ]]
	[[ "$output" == "Already have $TRANSCRIBE_MODEL_DIR/ggml-medium.en.bin" ]]
	! grep -q '^curl' "$FAKE_LOG"
}

@test "an interrupted download leaves nothing behind" {
	export FAKE_CURL_FAIL=1
	run "$SCRIPT" fetch-model small.en
	[[ "$status" -eq 1 ]]
	[[ "$output" == *"download failed for model 'small.en'"* ]]
	[[ -z "$(ls "$TRANSCRIBE_MODEL_DIR" | grep small)" ]]
}

@test "fetch-model reports a model directory it can't create" {
	: > "$BATS_TEST_TMPDIR/file"
	export TRANSCRIBE_MODEL_DIR="$BATS_TEST_TMPDIR/file/models"
	run "$SCRIPT" fetch-model
	[[ "$status" -eq 1 ]]
	[[ "$output" == *"could not create $TRANSCRIBE_MODEL_DIR"* ]]
}
