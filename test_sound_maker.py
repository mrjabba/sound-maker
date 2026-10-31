"""
Tests. Run:  python -m unittest -v
They don't open the window. The two built-in self-checks (python synth.py,
python notation.py) run here too.
"""
import os
import runpy
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pygame.midi

import app
import notation

HERE = Path(__file__).resolve().parent


def read_midi_file(data):
    """Just enough of a MIDI reader to check midi_bytes: header fields and each track's
    events as (absolute tick, raw message bytes)."""
    assert data[:4] == b"MThd"
    _, fmt, count, ticks = struct.unpack(">IHHH", data[4:14])
    tracks, i = [], 14
    while i < len(data):
        assert data[i:i + 4] == b"MTrk"
        (length,) = struct.unpack(">I", data[i + 4:i + 8])
        body, i = data[i + 8:i + 8 + length], i + 8 + length
        events, j, tick = [], 0, 0
        while j < len(body):
            delta = 0
            while True:
                delta = (delta << 7) | (body[j] & 0x7F)
                j += 1
                if body[j - 1] < 0x80:
                    break
            tick += delta
            if body[j] == 0xFF:  # Meta event: FF type length data.
                size = 3 + body[j + 2]
            else:  # Note on / off are 3 bytes, program change 2.
                size = 2 if body[j] & 0xF0 == 0xC0 else 3
            events.append((tick, body[j:j + size]))
            j += size
        tracks.append(events)
    assert i == len(data), "track lengths don't add up to the file size"
    return fmt, count, ticks, tracks


class SelfChecks(unittest.TestCase):
    def test_synth_self_check(self):
        runpy.run_path(str(HERE / "synth.py"), run_name="__main__")

    def test_notation_self_check(self):
        runpy.run_path(str(HERE / "notation.py"), run_name="__main__")


class Midi(unittest.TestCase):
    def test_file_structure_tempo_and_timing(self):
        take = [(0.5, 60, 0.5, "cello"), (1.0, 50, 0.25, "snare_drum")]
        fmt, count, ticks, tracks = read_midi_file(notation.midi_bytes(take, 120))
        self.assertEqual((fmt, count, ticks), (1, 3, 480))
        tempo = next(m for _, m in tracks[0] if m[:2] == b"\xff\x51")
        self.assertEqual(int.from_bytes(tempo[3:], "big"), 500_000)  # 120 bpm = 0.5 s per beat.
        for events in tracks:
            self.assertEqual(events[-1][1], b"\xff\x2f\x00")  # Every track ends with End of Track.
        cello = [(t, m) for t, m in tracks[1] if m[0] & 0xF0 in (0x80, 0x90)]
        self.assertEqual(cello[0][0], 480)  # 0.5 s at 120 bpm is one beat.
        self.assertEqual(cello[1][0], 960)
        self.assertEqual(cello[0][1][1], 60)
        drum_on = next(m for _, m in tracks[2] if m[0] & 0xF0 == 0x90)
        self.assertEqual((drum_on[0] & 0x0F, drum_on[1]), (9, 38))  # Drum channel, snare key.


class Trim(unittest.TestCase):
    def test_trim_start_moves_first_note_to_zero(self):
        take = [(1.5, 60, 0.2, "piano"), (2.0, 62, 0.2, "piano")]
        self.assertEqual([n[0] for n in app.trim_start(take)], [0.0, 0.5])

    def test_trim_to_bar_drops_whole_bars_only(self):
        # 120 bpm: a bar is 2 s. A first note at 4.1 s is in bar 3, so 4 s are dropped.
        self.assertAlmostEqual(app.trim_to_bar([(4.1, 60, 0.2, "piano")], 120)[0][0], 0.1)

    def test_trim_to_bar_counts_a_slightly_early_note_in_the_next_bar(self):
        # 3.8 s is a quarter beat before bar 3, so it moves to 0, never below.
        self.assertAlmostEqual(app.trim_to_bar([(3.8, 60, 0.2, "piano")], 120)[0][0], 0.0)


class Exports(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.saved = app.HERE, app.OUT
        self.addCleanup(lambda: (setattr(app, "HERE", self.saved[0]), setattr(app, "OUT", self.saved[1])))
        app.s.take, app.s.rec_start, app.s.saved, app.s.later = [(0.0, 60, 0.3, "piano")], None, set(), None

    def test_python_export_runs_on_another_machine(self):
        # Exports land in <sound-maker>/recordings/. Fake that layout somewhere else.
        shutil.copy(HERE / "synth.py", self.tmp)
        path = self.tmp / "recordings" / "take_1.py"
        path.parent.mkdir()
        app.export_python([(0.0, 60, 0.3, "piano"), (0.25, 64, 0.3, "flute")], path)
        self.assertNotIn(str(HERE), path.read_text())  # No local folder names in shared files.
        subprocess.run([sys.executable, "-I", str(path)], check=True, cwd=self.tmp)
        self.assertTrue(path.with_suffix(".wav").stat().st_size > 1000)

    def test_export_reports_a_folder_it_cant_write(self):
        blocker = self.tmp / "file"
        blocker.write_text("")
        app.OUT = blocker / "recordings"  # Can't make a folder inside a file.
        app.export("midi")
        self.assertIn("Couldn't save", app.s.status)

    @unittest.skipUnless(shutil.which("lilypond"), "LilyPond isn't installed")
    def test_lilypond_compiles_every_kind_of_staff(self):
        take = [(0.0, 60, 0.5, "piano"), (0.0, 40, 1.0, "cello"), (0.5, 64, 0.5, "guitar"), (1.0, 60, 0.1, "snare_drum")]
        ly = self.tmp / "t.ly"
        ly.write_text(notation.lilypond(take, 100, "t"))
        done = subprocess.run(["lilypond", "-o", str(self.tmp / "t"), str(ly)], capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)


class Engrave(unittest.TestCase):
    """engrave() with a stand-in `lilypond` program first on PATH."""

    def fake_lilypond(self, script):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp)
        exe = tmp / "lilypond"
        exe.write_text("#!/bin/sh\n" + script + "\n")
        exe.chmod(0o755)
        old = os.environ["PATH"]
        os.environ["PATH"] = f"{tmp}{os.pathsep}{old}"
        self.addCleanup(os.environ.__setitem__, "PATH", old)
        return app.HERE / "recordings" / "never-written.ly"

    def test_failure_with_no_error_text(self):
        app.engrave(self.fake_lilypond("exit 3"))
        self.assertIn("LilyPond failed", app.s.status)

    def test_lilypond_that_hangs_times_out(self):
        old = getattr(app, "LILYPOND_TIMEOUT", None)
        app.LILYPOND_TIMEOUT = 0.5
        self.addCleanup(setattr, app, "LILYPOND_TIMEOUT", old)
        app.s.saved = set()
        app.engrave(self.fake_lilypond("sleep 5"))
        self.assertIn("stopped", app.s.status)
        self.assertNotIn("lily", app.s.saved)  # Not checked off as done.


class Unplugged:
    """A MIDI input whose keyboard was just unplugged."""

    def poll(self):
        raise pygame.midi.MidiException("Host error")

    def close(self):
        pass


class Playing(unittest.TestCase):
    def setUp(self):
        app.s.held, app.s.bars, app.s.rec_start, app.s.midi_in = {}, [], None, None

    def test_unplugged_midi_keyboard_disconnects_and_releases_its_notes(self):
        bar = [0, 0.0, None, (0, 0, 0)]
        app.s.held[("midi", 60)] = (60, None, 0.0, "piano", bar)
        app.s.midi_in = Unplugged()
        app.read_midi()
        self.assertIsNone(app.s.midi_in)
        self.assertEqual(app.s.held, {})
        self.assertIsNotNone(bar[2])  # Its bar ended.
        self.assertIn("disconnected", app.s.status)

    def test_note_with_no_free_mixer_channel_still_ends(self):
        # Sound.play() returns None when all 32 channels are busy.
        bar = [0, 0.0, None, (0, 0, 0)]
        app.s.held[0] = (60, None, 0.0, "piano", bar)
        app.note_off(0)
        self.assertIsNotNone(bar[2])


if __name__ == "__main__":
    unittest.main()
