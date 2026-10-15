# Product

<!-- impeccable:product-schema 1 -->

## Platform

desktop

A native desktop window (macOS today), not a web page. No web, iOS or Android version.

## Stack

Python 3.12. UI: DearPyGui (chosen 2026-10-15 after trying a small piano prototype, since removed; plain pygame drawing is the fallback). Audio: pygame's mixer, playing sounds rendered by `synth.py` with numpy. No other runtime dependencies.

## Users

Music enthusiasts, the owner first, who use it equally as:
- a sketchpad for melodies and short pieces, played on the computer keyboard or with the mouse, and
- a workshop for short sound effects and jingles for their own games and code.

## Product Purpose

Play notes on 21 synthesized instruments, record a take, and turn it into something usable: a WAV file, Python or TypeScript code that rebuilds the sound, a MIDI file, or engraved sheet music (LilyPond). Success is going from an idea to a usable sound or score in a few minutes, without leaving the app.

## Positioning

Every sound is math in `synth.py`, with no samples. So what you hear, the WAV, and the exported code are the same sound. The exports are plain, editable text (note lists, `.ly` scores).

## Operating Context

- Played live, mostly from the computer keyboard: A–K for white keys, W–U for black keys, Z / X to change octave. Holding a key sustains the note.
- Typical loop: pick an instrument, play, Record, Stop, Play take, then export. Takes mix instruments and octaves.
- Exports go to `recordings/`. Sheet music assumes a fixed tempo (`BPM` in `app.py`).
- Used on a laptop.

## Capabilities and Constraints

- 21 instruments in five families (Keys & plucked, Strings, Woodwinds, Brass, Percussion), from `synth.FAMILIES`.
- 13 keys on screen (one octave plus the top C), shiftable from C1 to C7.
- Record / Stop, Play take, Trim start toggle, Save .wav, Export .py / .ts / .mid, Sheet music .ly (+ PDF when LilyPond is installed).
- The window must fit a 13" laptop screen (about 1280×800).
- Code must stay maintainable and easy to understand: a learner reads this code, and the README explains how it works.
- Not decided yet: a tempo / metronome control.

## Evidence on Hand

README.md (usage and how the sounds are made) and the working app (`app.py`). No logo, brand assets, or screenshots exist.

## Product Principles

1. Playing comes first: input latency and hold-to-sustain must never get worse.
2. What you hear is what you export.
3. Everything stays readable: plain-text exports and plain, commented code.
4. One small window that holds the whole loop: play, record, export.
