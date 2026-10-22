"""
app.py: the sound-maker window. A piano roll: every note you play rises from its
key as a bar, as tall as you held it, in its instrument family's color.
Across the top: record, play, the instrument families and the exports.

Run:  python app.py

How it works:
* DearPyGui opens the window and reads the mouse and keyboard. pygame's mixer
  plays the sounds (pygame doesn't open a window).
* Every frame, draw() clears the canvas and paints the whole window again from
  `s` (the app state), like a game loop. Each clickable thing it paints is added
  to `hits` with what it does, so a click just looks up what's under the mouse.
* When you choose an instrument, each of its 13 notes is rendered once by synth.py,
  MAX_HOLD seconds long, and cached in `sounds`.
* Pressing a key starts that note playing and adds a bar to `s.bars`. Releasing the
  key fades the note out over synth.RELEASE and ends the bar.
* While recording, each released note is added to `s.recording` as
  (start, midi, held, instrument). Pressing Stop turns it into `s.take`, the list
  every export is built from. If nothing was played, the previous take is kept.
* Tempo: s.bpm sets the metronome and the beat grid. Recording always starts with a
  one-bar count-in, so a take starts on beat 1 and remembers its tempo (s.take_bpm).
  Export .mid and Score (.ly) come from notation.py at that tempo.
* The metronome is one bar of clicks (synth.metronome_bar) looped on its own mixer
  channel, so its timing is exact instead of depending on the frame rate.
* A MIDI keyboard (pygame.midi) is connected at startup if one is plugged in, and the
  MIDI button connects or disconnects it. It plays every key it has, not just the 13
  on screen; notes outside them sound and record but aren't drawn.
"""
import math
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import dearpygui.dearpygui as dpg
import numpy as np
import pygame
import pygame.midi

import notation
import synth

HERE = Path(__file__).resolve().parent
OUT = HERE / "recordings"
FONTS = HERE / "fonts"

# ponytail: each note can sound for at most 8 s. Raise this if you hold notes longer
# (it costs memory: 8 s x 13 notes is ~4.5 MB per instrument).
MAX_HOLD = 8.0
LOW_NOTE = 60  # The leftmost key when the app starts. MIDI 60 = middle C (C4).
DEFAULT_BPM, MIN_BPM, MAX_BPM, BPM_STEP = 100, 40, 240, 5
# ponytail: always 4/4. Other time signatures would need this in notation.py too.
BEATS_PER_BAR = 4
LOWEST, HIGHEST = 24, 84  # How far the octave buttons can shift the leftmost key: C1 to C6 (the top key reaches C7).

# Computer keyboard -> half steps above the leftmost key. Most music apps use this layout:
# the home row plays the white keys and the row above plays the black keys.
#    W E   T Y U
#   A S D F G H J K
LETTERS = "awsedftgyhujk"
NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B", "C"]
BLACK = {1, 3, 6, 8, 10}  # Half steps that are black keys.


def note_name(midi):
    """60 -> "C4", 61 -> "C#4". The octave number goes up by one at each C."""
    return f"{NAMES[midi % 12]}{midi // 12 - 1}"


def pretty(name):
    """"french_horn" -> "French Horn"."""
    return name.replace("_", " ").title()


# ---------------------------------------------------------------- look
# Colors (R, G, B). Graphite greys for the window, and one color per instrument
# family. The family colors are the only colors: tabs, selected instrument, bars, lit keys.
GROUND = (23, 25, 29)  # The roll and the window.
PANEL = (29, 32, 37)  # The top strip and the status bar.
LANE = (35, 38, 44)  # Buttons.
BLACK_LANE = (19, 21, 25)  # The strip of roll above each black key.
LINE = (44, 48, 56)  # Lane edges and the beat grid.
BAR_LINE = (64, 69, 80)  # Every fourth beat (a bar of 4/4).
INK = (232, 230, 225)  # Text.
DIM = (138, 141, 150)  # Secondary text.
FAINT = (82, 86, 96)  # Text on controls that can't be used right now.
IVORY, EBONY = (232, 230, 225), (12, 13, 16)  # Piano keys.
REC_RED = (255, 90, 78)  # The record light. Transport red, not a family color.
FAMILY_COLORS = {
    "Keys & plucked": (242, 165, 65),  # amber
    "Strings": (228, 87, 46),  # vermilion
    "Woodwinds": (79, 176, 198),  # teal
    "Brass": (201, 180, 88),  # brass gold
    "Percussion": (143, 191, 90),  # green
}
FAMILY_LABELS = {"Keys & plucked": "Keys", "Woodwinds": "Winds", "Percussion": "Perc"}  # Short tab names.

# Layout, in pixels. Boxes are (left, top, right, bottom).
W, H = 1000, 720
TOP_H = 64  # The top strip.
ROW = (0, TOP_H, W, TOP_H + 44)  # The instrument row.
KEYS_TOP, KEYS_BOTTOM = 536, 688
ROLL = (16, ROW[3], W - 16, KEYS_TOP)  # The roll sits directly above the keys.
WHITE_W = (ROLL[2] - ROLL[0]) / 8
BLACK_W, BLACK_H = WHITE_W * 0.6, 94
SPEED = 120  # How fast bars rise, in pixels per second.
EXPORTS = {"wav": "WAV", "py": "PY", "ts": "TS", "midi": "MID", "lily": "SCORE"}
HELP = {  # Shown in the status bar while the mouse is over a control.
    "record": "Record a new take. Press again to stop.",
    "play": "Play the take back.",
    "wav": "Save the take as a WAV audio file.",
    "py": "Export the take as Python code that rebuilds the sound.",
    "ts": "Export the take as TypeScript code that rebuilds the sound.",
    "midi": "Export the take as a MIDI file.",
    "lily": "Export the take as sheet music (LilyPond .ly, plus a PDF if LilyPond is installed).",
    "trim": "Trim: start the take at its first note. MIDI and Score keep beat 1 and drop only whole bars.",
    "metronome": "Metronome: a click on every beat, higher on beat 1 (M). Recording always counts in one bar.",
    "slower": "Slower ([).",
    "faster": "Faster (]).",
    "midi_in": "MIDI keyboard: connect (finds one plugged in after launch) or disconnect.",
    "down": "Octave down (Z).",
    "up": "Octave up (X).",
}


def family_of(instrument):
    return next(f for f, names in synth.FAMILIES.items() if instrument in names)


def key_boxes():
    """A box for each of the 13 piano keys, by half step. Black keys sit between white keys."""
    boxes, white = {}, 0
    for i in range(13):
        x = ROLL[0] + white * WHITE_W
        if i in BLACK:
            boxes[i] = (x - BLACK_W / 2, KEYS_TOP, x + BLACK_W / 2, KEYS_TOP + BLACK_H)
        else:
            boxes[i] = (x, KEYS_TOP, x + WHITE_W, KEYS_BOTTOM)
            white += 1
    return boxes


KEY_BOXES = key_boxes()


def inside(box, pos):
    return box[0] <= pos[0] < box[2] and box[1] <= pos[1] < box[3]


# ---------------------------------------------------------------- exports
def stamp():
    return datetime.now().strftime("take-%Y%m%d-%H%M%S")


def trim_start(take):
    """Shift every note earlier so the first one starts at 0 s, removing the silence
    between pressing Record and playing. Takes a take sorted by start time."""
    first = take[0][0]
    return [(at - first, midi, held, inst) for at, midi, held, inst in take]


def bar_seconds(bpm):
    return BEATS_PER_BAR * 60 / bpm


def trim_to_bar(take, bpm):
    """Like trim_start, but only removes whole bars, so beat 1 stays beat 1 in MIDI and
    sheet music. A take starts on a downbeat (after the count-in), so its times are
    already counted in bars. A first note played a little early still counts in its bar."""
    bar, first = bar_seconds(bpm), take[0][0]
    shift = min(first, (first + bar / BEATS_PER_BAR / 2) // bar * bar)
    return [(at - shift, midi, held, inst) for at, midi, held, inst in take]


def export_python(take, path):
    """Write a Python file that holds the note list. Running it with python writes the WAV."""
    rows = "\n".join(f"    ({at:.3f}, {midi}, {held:.3f}, {inst!r}),  # {note_name(midi)}" for at, midi, held, inst in take)
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
        f"  {{ at: {at:.3f}, midi: {midi}, held: {held:.3f}, instrument: '{inst}' }}, // {note_name(midi)}"
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


# ---------------------------------------------------------------- state and actions
s = SimpleNamespace(
    instrument="piano",
    low=LOW_NOTE,  # MIDI note of the leftmost key. The octave buttons move it by 12.
    held={},  # key -> (midi, channel, start time, instrument, bar), for keys currently down.
    # A key is 0-12 for the keys on screen, or ("midi", note) for the MIDI keyboard.
    bars=[],  # Bars in the roll: [key, start time, end time or None while held, color]
    take=[],  # The last finished recording: (start, midi, held seconds, instrument)
    recording=[],  # Notes of the recording in progress. Replaces `take` when you press Stop.
    rec_start=None,  # When recording starts (after the count-in), or None when not recording
    bpm=DEFAULT_BPM,  # Tempo for the metronome and the next recording.
    take_bpm=DEFAULT_BPM,  # The tempo the take was recorded at. MIDI and Score use it.
    metronome=False,  # Whether the click keeps going after the count-in.
    beat0=time.time(),  # A downbeat that the beat grid and the click count from.
    click_bpm=DEFAULT_BPM,  # The tempo the click (and the grid) is running at.
    trim=True,  # Start the first note at 0 s when playing back or exporting.
    saved=set(),  # Exports saved from the current take ("wav", "midi", ...), shown checked.
    last=None,  # (midi, seconds held) of the last note, for the readout.
    mouse_key=None,  # The piano key the mouse is holding down, if any.
    status="Play with the mouse, or the keys A W S E D F T G Y H U J K. Z / X change octave, M the metronome.",
    hint=None,  # Help for the control under the mouse, shown in the status bar instead of `status`.
    midi_in=None,  # The MIDI keyboard's pygame.midi.Input, or None when not connected.
    later=None,  # A slow job to run after the next frame is shown, so its "working" message appears first.
)
sounds = {}  # (instrument, midi) -> pygame Sound
hits = []  # (box, action) for everything clickable in the last frame


def sound(name, midi):
    """One note as a pygame Sound, rendered the first time it's asked for and then cached."""
    if (name, midi) not in sounds:
        wave = synth.INSTRUMENTS[name](synth.hz(midi), MAX_HOLD) * synth.NOTE_GAIN
        sounds[name, midi] = pygame.sndarray.make_sound(synth.to_int16(wave))
    return sounds[name, midi]


def load(name):
    """Render the 13 notes of an instrument in the current octave. Octaves you've already
    visited are cached, so going back is instant."""
    for i in range(13):
        sound(name, s.low + i)


def note_on(key, midi):
    if key not in s.held:  # Key-press events repeat while a key is held; only start the note once.
        now = time.time()
        # ponytail: a MIDI note outside the cached octave renders on first press (~10 ms hitch).
        channel = sound(s.instrument, midi).play()
        bar = [midi - s.low, now, None, FAMILY_COLORS[family_of(s.instrument)]]
        if 0 <= midi - s.low <= 12:  # Only notes on the keys on screen get a bar.
            s.bars.append(bar)
        s.held[key] = (midi, channel, now, s.instrument, bar)


def note_off(key):
    # Held notes are stored by key, along with their midi number. If you change octave
    # while holding a key, releasing it still stops the note that's actually playing.
    if key not in s.held:
        return
    midi, channel, start, inst, bar = s.held.pop(key)
    channel.fadeout(int(synth.RELEASE * 1000))  # Same fade-out that synth.render() applies.
    bar[2] = time.time()
    s.last = (midi, bar[2] - start)
    # A note counts if it starts after the count-in, or up to half a beat before it:
    # players often hit beat 1 a little early. Early notes are moved to 0 s.
    if s.rec_start is not None and start >= s.rec_start - 30 / s.bpm:
        s.recording.append((max(0.0, start - s.rec_start), midi, bar[2] - start, inst))


def choose(name):
    """Switch instrument. Rendering takes a moment, so say so first and load after the frame."""
    if name == s.instrument:
        return

    def switch():
        load(name)
        s.instrument, s.status = name, pretty(name)

    s.status = f"Loading {pretty(name)}..."
    s.later = switch


def step_instrument(by):
    names = list(synth.INSTRUMENTS)
    choose(names[(names.index(s.instrument) + by) % len(names)])


def shift_octave(by):
    s.low = min(HIGHEST, max(LOWEST, s.low + 12 * by))
    load(s.instrument)
    s.status = f"Keys now play {note_name(s.low)} to {note_name(s.low + 12)}."


def toggle_midi():
    """Disconnect the MIDI keyboard, or look for one and connect it."""
    if s.midi_in:
        for key in [k for k in s.held if isinstance(k, tuple)]:
            note_off(key)  # Don't leave its notes hanging.
        s.midi_in.close()
        s.midi_in, s.status = None, "MIDI keyboard disconnected."
        return
    pygame.midi.quit()  # pygame.midi only lists devices at init, so start over to see new ones.
    pygame.midi.init()
    device = pygame.midi.get_default_input_id()
    if device < 0:
        s.status = "No MIDI keyboard found. Plug one in and press MIDI."
        return
    s.midi_in = pygame.midi.Input(device)
    s.status = f"MIDI keyboard: {pygame.midi.get_device_info(device)[1].decode()}."


def read_midi():
    """Play the notes the MIDI keyboard sent since the last frame. Other messages
    (clock, knobs, pedals) are ignored."""
    # ponytail: read once a frame, so up to ~16 ms of extra delay. A thread could cut it.
    while s.midi_in and s.midi_in.poll():
        for (status, note, velocity, _), _ in s.midi_in.read(64):
            kind = status & 0xF0
            if kind == 0x90 and velocity:  # Note on.
                note_on(("midi", note), note)
            elif kind in (0x80, 0x90):  # Note off, or note on with velocity 0 (which means off).
                note_off(("midi", note))


def start_click(loop, new_downbeat, bpm):
    """Start the click on channel 0: looping when the metronome is on, or a single bar
    (a count-in). new_downbeat makes now beat 1; otherwise it joins in step with the grid."""
    now = time.time()
    if new_downbeat:
        s.beat0 = now
    s.click_bpm = bpm
    bar = synth.metronome_bar(bpm, BEATS_PER_BAR) * 0.6
    offset = int((now - s.beat0) % bar_seconds(bpm) * synth.SR)  # How far into the bar we are.
    sound = pygame.sndarray.make_sound(synth.to_int16(np.roll(bar, -offset)))
    pygame.mixer.Channel(0).play(sound, loops=-1 if loop else 0)


def toggle_metronome():
    s.metronome = not s.metronome
    if s.metronome:
        start_click(loop=True, new_downbeat=False, bpm=s.bpm)
        s.status = f"Metronome on, {s.bpm} BPM."
    else:
        pygame.mixer.Channel(0).stop()
        s.status = "Metronome off. Recording still counts in one bar."


def change_tempo(by):
    if s.rec_start is not None:
        s.status = "Press Stop before changing the tempo."
        return
    s.bpm = min(MAX_BPM, max(MIN_BPM, s.bpm + by))
    if s.metronome:
        start_click(loop=True, new_downbeat=True, bpm=s.bpm)
    else:
        s.beat0, s.click_bpm = time.time(), s.bpm  # The grid follows the new tempo.
    s.status = f"Tempo {s.bpm} BPM."


def record():
    if s.rec_start is None:
        start_click(loop=s.metronome, new_downbeat=True, bpm=s.bpm)  # One bar of count-in clicks.
        s.recording, s.rec_start = [], s.beat0 + bar_seconds(s.bpm)
        s.status = "Count-in, then recording starts on beat 1. Press Stop when you're done."
        return
    s.rec_start = None
    if not s.metronome:
        pygame.mixer.Channel(0).stop()  # In case Stop came during the count-in.
    if s.recording:
        s.take, s.saved, s.take_bpm = sorted(s.recording), set(), s.bpm  # Notes are saved when released, so sort by start.
        s.status = f"Recorded {len(s.take)} notes."
    else:  # Record then Stop without playing: you changed your mind, so keep the old take.
        s.status = "Nothing was played, so the previous take is kept."


def take_notes(musical=False):
    """The take as played or exported. With Trim on, it starts at its first note; musical
    (MIDI, Score, playing along with the metronome) drops only whole bars, so the beats
    stay where they were played. The recording itself is unchanged."""
    if not s.trim:
        return s.take
    return trim_to_bar(s.take, s.take_bpm) if musical else trim_start(s.take)


def play():
    if s.rec_start is not None:
        s.status = "Press Stop before playing the take."
        return
    if not s.take:
        s.status = "Nothing recorded yet. Press Record first."
        return
    notes = take_notes(musical=s.metronome)
    if s.metronome:  # Click along at the take's tempo, starting on its beat 1.
        start_click(loop=True, new_downbeat=True, bpm=s.take_bpm)
    pygame.sndarray.make_sound(synth.to_int16(synth.render(notes))).play()
    # Show the take rising through the roll as it plays. Notes outside the keys on screen aren't drawn.
    t0 = time.time()
    for at, midi, held, inst in notes:
        if 0 <= midi - s.low <= 12:
            s.bars.append([midi - s.low, t0 + at, t0 + at + held, FAMILY_COLORS[family_of(inst)]])
    s.status = "Playing the take."


def toggle_trim():
    s.trim = not s.trim
    s.status = "The first note will start at 0 s." if s.trim else "Keeping the silence before the first note."


def export(kind):
    if s.rec_start is not None:
        s.status = "Press Stop before exporting."
        return
    if not s.take:
        s.status = "Nothing recorded yet. Press Record first."
        return
    OUT.mkdir(exist_ok=True)
    notes, name = take_notes(musical=kind in ("midi", "lily")), stamp()
    if kind == "wav":
        path = OUT / f"{name}.wav"
        synth.save_wav(path, synth.render(notes))
    elif kind == "py":
        path = OUT / f"{name.replace('-', '_')}.py"  # Underscores so it can be imported.
        export_python(notes, path)
    elif kind == "ts":
        path = OUT / f"{name}.ts"
        export_typescript(notes, path)
    elif kind == "midi":
        path = OUT / f"{name}.mid"
        path.write_bytes(notation.midi_bytes(notes, s.take_bpm))
    else:
        path = OUT / f"{name}.ly"
        path.write_text(notation.lilypond(notes, s.take_bpm, name))
        if not shutil.which("lilypond"):
            s.status = f"Saved {path.relative_to(HERE)}. Install LilyPond (brew install lilypond) to get a PDF."
            s.saved.add(kind)
            return
        s.status = "Engraving the score..."
        s.later = lambda: engrave(path)
        return
    s.saved.add(kind)
    s.status = f"Saved {path.relative_to(HERE)}"


def engrave(path):
    """Run LilyPond to turn the .ly into a PDF next to it. -o names the PDF after the .ly."""
    done = subprocess.run(["lilypond", "-o", str(path.with_suffix("")), str(path)], capture_output=True, text=True)
    if done.returncode:
        s.status = "LilyPond failed: " + done.stderr.strip().splitlines()[-1]
        return
    s.saved.add("lily")
    s.status = f"Saved {path.relative_to(HERE)} and its .pdf"


def press(action):
    """What each clickable thing does."""
    if action.startswith("family:"):
        choose(next(iter(synth.FAMILIES[action[7:]])))  # A family tab picks its first instrument.
    elif action.startswith("inst:"):
        choose(action[5:])
    elif action in ("down", "up"):
        shift_octave(-1 if action == "down" else 1)
    elif action in ("prev", "next"):
        step_instrument(-1 if action == "prev" else 1)
    elif action == "record":
        record()
    elif action == "play":
        play()
    elif action == "trim":
        toggle_trim()
    elif action == "midi_in":
        toggle_midi()
    elif action == "metronome":
        toggle_metronome()
    elif action in ("slower", "faster"):
        change_tempo(-BPM_STEP if action == "slower" else BPM_STEP)
    else:
        export(action)


# ---------------------------------------------------------------- input
def on_key_down(_, key):
    if key in KEYS:
        note_on(KEYS[key], s.low + KEYS[key])
    elif key in SHORTCUTS:
        press(SHORTCUTS[key])


def on_key_up(_, key):
    if key in KEYS:
        note_off(KEYS[key])


def on_mouse_down():
    pos = dpg.get_drawing_mouse_pos()
    for i in sorted(KEY_BOXES, key=lambda i: i not in BLACK):  # Black keys are on top, so check them first.
        if inside(KEY_BOXES[i], pos):
            s.mouse_key = i
            note_on(i, s.low + i)
            return
    for box, action in hits:
        if inside(box, pos):
            press(action)
            return


def on_mouse_up():
    if s.mouse_key is not None:
        note_off(s.mouse_key)
        s.mouse_key = None


# ---------------------------------------------------------------- drawing helpers
def box(b, fill, rounding=0):
    dpg.draw_rectangle(b[:2], b[2:], fill=fill, color=fill, rounding=rounding, parent="canvas")


def line(a, b, color, thickness=1):
    dpg.draw_line(a, b, color=color, thickness=thickness, parent="canvas")


def text_width(words, size, font="ui"):
    measured = dpg.get_text_size(words, font=font)  # None until the first frame has loaded the fonts.
    return (measured or [0])[0] * size / FONT_LOAD_SIZE


def text(pos, words, color, size=15, font="ui"):
    dpg.bind_item_font(dpg.draw_text(pos, words, color=color, size=size, parent="canvas"), font)


def text_in(b, words, color, size=15, font="ui", align="center"):
    """Text vertically centered in box b: centered, or from its left / right edge."""
    w = text_width(words, size, font)
    x = {"center": (b[0] + b[2] - w) / 2, "left": b[0] + 12, "right": b[2] - 12 - w}[align]
    text((x, (b[1] + b[3]) / 2 - size * 0.62), words, color, size, font)


def triangle(points, fill):
    dpg.draw_triangle(*points, fill=fill, color=fill, parent="canvas")


def hovered(b):
    return dpg.is_item_hovered("canvas") and inside(b, dpg.get_drawing_mouse_pos())


def pushed(b):
    return hovered(b) and dpg.is_mouse_button_down(dpg.mvMouseButton_Left)


def button(b, action, enabled=True, fill=LANE):
    """A flat button: lighter when hovered, darker while pressed. Returns its text color."""
    if enabled and pushed(b):
        fill = tuple(c - 8 for c in fill)
    elif enabled and hovered(b):
        fill = tuple(c + 12 for c in fill)
    box(b, fill, rounding=6)
    hits.append((b, action))
    if hovered(b) and action in HELP:
        s.hint = HELP[action]
    return INK if enabled else FAINT


# ---------------------------------------------------------------- drawing
def draw():
    """Paint the whole window from `s`. Called every frame."""
    dpg.delete_item("canvas", children_only=True)
    hits.clear()
    s.hint = None
    now = time.time()
    s.bars = [b for b in s.bars if b[2] is None or now - b[2] < 6]  # Forget bars that have risen off the top.
    box((0, 0, W, H), GROUND)
    draw_top()
    draw_row()
    draw_roll(now)
    draw_keys(now)
    draw_status(now)


def draw_top():
    box((0, 0, W, TOP_H), PANEL)
    recording = s.rec_start is not None
    # Record: a red dot. While recording the button turns red and becomes Stop.
    b = (16, 14, 108, 50)
    ink = button(b, "record", fill=(92, 34, 36) if recording else LANE)
    pulse = 255 if not recording else int(150 + 105 * math.sin(time.time() * 6))  # The dot breathes while recording.
    dpg.draw_circle((b[0] + 20, 32), 6, fill=(*REC_RED, pulse), color=(*REC_RED, pulse), parent="canvas")
    text((b[0] + 34, 32 - 9), "Stop" if recording else "Record", ink, 15, "bold")
    # Play: a triangle.
    b = (116, 14, 196, 50)
    ink = button(b, "play", enabled=bool(s.take) and not recording)
    triangle(((b[0] + 15, 26), (b[0] + 15, 38), (b[0] + 25, 32)), ink)
    text((b[0] + 34, 32 - 9), "Play", ink, 15, "bold")
    # Metronome: its light flashes on each beat while it's on.
    b = (204, 14, 304, 50)
    button(b, "metronome")
    on_beat = (time.time() - s.beat0) % (60 / s.click_bpm) < 0.1
    light = (INK if on_beat else DIM) if s.metronome else FAINT
    dpg.draw_circle((b[0] + 14, 32), 3.5, fill=light, color=light, parent="canvas")
    text((b[0] + 24, 32 - 9), "Metronome", INK if s.metronome else DIM, 15, "bold")

    # Family tabs. Each family's color underlines its tab; the current one is filled.
    family_now = family_of(s.instrument)
    for n, (family, color) in enumerate(FAMILY_COLORS.items()):
        b = (316 + n * 60, 14, 316 + n * 60 + 58, 50)
        on = family == family_now
        button(b, f"family:{family}", fill=LANE if on else PANEL)
        if on:  # The current family's color at full strength; the others are a faint hairline.
            box((b[0] + 8, b[3] - 4, b[2] - 8, b[3]), color, rounding=1)
        else:
            box((b[0] + 18, b[3] - 4, b[2] - 18, b[3] - 3), tuple(c // 2 + p // 2 for c, p in zip(color, PANEL)))
        text_in(b, FAMILY_LABELS.get(family, family), INK if on else DIM, 15, "bold")

    # Exports, then Trim. Exports work once there's a finished take; each one saved
    # from this take gets a check mark until the next take.
    ready = bool(s.take) and not recording
    x = 622
    for kind, label in EXPORTS.items():
        w = 66 if kind == "lily" else 52
        b = (x, 14, x + w, 50)
        ink = button(b, kind, enabled=ready)
        if kind in s.saved and not recording:  # Label and check mark, centered together.
            x0 = (b[0] + b[2] - text_width(label, 14, "bold") - 13) / 2
            text((x0, 32 - 9), label, INK, 14, "bold")
            cx = x0 + text_width(label, 14, "bold") + 5
            line((cx, 32), (cx + 3, 35), INK, 2)
            line((cx + 3, 35), (cx + 9, 28), INK, 2)
        else:
            text_in(b, label, ink, 14, "bold")
        x += w + 4
    b = (W - 16 - 64, 14, W - 16, 50)
    button(b, "trim")
    light = INK if s.trim else FAINT  # A small light: on or off.
    dpg.draw_circle((b[0] + 14, 32), 3.5, fill=light, color=light, parent="canvas")
    text((b[0] + 24, 32 - 9), "Trim on" if s.trim else "Trim off", INK if s.trim else DIM, 14, "bold")


def draw_row():
    """The current family's instruments, and the octave control on the right."""
    family = family_of(s.instrument)
    color = FAMILY_COLORS[family]
    for n, name in enumerate(synth.FAMILIES[family]):
        b = (16 + n * 128, ROW[1] + 8, 16 + n * 128 + 122, ROW[3] - 6)
        on = name == s.instrument
        if on:
            box(b, color, rounding=6)
            hits.append((b, f"inst:{name}"))
            text_in(b, pretty(name), GROUND, 15, "bold")
        else:
            button(b, f"inst:{name}", fill=GROUND)
            text_in(b, pretty(name), DIM, 15, "bold")
    # MIDI: its light is on while a MIDI keyboard is connected.
    b = (W - 300, ROW[1] + 8, W - 208, ROW[3] - 6)
    button(b, "midi_in", fill=GROUND)
    light = INK if s.midi_in else FAINT
    dpg.draw_circle((b[0] + 14, (b[1] + b[3]) / 2), 3.5, fill=light, color=light, parent="canvas")
    text((b[0] + 24, (b[1] + b[3]) / 2 - 9), "MIDI", INK if s.midi_in else DIM, 15, "bold")
    # Octave: down, the range the keys play, up.
    down, up = (W - 196, ROW[1] + 8, W - 164, ROW[3] - 6), (W - 48, ROW[1] + 8, W - 16, ROW[3] - 6)
    for b, action, sign in ((down, "down", -1), (up, "up", 1)):
        ink = button(b, action, enabled=(s.low > LOWEST) if sign < 0 else (s.low < HIGHEST))
        cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        triangle(((cx - 5 * sign, cy - 6), (cx - 5 * sign, cy + 6), (cx + 5 * sign, cy)), ink)
    text_in((down[2], down[1], up[0], up[3]), f"{note_name(s.low)} – {note_name(s.low + 12)}", INK, 15, "bold")


def draw_roll(now):
    left, top, right, bottom = ROLL
    box(ROLL, LANE)  # The roll's surface, a step lighter than the window.
    # Lanes: a darker strip above each black key, a thin line between white keys.
    for i, b in KEY_BOXES.items():
        if i in BLACK:
            box((b[0], top, b[2], bottom), BLACK_LANE)
        elif b[0] > left and i - 1 not in BLACK:  # Only E|F and B|C have no black key between them.
            line((b[0], top), (b[0], bottom), LINE)
    # The beat grid rises with the notes, in step with the metronome, so notes played on
    # the beat line up with it. Beat k happened at s.beat0 + k * beat; k = 0, 4, 8... start bars.
    beat = 60 / s.click_bpm
    oldest = now - (bottom - top) / SPEED  # The time that has risen to the top of the roll.
    for k in range(math.ceil((oldest - s.beat0) / beat), math.floor((now - s.beat0) / beat) + 1):
        y = bottom - (now - s.beat0 - k * beat) * SPEED
        line((left, y), (right, y), BAR_LINE if k % BEATS_PER_BAR == 0 else LINE)
    # The bars. A bar's top is where the note started and its bottom where it ended,
    # both rising at SPEED. A held note's bottom stays on the keys. White-key bars go
    # first so black-key bars sit on top, and an outline keeps neighbours apart.
    for i, start, end, color in sorted(s.bars, key=lambda bar: bar[0] in BLACK):
        if start > now:
            continue  # Playback notes that haven't started yet.
        b = KEY_BOXES[i]
        pad = 4 if i in BLACK else 6
        y_top = max(top, bottom - (now - start) * SPEED)
        y_bottom = bottom if end is None or end > now else bottom - (now - end) * SPEED
        if y_bottom - y_top >= 1:
            dpg.draw_rectangle((b[0] + pad, y_top), (b[2] - pad, y_bottom), fill=color, color=BLACK_LANE,
                               thickness=2, rounding=3, parent="canvas")
    if s.rec_start is not None:  # A red line along the keys while recording.
        box((left, bottom - 3, right, bottom), REC_RED)
    if not s.bars and s.last is None:  # Before the first note: say what the roll is for.
        text_in((left, top, right, bottom), "Play a key. Each note rises here, as tall as you hold it.", DIM, 16)


def draw_keys(now):
    # A key is lit while a bar in its lane is sounding: your own notes and the take playing back.
    lit = {i: color for i, start, end, color in s.bars if start <= now and (end is None or end > now)}
    for black in (False, True):  # White keys first, so black keys draw on top.
        for i, b in KEY_BOXES.items():
            if (i in BLACK) != black:
                continue
            box(b, lit.get(i, EBONY if black else IVORY), rounding=4)
            if not black:
                line((b[0], b[1]), (b[0], b[3]), GROUND, 2)  # The gap between white keys.
            if i in lit or not black:
                ink, hint = GROUND, (96, 96, 102) if i not in lit else GROUND
            else:
                ink, hint = INK, DIM
            text((b[0] + 10, b[3] - 44), LETTERS[i].upper(), hint, 14, "bold")
            text((b[0] + 10, b[3] - 24), note_name(s.low + i), ink, 15, "bold")


def draw_status(now):
    b = (0, KEYS_BOTTOM + 4, W, H)
    box(b, PANEL)
    text_in(b, s.hint or s.status, INK if s.hint else DIM, 14, align="left")
    # The readout: the note you're playing (or played last), how long, and the take.
    if s.held:
        midi, _, start, _, _ = max(s.held.values(), key=lambda h: h[2])  # The most recent key still down.
        note = f"{note_name(midi)}  {now - start:.2f} s"
    elif s.last:
        note = f"{note_name(s.last[0])}  {s.last[1]:.2f} s"
    else:
        note = "–"
    if s.rec_start is not None and now < s.rec_start:
        take = f"Count-in {math.ceil((s.rec_start - now) * s.bpm / 60)}"
    elif s.rec_start is not None:
        take = f"Recording {now - s.rec_start:.1f} s, {len(s.recording)} notes"
    elif s.take:
        take = f"Take: {len(s.take)} notes, {s.take[-1][0] + s.take[-1][2] - s.take[0][0]:.1f} s"
    else:
        take = "No take yet"
    # Fixed left edges, so the ticking numbers don't shift the line every frame.
    y = (b[1] + b[3]) / 2 - 14 * 0.62
    text((W - 450, y), note, INK, 14)
    text((W - 340, y), take, INK, 14)
    # Tempo: slower, the BPM, faster. Locked while recording.
    slower, faster = (W - 130, b[1] + 4, W - 106, b[3] - 4), (W - 40, b[1] + 4, W - 16, b[3] - 4)
    for bb, action in ((slower, "slower"), (faster, "faster")):
        ink = button(bb, action, enabled=s.rec_start is None)
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        line((cx - 5, cy), (cx + 5, cy), ink, 2)
        if action == "faster":
            line((cx, cy - 5), (cx, cy + 5), ink, 2)
    text_in((slower[2], b[1], faster[0], b[3]), f"{s.bpm} BPM", INK, 14, "bold")


# ---------------------------------------------------------------- setup
# Fonts are loaded at twice the size they're drawn so they stay sharp on Retina screens (see main()).
FONT_LOAD_SIZE = 30
KEYS = {}  # DearPyGui key code -> piano key. Filled in by main(), once DearPyGui is running.
SHORTCUTS = {}  # DearPyGui key code -> action.


def main():
    # Ask for exactly our sample rate in mono 16-bit. allowedchanges=0 tells SDL to
    # convert for the sound card itself, so our arrays always play at the right pitch.
    # buffer=256 samples (~12 ms) keeps the delay between keypress and sound short.
    pygame.mixer.pre_init(synth.SR, -16, 1, 256, allowedchanges=0)
    pygame.mixer.init()
    pygame.mixer.set_num_channels(32)  # Up to 32 notes at once, including release tails.
    pygame.mixer.set_reserved(1)  # Channel 0 is kept for the metronome; notes never take it.
    load(s.instrument)
    pygame.midi.init()
    if pygame.midi.get_default_input_id() >= 0:
        toggle_midi()

    dpg.create_context()
    KEYS.update({getattr(dpg, f"mvKey_{c.upper()}"): i for i, c in enumerate(LETTERS)})
    SHORTCUTS.update({dpg.mvKey_Z: "down", dpg.mvKey_X: "up", dpg.mvKey_Left: "down",
                      dpg.mvKey_Right: "up", dpg.mvKey_Up: "prev", dpg.mvKey_Down: "next",
                      dpg.mvKey_M: "metronome", dpg.mvKey_Open_Brace: "slower", dpg.mvKey_Close_Brace: "faster"})
    with dpg.font_registry():
        dpg.add_font(str(FONTS / "BarlowSemiCondensed-Medium.ttf"), FONT_LOAD_SIZE, tag="ui")
        dpg.add_font(str(FONTS / "BarlowSemiCondensed-SemiBold.ttf"), FONT_LOAD_SIZE, tag="bold")
    dpg.set_global_font_scale(0.5)
    with dpg.theme() as no_padding, dpg.theme_component(dpg.mvAll):
        dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 0, 0)
        dpg.add_theme_color(dpg.mvThemeCol_WindowBg, GROUND)
    dpg.bind_theme(no_padding)
    with dpg.window(tag="main", no_scrollbar=True):
        dpg.add_drawlist(W, H, tag="canvas")
    with dpg.handler_registry():
        dpg.add_key_press_handler(callback=on_key_down)
        dpg.add_key_release_handler(callback=on_key_up)
        dpg.add_mouse_click_handler(button=dpg.mvMouseButton_Left, callback=on_mouse_down)
        dpg.add_mouse_release_handler(button=dpg.mvMouseButton_Left, callback=on_mouse_up)

    dpg.create_viewport(title="sound-maker", width=W, height=H, resizable=False)
    dpg.setup_dearpygui()
    dpg.show_viewport()
    dpg.set_primary_window("main", True)
    while dpg.is_dearpygui_running():
        read_midi()
        draw()
        dpg.render_dearpygui_frame()
        if s.later:  # A slow job whose "working" message is now on screen.
            job, s.later = s.later, None
            job()
    if s.midi_in:
        s.midi_in.close()
    dpg.destroy_context()


if __name__ == "__main__":
    main()
