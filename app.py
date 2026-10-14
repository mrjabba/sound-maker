"""
app.py: the sound-maker window. It has a one-octave piano, an instrument picker,
a recorder, and export buttons.

Run:  python app.py

How it works:
* pygame opens the window, reads the mouse and keyboard, and plays the sounds.
* When you choose an instrument, each of its 13 notes is rendered once by synth.py,
  MAX_HOLD seconds long. These are cached in `sounds`.
* Pressing a key starts that note playing. Releasing the key fades it out over
  synth.RELEASE. Holding the key longer makes the note longer.
* While recording, each released note is added to `recording` as
  (start, midi, held, instrument). Pressing Stop turns it into `take`, the list
  every export is built from. If nothing was played, the previous take is kept.
"""
import time
from datetime import datetime
from pathlib import Path

import pygame

import synth

HERE = Path(__file__).resolve().parent
OUT = HERE / "recordings"

# ponytail: each note can sound for at most 8 s. Raise this if you hold notes longer
# (it costs memory: 8 s x 13 notes is ~4.5 MB per instrument).
MAX_HOLD = 8.0
LOW_NOTE = 60  # MIDI 60 = middle C (C4). Change it to move the octave up or down (+12 = one octave up).

# Computer keyboard -> half steps above LOW_NOTE. Most music apps use this layout:
# the home row plays the white keys and the row above plays the black keys.
#    W E   T Y U
#   A S D F G H J K
KEYMAP = {k: i for i, k in enumerate("awsedftgyhujk")}
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B", "C"]
BLACK = {1, 3, 6, 8, 10}  # Half steps that are black keys.

# Layout, in pixels.
W, H = 760, 360
WHITE_W, WHITE_H, BLACK_W, BLACK_H = 80, 200, 50, 125
KEYS_X, KEYS_Y = (W - 8 * WHITE_W) // 2, 70


# ---------------------------------------------------------------- key geometry
def key_rects():
    """A rectangle for each of the 13 keys, by half step. Black keys sit between white keys."""
    rects, white = {}, 0
    for i in range(13):
        if i in BLACK:
            # A black key is centered on the line between the white key before it and the next one.
            rects[i] = pygame.Rect(KEYS_X + white * WHITE_W - BLACK_W // 2, KEYS_Y, BLACK_W, BLACK_H)
        else:
            rects[i] = pygame.Rect(KEYS_X + white * WHITE_W, KEYS_Y, WHITE_W, WHITE_H)
            white += 1
    return rects


def key_at(pos, rects):
    """Which key is at the mouse position. Black keys are on top, so check them first."""
    for i in sorted(rects, key=lambda i: i not in BLACK):
        if rects[i].collidepoint(pos):
            return i
    return None


# ---------------------------------------------------------------- exports
def stamp():
    return datetime.now().strftime("take-%Y%m%d-%H%M%S")


def trim_start(take):
    """Shift every note earlier so the first one starts at 0 s, removing the silence
    between pressing Record and playing. Takes a take sorted by start time."""
    first = take[0][0]
    return [(at - first, midi, held, inst) for at, midi, held, inst in take]


def export_python(take, path):
    """Write a Python file that holds the note list. Running it with python writes the WAV."""
    rows = "\n".join(f"    ({at:.3f}, {midi}, {held:.3f}, {inst!r}),  # {NAMES[midi - LOW_NOTE]}" for at, midi, held, inst in take)
    path.write_text(f'''"""
Recorded with sound-maker on {datetime.now():%Y-%m-%d %H:%M}.

Each note is (start seconds, MIDI note, seconds held, instrument).
MIDI 60 is middle C, and each +1 is one half step up. Edit the list to change the song.
Run this file (with the sound-maker venv active) to write {path.stem}.wav next to it.
"""
import sys
from pathlib import Path

sys.path.insert(0, {str(HERE)!r})  # Folder that holds synth.py
from synth import render, save_wav

NOTES = [
{rows}
]

if __name__ == "__main__":
    save_wav(Path(__file__).with_suffix(".wav"), render(NOTES))
''')


def export_typescript(take, path):
    """Write a TypeScript module that plays the take using ts/instruments.ts (copy that file next to it)."""
    rows = "\n".join(
        f"  {{ at: {at:.3f}, midi: {midi}, held: {held:.3f}, instrument: '{inst}' }}, // {NAMES[midi - LOW_NOTE]}"
        for at, midi, held, inst in take
    )
    path.write_text(f"""// Recorded with sound-maker on {datetime.now():%Y-%m-%d %H:%M}.
// Needs instruments.ts from sound-maker/ts/ in the same folder.
// midi 60 is middle C, and each +1 is one half step up. at and held are in seconds.
import {{ renderWav, type Note }} from './instruments'

export const NOTES: Note[] = [
{rows}
]

// The song as WAV file bytes, built in memory (same format as sound-samples.ts).
export const {path.stem.replace('-', '_')}Sound = (): Uint8Array => renderWav(NOTES)
""")


# ---------------------------------------------------------------- app
def main():
    # Ask for exactly our sample rate in mono 16-bit. allowedchanges=0 tells SDL to
    # convert for the sound card itself, so our arrays always play at the right pitch.
    # buffer=256 samples (~12 ms) keeps the delay between keypress and sound short.
    pygame.mixer.pre_init(synth.SR, -16, 1, 256, allowedchanges=0)
    pygame.init()
    pygame.mixer.set_num_channels(32)  # Up to 32 notes at once, including release tails.
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("sound-maker")
    font = pygame.font.SysFont("helvetica", 16)
    small = pygame.font.SysFont("helvetica", 13)

    rects = key_rects()
    sounds = {}  # (instrument, midi) -> pygame Sound
    instrument = "piano"
    held = {}  # midi -> (channel, start time, instrument), for notes currently down
    take = []  # The last finished recording: (start, midi, held seconds, instrument)
    recording = []  # Notes of the recording in progress. Replaces `take` when you press Stop.
    rec_start = None  # time.time() when recording started, or None when not recording
    status = "Click keys or type A W S E D F T G Y H U J K."

    def load(name):
        """Render all 13 notes of an instrument and cache them as pygame Sounds."""
        for i in range(13):
            midi = LOW_NOTE + i
            if (name, midi) not in sounds:
                wave = synth.INSTRUMENTS[name](synth.hz(midi), MAX_HOLD) * synth.NOTE_GAIN
                sounds[name, midi] = pygame.sndarray.make_sound(synth.to_int16(wave))

    def note_on(i):
        midi = LOW_NOTE + i
        if midi not in held:  # Mouse and keyboard pressing the same key only start it once.
            held[midi] = (sounds[instrument, midi].play(), time.time(), instrument)

    def note_off(i):
        midi = LOW_NOTE + i
        if midi not in held:
            return
        channel, start, inst = held.pop(midi)
        channel.fadeout(int(synth.RELEASE * 1000))  # Same fade-out that synth.render() applies.
        if rec_start is not None and start >= rec_start:
            recording.append((start - rec_start, midi, time.time() - start, inst))

    # Buttons: (label, rectangle). Labels for some of them change while the app runs.
    inst_buttons = {name: pygame.Rect(KEYS_X + n * 128, 20, 120, 32) for n, name in enumerate(synth.INSTRUMENTS)}
    actions = ["record", "play", "wav", "python", "typescript"]
    action_buttons = {a: pygame.Rect(KEYS_X + n * 128, 290, 120, 32) for n, a in enumerate(actions)}
    action_buttons["trim"] = pygame.Rect(KEYS_X + 4 * 128, 328, 120, 24)  # Under Export .ts
    trim = True  # Start the first note at 0 s when playing back or exporting.

    def action(a):
        nonlocal rec_start, take, recording, status, trim
        if a == "trim":
            trim = not trim
            status = "The first note will start at 0 s." if trim else "Keeping the silence before the first note."
            return
        if a == "record":
            if rec_start is None:
                recording, rec_start = [], time.time()
                status = "Recording... play something, then press Stop."
            else:
                rec_start = None
                if recording:
                    take = recording
                    status = f"Recorded {len(take)} notes."
                else:  # Record then Stop without playing: you changed your mind, so keep the old take.
                    status = "Stopped. Nothing was played, so the previous take is kept."
            return
        if not take:
            status = "Nothing recorded yet. Press Record first."
            return
        take.sort()  # Notes are saved when released, so put them back in start order.
        notes = trim_start(take) if trim else take  # A trimmed copy. The recording itself is unchanged.
        if a == "play":
            pygame.sndarray.make_sound(synth.to_int16(synth.render(notes))).play()
            status = "Playing the take."
            return
        OUT.mkdir(exist_ok=True)
        name = stamp()
        if a == "wav":
            path = OUT / f"{name}.wav"
            synth.save_wav(path, synth.render(notes))
        elif a == "python":
            path = OUT / f"{name.replace('-', '_')}.py"  # Underscores so it can be imported.
            export_python(notes, path)
        else:
            path = OUT / f"{name}.ts"
            export_typescript(notes, path)
        status = f"Saved {path.relative_to(HERE)}"

    load(instrument)
    clock = pygame.time.Clock()
    mouse_key = None  # The piano key the mouse is holding down, if any.
    while True:
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                return
            # pygame doesn't repeat KEYDOWN while a key is held (unless set_repeat is
            # turned on), so holding a key gives one down and one up.
            elif e.type == pygame.KEYDOWN and e.unicode.lower() in KEYMAP:
                note_on(KEYMAP[e.unicode.lower()])
            elif e.type == pygame.KEYUP:
                # e.unicode is not reliable on KEYUP, so use the key's name instead.
                k = pygame.key.name(e.key)
                if k in KEYMAP:
                    note_off(KEYMAP[k])
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                mouse_key = key_at(e.pos, rects)
                if mouse_key is not None:
                    note_on(mouse_key)
                for name, r in inst_buttons.items():
                    if r.collidepoint(e.pos):
                        status = f"Loading {name}..."
                        draw(screen, font, small, rects, held, inst_buttons, action_buttons, instrument, rec_start, trim, status)
                        load(name)
                        instrument, status = name, f"Instrument: {name}"
                for a, r in action_buttons.items():
                    if r.collidepoint(e.pos):
                        action(a)
            elif e.type == pygame.MOUSEBUTTONUP and e.button == 1 and mouse_key is not None:
                note_off(mouse_key)
                mouse_key = None
        draw(screen, font, small, rects, held, inst_buttons, action_buttons, instrument, rec_start, trim, status)
        clock.tick(60)


def draw(screen, font, small, rects, held, inst_buttons, action_buttons, instrument, rec_start, trim, status):
    """Redraw the whole window. Called about 60 times a second."""
    screen.fill((34, 36, 42))
    letters = "awsedftgyhujk"

    for name, r in inst_buttons.items():
        button(screen, font, r, name.title(), active=name == instrument)

    # White keys first, then black keys on top. A pressed key is drawn highlighted.
    for black in (False, True):
        for i, r in rects.items():
            if (i in BLACK) != black:
                continue
            down = LOW_NOTE + i in held
            color = (120, 170, 255) if down else ((20, 20, 24) if black else (245, 245, 240))
            pygame.draw.rect(screen, color, r, border_radius=4)
            pygame.draw.rect(screen, (60, 60, 60), r, 1, border_radius=4)
            ink = (200, 200, 200) if black and not down else (40, 40, 40)
            label = font.render(NAMES[i], True, ink)  # Note name
            screen.blit(label, label.get_rect(midbottom=(r.centerx, r.bottom - 8)))
            hint = small.render(letters[i].upper(), True, (130, 130, 140))  # Computer key that plays it
            screen.blit(hint, hint.get_rect(midbottom=(r.centerx, r.bottom - 30)))

    labels = {
        "record": "Stop" if rec_start is not None else "Record",
        "play": "Play take",
        "wav": "Save .wav",
        "python": "Export .py",
        "typescript": "Export .ts",
        "trim": f"Trim start: {'on' if trim else 'off'}",
    }
    for a, r in action_buttons.items():
        button(screen, small if a == "trim" else font, r, labels[a], active=(a == "record" and rec_start is not None) or (a == "trim" and trim), red=a == "record")

    screen.blit(small.render(status, True, (200, 200, 200)), (KEYS_X, 334))
    pygame.display.flip()


def button(screen, font, rect, text, active=False, red=False):
    color = ((200, 60, 60) if red else (70, 110, 200)) if active else (60, 63, 72)
    pygame.draw.rect(screen, color, rect, border_radius=6)
    label = font.render(text, True, (240, 240, 240))
    screen.blit(label, label.get_rect(center=rect.center))


if __name__ == "__main__":
    main()
