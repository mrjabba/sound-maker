"""
notation.py: turns a take into a MIDI file or LilyPond sheet music. Like synth.py,
it has no UI, so other scripts can import it.

    from notation import midi_bytes, lilypond
    Path("take.mid").write_bytes(midi_bytes(notes, bpm=100))
    Path("take.ly").write_text(lilypond(notes, bpm=100, title="take"))

A take is in seconds, but music is written in beats, so both need a tempo (bpm).
* The MIDI file keeps the exact timing. MuseScore, GarageBand, etc. open it, and
  MuseScore shows it as sheet music.
* The LilyPond file snaps notes to a 16th-note grid in 4/4 time. Running
  `lilypond take.ly` engraves it as take.pdf.
Both line up with the bars only if the take was played at that tempo.

Run `python notation.py` to run the self-check at the bottom.
"""
import struct
from math import inf

# instrument -> (General MIDI program, LilyPond clef). Programs count from 0 (0 = Acoustic Grand Piano).
# Clef None means a two-staff piano part that moves notes between staves automatically.
# "treble_8" and "bass_8" mean the part sounds an octave lower than written, as guitar and double bass parts do.
# Everything is written at concert pitch, so clarinet, trumpet, horn and sax parts are not transposed.
MELODIC = {
    "piano": (0, None),
    "organ": (16, None),
    "guitar": (25, "treble_8"),
    "harp": (46, None),
    "violin": (40, "treble"),
    "viola": (41, "alto"),
    "cello": (42, "bass"),
    "double_bass": (43, "bass_8"),
    "flute": (73, "treble"),
    "oboe": (68, "treble"),
    "clarinet": (71, "treble"),
    "bassoon": (70, "bass"),
    "saxophone": (65, "treble"),
    "trumpet": (56, "treble"),
    "french_horn": (60, "treble"),
    "trombone": (57, "bass"),
    "tuba": (58, "bass"),
    "timpani": (47, "bass"),
    "xylophone": (13, "treble"),
}
# Unpitched instruments -> (General MIDI drum note, LilyPond drum name). Every key plays the same drum.
DRUMS = {"snare_drum": (38, "sn"), "cymbals": (49, "cymc")}


def instruments_in(notes):
    """The instruments a take uses, in the order they first play."""
    return list(dict.fromkeys(inst for *_, inst in notes))


def pretty(name):
    """"french_horn" -> "French Horn"."""
    return name.replace("_", " ").title()


# ---------------------------------------------------------------- MIDI
TICKS = 480  # MIDI time steps per beat.
CHANNELS = [c for c in range(16) if c != 9]  # Channel 10 (9 counting from 0) is reserved for drums.


def _vlq(n):
    """MIDI's variable-length number: 7 bits per byte, high bit set on every byte but the last."""
    out = [n & 0x7F]
    while n > 0x7F:
        n >>= 7
        out.append(0x80 | (n & 0x7F))
    return bytes(reversed(out))


def midi_bytes(notes, bpm):
    """A standard MIDI file (type 1): a tempo track, then one track per instrument on its own channel."""
    tempo = round(60_000_000 / bpm).to_bytes(3, "big")  # Microseconds per beat.
    tracks = [b"\x00\xff\x51\x03" + tempo + b"\x00\xff\x58\x04\x04\x02\x18\x08"]  # Tempo, then 4/4 time.
    for i, name in enumerate(instruments_in(notes)):
        # ponytail: more than 15 pitched instruments in one take would share channels.
        ch = 9 if name in DRUMS else CHANNELS[i % len(CHANNELS)]
        events = []  # (tick, 0 for off / 1 for on, message). Sorting puts note-offs before note-ons at the same tick.
        for at, midi, held, inst in notes:
            if inst == name:
                key = DRUMS[name][0] if name in DRUMS else midi
                on = round(at * bpm / 60 * TICKS)
                off = max(on + 1, round((at + held) * bpm / 60 * TICKS))
                events += [(on, 1, bytes([0x90 | ch, key, 90])), (off, 0, bytes([0x80 | ch, key, 0]))]
        label = pretty(name).encode()
        data = b"\x00\xff\x03" + _vlq(len(label)) + label  # Track name.
        if name not in DRUMS:
            data += bytes([0, 0xC0 | ch, MELODIC[name][0]])  # Pick the instrument's sound.
        last = 0
        for tick, _, message in sorted(events):
            data += _vlq(tick - last) + message
            last = tick
        tracks.append(data)
    tracks = [t + b"\x00\xff\x2f\x00" for t in tracks]  # End of track.
    header = b"MThd" + struct.pack(">IHHH", 6, 1, len(tracks), TICKS)
    return header + b"".join(b"MTrk" + struct.pack(">I", len(t)) + t for t in tracks)


# ---------------------------------------------------------------- LilyPond
STEPS_PER_BEAT = 4  # The grid notes snap to: 16th notes.
BAR = 4 * STEPS_PER_BEAT  # Steps in a bar of 4/4.
# Lengths LilyPond can write as one note, in 16ths: whole, dotted half, half, dotted quarter, ...
LENGTHS = {16: "1", 12: "2.", 8: "2", 6: "4.", 4: "4", 3: "8.", 2: "8", 1: "16"}
NAMES = ["c", "cis", "d", "dis", "e", "f", "fis", "g", "gis", "a", "ais", "b"]  # LilyPond's names. "cis" is C#.


def pitch(midi):
    """60 -> "c'" (middle C), 48 -> "c", 47 -> "b,". Always spelled with sharps."""
    octave = midi // 12 - 4
    return NAMES[midi % 12] + ("'" * octave if octave > 0 else "," * -octave)


def quantize(notes, bpm):
    """(start, midi, held) in seconds -> [(start step, length in steps, set of midi)] on the grid.

    Notes that start on the same step become one chord. A chord is cut short where the
    next one starts, because each staff here holds a single line of music.
    """
    per_second = bpm / 60 * STEPS_PER_BEAT
    chords = {}
    for at, midi, held in notes:
        s = round(at * per_second)
        length, keys = chords.get(s, (0, set()))
        chords[s] = (max(length, round(held * per_second), 1), keys | {midi})
    starts = sorted(chords)
    return [(s, min(chords[s][0], nxt - s), chords[s][1]) for s, nxt in zip(starts, starts[1:] + [inf])]


def music(chords, name, end=0):
    """Quantized chords -> LilyPond notes and rests, split at barlines and tied where needed.
    name(set of midi) gives the text for a note or chord, for example "c'" or "<c' e'>".
    Rests fill out the music up to step `end`, so every staff ends on the same barline."""
    out, t = [], 0

    def put(text, steps, tie):
        nonlocal t
        while steps:
            n = min(steps, BAR - t % BAR)  # Stop at the next barline.
            n = max(k for k in LENGTHS if k <= n)  # The longest note that can be written in one go.
            steps -= n
            t += n
            out.append(text + LENGTHS[n] + ("~" if tie and steps else "") + (" |\n" if t % BAR == 0 else " "))

    for start, length, keys in chords:
        put("r", start - t, False)  # A rest for any gap before the chord.
        put(name(keys), length, True)
    put("r", max(0, end - t), False)
    return "".join(out).rstrip()


def chord_name(keys):
    names = [pitch(k) for k in sorted(keys)]
    return names[0] if len(names) == 1 else "<" + " ".join(names) + ">"


def lilypond(notes, bpm, title):
    """A LilyPond score with one staff per instrument, in the order they first play."""
    parts = {name: quantize([(at, m, held) for at, m, held, inst in notes if inst == name], bpm) for name in instruments_in(notes)}
    last = max(start + length for chords in parts.values() for start, length, _ in chords)
    end = -(-last // BAR) * BAR  # Round up to a whole bar.
    staves = []
    for name, chords in parts.items():
        start = (rf"\tempo 4 = {bpm} " if not staves else "") + r"\time 4/4"
        head = rf'\with {{ instrumentName = "{pretty(name)}" }}'
        if name in DRUMS:
            drum = DRUMS[name][1]
            staves.append(rf"\new DrumStaff {head} \drummode {{ {start}" + "\n" + music(chords, lambda _: drum, end) + "\n}")
        elif MELODIC[name][1]:
            body = rf'{start} \clef "{MELODIC[name][1]}"' + "\n" + music(chords, chord_name, end)
            staves.append(rf"\new Staff {head} {{ {body}" + "\n}")
        else:
            staves.append(rf"\new PianoStaff {head} \autoChange {{ {start}" + "\n" + music(chords, chord_name, end) + "\n}")
    return (
        rf'''\version "2.24.0"
\header {{ title = "{title}" tagline = ##f }}
\score {{
<<
'''
        + "\n".join(staves)
        + r"""
>>
\layout { }
}
"""
    )


# ---------------------------------------------------------------- self-check
if __name__ == "__main__":
    import synth

    assert set(MELODIC) | set(DRUMS) == set(synth.INSTRUMENTS), "every instrument needs a MIDI program and clef"
    assert (pitch(60), pitch(48), pitch(47), pitch(73)) == ("c'", "c", "b,", "cis''")
    assert _vlq(0) == b"\x00" and _vlq(0x80) == b"\x81\x00" and _vlq(480) == b"\x83\x60"
    # At 60 bpm one beat is one second. C for a beat, a short E+G chord, a rest, then a
    # D held 3 beats, which crosses the barline and gets tied.
    take = [(0.0, 60, 1.0, "cello"), (1.02, 64, 0.5, "cello"), (0.98, 67, 0.5, "cello"), (2.0, 62, 3.0, "cello")]
    chords = quantize([(at, m, h) for at, m, h, _ in take], 60)
    assert chords == [(0, 4, {60}), (4, 2, {64, 67}), (8, 12, {62})], chords
    assert music(chords, chord_name) == "c'4 <e' g'>8 r8 d'2~ |\nd'4", music(chords, chord_name)
    data = midi_bytes(take + [(0.0, 60, 0.1, "snare_drum")], 120)
    assert data[:4] == b"MThd" and data.count(b"MTrk") == 3
    assert r"\clef " in lilypond(take, 60, "t") and r"\drummode" in lilypond([(0.0, 60, 0.1, "cymbals")], 60, "t")
    print("ok")
