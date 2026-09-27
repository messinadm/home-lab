# AGENTS.md

Small, unrelated projects that don't need their own repo.

## Layout

- Projects live in `<category>/<name>-NN/`, for example `linux/voice-dictation-00/`. A new take on the same idea gets the next number instead of replacing the old one.
- Every project has a row in the table in the top-level `README.md`. Adding, renaming, or retiring a project means updating that row.

## Project READMEs

Write the result, not the history. Each README stands alone: it may point to a related project at the top, but someone who never ran that project must be able to follow it. Sections, in order:

Goal, What it uses, How it works, Requirements, Setup, Daily use, Things we struggled with, Troubleshooting, Limitations, Possible next steps.

- Setup is numbered steps that work on the tested system.
- "Things we struggled with" gives the problem and what to know, not the story of how it was found.
- Ideas that weren't built go in "Possible next steps".

## Privacy

This repo may be public. Never commit usernames or home paths (write `/home/<you>`), hardware IDs such as Bluetooth addresses, or anything dictated.

## Code and tests

- Any code needs unit tests that run on the build, with at least 90% coverage.
- Python projects are uv projects: `pyproject.toml`, `uv.lock`, and `.python-version`. `uv run pytest` runs the tests and enforces the coverage floor.
- Tests use fakes for hardware and outside tools. Tests that need real hardware are marked and skipped unless asked for, because CI has none.
- Each project with code has its own workflow, `.github/workflows/<project>.yml`, triggered only by changes to that project's directory or that workflow file.
- Bash: tabs, `[[ ]]`, quoted expansions, no `set -e`, fixed paths to tools.
- If code is installed outside the repo (for example `~/.local/bin`), keep the repo copy identical.

## Git

- Commit with a subject that says what changed and a body that says why.
- Don't push without asking.
