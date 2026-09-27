# AGENTS.md

Small, unrelated projects that don't need their own repo.

## Layout

- Projects live in `<category>/<name>-NN/`, for example `linux/voice-dictation-00/`. A new take on the same idea gets the next number instead of replacing the old one.
- Every project has a row in the table in the top-level `README.md`. Adding, renaming, or retiring a project means updating that row.

## Project READMEs

Write the result, not the history. Sections, in order:

Goal, What it uses, How it works, Requirements, Setup, Daily use, Things we struggled with, Troubleshooting, Limitations, Possible next steps.

- Setup is numbered steps that work on the tested system.
- "Things we struggled with" gives the problem and what to know, not the story of how it was found.
- Ideas that weren't built go in "Possible next steps".

## Privacy

This repo may be public. Never commit usernames or home paths (write `/home/<you>`), hardware IDs such as Bluetooth addresses, or anything dictated.

## Scripts

- Bash: tabs, `[[ ]]`, quoted expansions, no `set -e`, fixed paths to tools.
- If a script is installed outside the repo (for example `~/.local/bin`), keep the repo copy identical.

## Git

- Commit with a subject that says what changed and a body that says why.
- Don't push without asking.
