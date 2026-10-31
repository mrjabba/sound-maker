"""
synth.py: every sound in sound-maker is made from math here. There are no audio samples.

This file has no UI and no pygame, so other scripts can import it, for example
a game's asset script or a file the app exported:

    from synth import render, save_wav
    notes = [(0.0, 60, 0.5, "piano"), (0.5, 64, 0.5, "flute")]
    save_wav("out.wav", render(notes))

Two ideas to know:

* A sound is a numpy array of floats between -1 and 1, one per sample.
  SR (sample rate) samples make up one second of sound.
* An instrument is a function  fn(freq_hz, seconds) -> array.  This
  simple shape makes the instruments easy to call from other code.

Run `python synth.py` to run the self-check at the bottom.
"""
import wave

import numpy as np

SR = 22050          # Samples per second. 22050 is plenty for game sounds and keeps files small.
NOTE_GAIN = 0.3     # Volume of one note. Kept below 1 so a chord of 3 or 4 notes doesn't clip.
RELEASE = 0.15      # Seconds a note takes to fade out after you let go of its key.


def hz(midi):
    """MIDI note number -> frequency. 69 is A4 (440 Hz), 60 is middle C, +1 = one half step up."""
    return 440.0 * 2 ** ((midi - 69) / 12)


def _t(seconds):
    """Time in seconds of every sample: [0, 1/SR, 2/SR, ...]."""
    return np.arange(int(seconds * SR)) / SR


def _attack(t, seconds):
    """Fade in from 0 to 1 over `seconds`. Without it every note would start with a click."""
    return np.minimum(1.0, t / seconds)


def _partials(freq, seconds, partials, attack, vibrato=0.0, rate=5.0, decay=0.0):
    """The recipe most instruments share: add up sine waves at freq * ratio, each at its
    level, with a vibrato that fades in over 0.4 s and an optional fade-out (decay per
    second). Dividing by the sum of the levels keeps the peak at or below 1."""
    t = _t(seconds)
    phase = np.cumsum(freq * (1 + vibrato * np.minimum(1, t / 0.4) * np.sin(2 * np.pi * rate * t))) / SR
    out = sum(level * np.sin(2 * np.pi * ratio * phase) for ratio, level in partials)
    return _attack(t, attack) * np.exp(-decay * t) * out / sum(level for _, level in partials)


def _harmonics(*levels):
    """Levels for harmonics 1, 2, 3... -> (ratio, level) pairs for _partials."""
    return list(enumerate(levels, 1))


# ---------------------------------------------------------------- instruments
# Every instrument builds its tone by adding up sine waves (harmonics) or by
# shaping noise, then multiplies by an envelope (the volume over time).
# The number each one divides by at the end brings its loudest point to about 1.0,
# so every instrument plays at the same volume.


def piano(freq, seconds):
    """A struck string. The harmonics are slightly sharp, because real piano strings
    are stiff, and the higher ones fade faster than the low ones. It fades away even
    if you keep holding the key, like a real piano."""
    t = _t(seconds)
    out = np.zeros_like(t)
    for k in range(1, 8):
        stretch = np.sqrt(1 + 0.0004 * k * k)   # Slightly sharp, more so for higher harmonics.
        fade = np.exp(-t * (1.6 + k * 1.4))     # Harmonic k dies away faster as k grows.
        out += fade / k**1.2 * np.sin(2 * np.pi * freq * k * stretch * t)
    return _attack(t, 0.0025) * out / 1.7


def organ(freq, seconds):
    """A tonewheel organ: fixed sine "drawbars" at several harmonics, a fast attack
    (the key click), and a slow wobble in volume like a rotating Leslie speaker.
    It holds at full volume for as long as you hold the key."""
    t = _t(seconds)
    # (harmonic, level). 0.5 is the octave below. Change these to change the registration.
    drawbars = ((0.5, 0.5), (1, 1.0), (2, 0.6), (3, 0.4), (4, 0.3), (6, 0.15))
    out = sum(level * np.sin(2 * np.pi * freq * h * t) for h, level in drawbars)
    leslie = 1 + 0.08 * np.sin(2 * np.pi * 6 * t)
    return _attack(t, 0.005) * leslie * out / 2.05


def _pluck(freq, seconds, loss, noise):
    """A plucked string using the Karplus-Strong algorithm.

    It starts with one period of random noise, which is the pluck. Then it plays that
    period over and over, and each time through it averages each sample with its
    neighbour. The averaging removes the harsh high frequencies first, so a noisy burst
    turns into a mellow tone that dies away, the way a real string does.
    loss (just under 1) sets how long it rings, and noise how bright the pluck is.
    """
    n = int(seconds * SR)
    # Averaging two neighbouring samples delays the signal by half a sample, so take
    # 0.5 off to stay in tune.
    # ponytail: the period is rounded to whole samples, so pitch can be off by up to
    # ~10 cents at C5. A fractional-delay filter would fix it if anyone notices.
    period = max(2, round(SR / freq - 0.5))
    rng = np.random.default_rng(int(freq))  # Same seed every time, so the same note sounds the same.
    out = np.zeros(n + period)
    # The pluck: the string pulled into a triangle shape (which gives a strong fundamental)
    # plus noise (which gives the bright "pick" sound).
    shape = 1 - 2 * np.abs(np.linspace(-1, 1, period))
    burst = (1 - noise) * shape + noise * rng.uniform(-1, 1, period)
    out[:period] = burst - burst.mean()   # Center it on 0. Averaging never removes an offset, so it would stay forever.
    # Fill in the samples one period-sized block at a time. This uses
    # y[i] = loss * (y[i - period] + y[i - period - 1]) / 2
    for start in range(period, n + period, period):
        prev = out[start - period:start]
        before = np.concatenate(([out[start - period - 1] if start > period else 0.0], prev[:-1]))
        block = loss * 0.5 * (prev + before)
        end = min(start + period, len(out))
        out[start:end] = block[: end - start]
    return out[:n] / np.abs(out[:period]).max()   # The pluck is the loudest moment.


def guitar(freq, seconds):
    """An acoustic guitar string: a bright pick that dies away fairly quickly."""
    return _pluck(freq, seconds, loss=0.996, noise=0.3)


def harp(freq, seconds):
    """A harp string: plucked with a finger, so softer than a pick, and it rings longer."""
    return _pluck(freq, seconds, loss=0.998, noise=0.1)


def trumpet(freq, seconds):
    """A brass buzz: lots of harmonics (a sawtooth wave) that start muffled and open up
    as the player begins to blow, with vibrato that fades in on long notes."""
    t = _t(seconds)
    vibrato = 1 + 0.006 * np.minimum(1, t / 0.4) * np.sin(2 * np.pi * 5.5 * t)
    # When the pitch keeps changing (vibrato), add up the frequency over time to get the
    # phase, instead of using freq * t.
    phase = np.cumsum(freq * vibrato) / SR
    brightness = 2 + 6 * np.minimum(1, t / 0.08)  # How many harmonics are open. Rises from 2 to 8.
    out = sum(np.sin(2 * np.pi * k * phase) / k * np.exp(-((k / brightness) ** 2)) for k in range(1, 15))
    return _attack(t, 0.03) * out / 1.4


def flute(freq, seconds):
    """Close to a pure sine wave, plus a little breath noise and a gentle vibrato.
    It fades in slowly, the way breath does."""
    t = _t(seconds)
    vibrato = 1 + 0.004 * np.minimum(1, t / 0.5) * np.sin(2 * np.pi * 5 * t)
    phase = np.cumsum(freq * vibrato) / SR
    tone = np.sin(2 * np.pi * phase) + 0.25 * np.sin(4 * np.pi * phase) + 0.08 * np.sin(6 * np.pi * phase)
    rng = np.random.default_rng(int(freq))
    breath = np.convolve(rng.uniform(-1, 1, len(t)), np.ones(8) / 8, mode="same")  # Smoothed (low-passed) noise.
    breathiness = 0.1 + 0.25 * np.exp(-t * 12)  # Breathier while the note is starting.
    return _attack(t, 0.08) * (tone + breathiness * breath) / 1.3


# Woodwinds and brass. Each is a mix of harmonics: clarinet has almost only the odd
# ones (a hollow sound), the reeds have strong upper ones (nasal, buzzy), and the low
# brass have few (round, dark).
def oboe(freq, seconds):
    """A double reed: bright and nasal, with strong upper harmonics."""
    return _partials(freq, seconds, _harmonics(1, 0.9, 0.8, 0.6, 0.45, 0.3, 0.2, 0.15), 0.04, 0.005, 5)


def clarinet(freq, seconds):
    """A single reed in a cylinder: mostly odd harmonics, which sounds hollow."""
    return _partials(freq, seconds, _harmonics(1, 0.05, 0.45, 0.04, 0.25, 0.03, 0.12, 0, 0.06), 0.04, 0.002, 5)


def bassoon(freq, seconds):
    """The oboe's big cousin: reedy but darker, with fewer upper harmonics."""
    return _partials(freq, seconds, _harmonics(1, 0.8, 0.6, 0.4, 0.25, 0.12, 0.06), 0.05, 0.003, 5)


def saxophone(freq, seconds):
    """A reed in a cone: lots of harmonics, so it's buzzy, with a wide vibrato."""
    return _partials(freq, seconds, _harmonics(1, 0.8, 0.65, 0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1), 0.03, 0.006, 5.5)


def french_horn(freq, seconds):
    """Mellow brass: few harmonics and a soft attack."""
    return _partials(freq, seconds, _harmonics(1, 0.5, 0.25, 0.12, 0.06), 0.06, 0.002, 5)


def trombone(freq, seconds):
    """Brass between the horn and the trumpet in brightness."""
    return _partials(freq, seconds, _harmonics(1, 0.7, 0.5, 0.35, 0.25, 0.15, 0.1), 0.05, 0.002, 5)


def tuba(freq, seconds):
    """Low, round brass: almost just the fundamental and the first few harmonics."""
    return _partials(freq, seconds, _harmonics(1, 0.45, 0.2, 0.08), 0.06)


# Bowed strings: a sawtooth (harmonic k at level 1/k) is what a bow makes a string do.
# The bigger the instrument, the faster the harmonics fall off, the slower the bow
# gets going, and the slower the vibrato.
def violin(freq, seconds):
    return _partials(freq, seconds, [(k, k**-1.0) for k in range(1, 13)], 0.08, 0.007, 5.5)


def viola(freq, seconds):
    return _partials(freq, seconds, [(k, k**-1.2) for k in range(1, 11)], 0.09, 0.006, 5.2)


def cello(freq, seconds):
    return _partials(freq, seconds, [(k, k**-1.3) for k in range(1, 11)], 0.1, 0.006, 5)


def double_bass(freq, seconds):
    return _partials(freq, seconds, [(k, k**-1.5) for k in range(1, 9)], 0.12, 0.004, 4.5)


# Percussion. Drums and bars don't vibrate in whole-number harmonics, so their
# ratios are odd numbers like 1.5 and 3.93. They're struck, so they all fade away.
def timpani(freq, seconds):
    """A kettle drum: a tuned membrane with a booming fundamental."""
    return _partials(freq, seconds, [(1, 1), (1.5, 0.5), (1.98, 0.3), (2.44, 0.15)], 0.003, decay=1.8)


def xylophone(freq, seconds):
    """A struck wooden bar: a short bright 'tock' (overtones at 3.93x and 9.36x)."""
    return _partials(freq, seconds, [(1, 1), (3.93, 0.35), (9.36, 0.1)], 0.001, decay=7)


def snare_drum(freq, seconds):
    """A burst of noise (the snare wires) over a quick thump (the drum head).
    The key you press tunes the thump."""
    t = _t(seconds)
    rng = np.random.default_rng(int(freq))
    rattle = rng.uniform(-1, 1, len(t)) * np.exp(-t * 18)
    thump = np.sin(2 * np.pi * freq * t) * np.exp(-t * 30)
    return _attack(t, 0.001) * (0.7 * rattle + 0.5 * thump) / 1.15


def cymbals(freq, seconds):
    """A crash: high-pitched noise that rings for a while. Higher keys die away faster."""
    t = _t(seconds)
    rng = np.random.default_rng(int(freq))
    noise = rng.uniform(-1, 1, len(t))
    hiss = noise - np.convolve(noise, np.ones(4) / 4, mode="same")  # Noise minus its smoothed self = only the highs.
    return _attack(t, 0.002) * np.exp(-t * freq / 300) * hiss / 1.35


# The app shows one row of buttons per family, in this order. To add an instrument,
# write a function above and add it to a family.
FAMILIES = {
    "Keys & plucked": {"piano": piano, "organ": organ, "guitar": guitar, "harp": harp},
    "Strings": {"violin": violin, "viola": viola, "cello": cello, "double_bass": double_bass},
    "Woodwinds": {"flute": flute, "oboe": oboe, "clarinet": clarinet, "bassoon": bassoon, "saxophone": saxophone},
    "Brass": {"trumpet": trumpet, "french_horn": french_horn, "trombone": trombone, "tuba": tuba},
    "Percussion": {"timpani": timpani, "snare_drum": snare_drum, "cymbals": cymbals, "xylophone": xylophone},
}
INSTRUMENTS = {name: fn for family in FAMILIES.values() for name, fn in family.items()}
UNPITCHED = {"snare_drum", "cymbals"}  # Noise-based, so the self-check skips their pitch test.


# ---------------------------------------------------------------- songs
def render(notes):
    """Mix a list of notes into one sound.

    notes: (start_seconds, midi, held_seconds, instrument_name) for each note. This is
    what the app records. Each note plays for held_seconds and then fades out over
    RELEASE seconds. The live app fades notes the same way, so the file sounds like
    what you played.
    """
    if not notes:
        return np.zeros(0)
    end = max(at + held + RELEASE for at, _, held, _ in notes)
    buf = np.zeros(int(end * SR) + 1)
    r = int(RELEASE * SR)
    for at, midi, held, name in notes:
        s = INSTRUMENTS[name](hz(midi), held + RELEASE) * NOTE_GAIN
        s[-r:] *= np.linspace(1, 0, min(r, len(s)))   # The fade-out after the key is released.
        i = int(at * SR)
        buf[i:i + len(s)] += s
    peak = np.abs(buf).max()
    return buf * (0.99 / peak) if peak > 0.99 else buf  # Only turn it down, and only if it would clip.


def metronome_bar(bpm, beats=4):
    """One bar of metronome clicks at bpm: a short high blip on every beat, higher on
    beat 1 so you can hear where the bar starts. Loop it for a steady click track."""
    beat = int(SR * 60 / bpm)
    out = np.zeros(beat * beats)
    t = _t(0.03)  # Each click lasts 30 ms.
    for n in range(beats):
        freq = 2000 if n == 0 else 1500
        out[n * beat:n * beat + len(t)] = np.sin(2 * np.pi * freq * t) * np.exp(-t * 150) * 0.5
    return out


def to_int16(samples):
    """Convert floats (-1..1) to 16-bit integers, the format WAV files and pygame use."""
    return (np.clip(samples, -1, 1) * 32767).astype(np.int16)


def save_wav(path, samples):
    """Write a mono, 16-bit WAV at SR samples per second."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(to_int16(samples).tobytes())


# ---------------------------------------------------------------- self-check
if __name__ == "__main__":
    # Every instrument should play the pitch it was asked for and stay within -1..1.
    # This finds the strongest frequency with an FFT and checks it is A4 (440 Hz).
    for name, fn in INSTRUMENTS.items():
        x = fn(440.0, 1.0)
        spectrum = np.abs(np.fft.rfft(x * np.hanning(len(x))))
        pitch = np.argmax(spectrum) * SR / len(x)
        peak = np.abs(x).max()
        print(f"{name:12s} pitch {pitch:6.1f} Hz   peak {peak:.2f}")
        assert name in UNPITCHED or abs(pitch - 440) / 440 < 0.015, f"{name} is out of tune"
        assert 0.5 < peak <= 1.05, f"{name} volume is off"
    song = render([(0.0, 60, 0.5, "piano"), (0.25, 64, 1.0, "organ")])
    assert len(song) == int((1.25 + RELEASE) * SR) + 1 and np.abs(song).max() <= 0.99
    bar = metronome_bar(120)  # 4 beats at 120 bpm = 2 s, with a click at the start of each beat.
    assert len(bar) == 2 * SR and bar[1] != 0 and bar[SR // 2 + 1] != 0 and bar[SR // 4] == 0
    print("ok")
