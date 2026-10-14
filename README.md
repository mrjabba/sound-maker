# sound-maker

A small desktop piano for making sounds and short songs for games and other code.
Play notes with the mouse or keyboard, record them, and then:

- **Save .wav**: a normal audio file, for example for `weird-austin/src/main/resources/audio/`.
- **Export .py**: a Python file holding the note list. Run it to rebuild the WAV, edit the notes, or paste them into `gen_audio.py`.
- **Export .ts**: a TypeScript module that builds the same sound in memory, like `sound-samples.ts`.

Every sound is made from math in `synth.py`. There are no audio sample files. So what you play, the WAV, and the exported code all sound the same.

```
sound-maker/
  app.py            the window: piano, instrument buttons, record and export
  synth.py          the instruments and the song renderer (no UI, so other scripts can import it)
  ts/instruments.ts the same instruments in TypeScript, used by .ts exports
  requirements.txt  the Python packages it needs (numpy, pygame)
  recordings/       where saves and exports go (created on first save, ignored by git)
```

---

## 1. Setup (one time)

Use your own Python from pyenv plus a **virtual environment** (venv), so nothing is installed into the macOS system Python.

> **What a venv is:** a folder (`.venv/`) with its own copy of Python and its own installed packages.
> "Activating" it changes your shell so that `python` and `pip` point into that folder.
> Delete the folder and everything it installed is gone. Nothing else on your machine changes.

```bash
cd ~/dev/sound-maker

# 1. Pick the Python version. The repo includes a .python-version file (3.12.2),
#    and pyenv reads it automatically whenever you're in this folder. Check it:
pyenv version            # -> 3.12.2 (set by .../sound-maker/.python-version)
python --version         # -> Python 3.12.2
#    If that version isn't installed:  pyenv install 3.12.2
#    To change version:                pyenv local 3.13.1   (rewrites .python-version)

# 2. Create the venv. Only needed once. It makes the .venv/ folder.
python -m venv .venv

# 3. Activate it. Do this in every new terminal before working on the project.
source .venv/bin/activate
#    Your prompt now starts with (.venv). Check: `which python` -> .../sound-maker/.venv/bin/python

# 4. Install the packages into the venv
pip install -r requirements.txt
```

**Every time after that:**

```bash
cd ~/dev/sound-maker
source .venv/bin/activate
python app.py
# when you're done, `deactivate` (or just close the terminal)
```

**Python cheat sheet**

| Task | Command |
|---|---|
| Run without activating | `.venv/bin/python app.py` |
| Add a package | `pip install <name>` then `pip freeze > requirements.txt` |
| See installed packages | `pip list` |
| Start the venv over (broken or new Python version) | `rm -rf .venv` then repeat steps 2–4 |
| Self-check the instruments | `python synth.py` (prints each pitch and `ok`) |
| Try code interactively | `python` then `>>> import synth` (`exit()` to quit) |

> You don't need tkinter. Your pyenv Pythons weren't built with it, which is why this app
> uses pygame, a normal pip package that includes everything it needs.

---

## 2. Using the app

```bash
python app.py
```

- **Play:** click the keys, or type on the computer keyboard. The key letters are printed on the piano keys:

  ```
     W E   T Y U          C# D#    F# G# A#
    A S D F G H J K      C  D  E  F  G  A  B  C
  ```
- **Hold** a key to make the note longer. Releasing it fades the note out over 0.15 s. Piano and guitar die away on their own, like real ones. Trumpet, flute and organ keep sounding as long as you hold the key (up to 8 s).
- **Instrument buttons:** Piano, Guitar, Trumpet, Flute, Organ. Switching only changes notes you play after that, so one take can mix instruments.
- **Record** starts a new take, and **Stop** ends it. Only notes played between them are saved. If you press Record and then Stop without playing anything, the previous take is kept, so you can back out safely.
- **Play take** plays the recording back.
- **Trim start** (on by default) moves the take so the first note starts at 0 s, which removes the silence between pressing Record and playing. Sound effects then start the moment the game calls them. It changes only playback and exports, never the recording, so you can turn it off and export again with the original timing.
- **Save .wav / Export .py / Export .ts** write to `recordings/take-<date>-<time>.*`.

The recording is just a list of notes:

```python
(start_seconds, midi_note, held_seconds, instrument)
(0.019, 60, 0.231, 'piano')    # middle C, 0.02 s in, held 0.23 s
```

MIDI note numbers: 60 is middle C, and each +1 is one half step (one piano key, black or white), so 72 is the next C up.
Exports are plain text, so you can clean up timing, change notes, or loop sections by editing the list.

---

## 3. Using the exports

### a) In Python: rebuild the WAV

```bash
source .venv/bin/activate
python recordings/take_20261014_090513.py    # writes take_20261014_090513.wav next to it
```

The exported file imports `synth.py` from this folder (its path is written into the file).

### b) In weird-austin's `gen_audio.py`

`gen_audio.py` also works at 22050 Hz with numpy, and its `save(name, make)` takes a function that returns samples. So:

1. Copy `synth.py` into `weird-austin/tools/`.
2. In `gen_audio.py`:

   ```python
   from synth import render

   MY_JINGLE = [            # pasted from an exported .py
       (0.000, 60, 0.231, "piano"),
       (0.250, 64, 0.231, "piano"),
   ]

   save("jingle", lambda: render(MY_JINGLE))   # -> src/main/resources/audio/jingle.wav
   ```

The instruments use the same `fn(freq, seconds)` signature as `gen_audio.py`'s `voice()`, so you can also use them directly:
`voice(buf, melody, beat, 0, synth.flute, 0.3)`.

### c) In TypeScript (like `sound-samples.ts`)

1. Copy `ts/instruments.ts` next to the exported `take-....ts`.
2. Use it:

   ```ts
   import { take_20261014_090513Sound } from './take-20261014-090513'
   const bytes: Uint8Array = take_20261014_090513Sound()   // WAV bytes, built in memory
   ```

   Or write notes by hand:

   ```ts
   import { renderWav } from './instruments'
   const ding = renderWav([
     { at: 0,    midi: 72, held: 0.1, instrument: 'piano' },
     { at: 0.12, midi: 79, held: 0.4, instrument: 'piano' },
   ])
   ```

The bytes are a complete 16-bit mono WAV, the same format as `pcm()` in `sound-samples.ts`.
In a browser you can play them with `new Audio(URL.createObjectURL(new Blob([bytes], { type: 'audio/wav' }))).play()`.
Recent Node can run `.ts` files directly (`node file.ts`). In that case write the import as `'./instruments.ts'`.

---

## 4. How the sounds are made (for tweaking)

A sound is an array of numbers between -1 and 1, 22050 of them per second (`SR`).
A speaker cone moves out and in following those numbers. A pattern that repeats 440
times a second is heard as the note A.

Each instrument in `synth.py` is a short function, `fn(freq, seconds) -> array`:

| Instrument | Technique | Things to try changing |
|---|---|---|
| piano | adds 7 harmonics (multiples of the note's frequency), with the high ones fading faster | the fade `1.6 + k * 1.4` (smaller = rings longer) |
| guitar | **Karplus-Strong**: a burst of noise that loops and gets smoothed each time round | `0.996` (closer to 1 = sustains longer), the `0.7`/`0.3` mix of triangle shape and noise |
| trumpet | sawtooth harmonics that "open up" over 80 ms, plus vibrato | `brightness` (higher = brassier), vibrato depth `0.006` |
| flute | sine wave plus a little breath noise | `breathiness` |
| organ | fixed sine "drawbars" plus a Leslie wobble | the `drawbars` list |

Vocabulary:
- **Harmonics:** extra sine waves at 2×, 3×, 4×... the note's frequency. Their mix gives each instrument its *timbre* (its tone color).
- **Envelope:** volume over time. A sharp *attack* sounds plucked or struck, and a slow one sounds blown or bowed.
- **Vibrato:** a small, steady wobble in pitch (about 5 times a second).

**Adding an instrument:** write `def kazoo(freq, seconds): ...` in `synth.py` and add it to `INSTRUMENTS`.
A button appears in the app automatically. To use it from `.ts` exports too, port it into `ts/instruments.ts`.
Run `python synth.py` after any change to check the instruments are still in tune and not too loud.

**Other knobs:** `LOW_NOTE` in `app.py` moves the keyboard by octaves (+12 = one up). `NOTE_GAIN` and `RELEASE` in `synth.py` set the note volume and the fade-out time.

---

## Known limits

- One octave, no octave-shift key. Change `LOW_NOTE` or ask for octave keys.
- Each note can sound for at most 8 s (`MAX_HOLD` in `app.py`).
- The guitar can be up to ~10 cents off pitch on high notes. You'd only notice next to another instrument.
- These are synthesized sounds, not recordings of real instruments. Real-instrument sounds would need SoundFont playback (for example fluidsynth). That's a bigger change, and code exports would no longer match exactly.
