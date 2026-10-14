// instruments.ts: the sound-maker instruments ported from synth.py, so a take
// exported as .ts plays in TypeScript with no audio files or libraries.
//
//   import { renderWav, type Note } from './instruments'
//   const bytes = renderWav([{ at: 0, midi: 60, held: 0.5, instrument: 'piano' }])
//
// Built in the same style as sound-samples.ts: an instrument is
// (freq, seconds) => number[] of samples, and renderWav() returns WAV file bytes.
// If you change an instrument in synth.py, make the same change here.
// The noise in guitar, harp, flute, snare and cymbals comes from a different random generator than in
// Python, so it won't match sample for sample, but it sounds the same.

export const RATE = 22050 // samples per second
const NOTE_GAIN = 0.3 // volume of one note, low enough that chords don't clip
const RELEASE = 0.15 // seconds a note fades out after its key is released

export type Instrument = keyof typeof INSTRUMENTS
export type Note = { at: number; midi: number; held: number; instrument: Instrument }

// MIDI note number -> frequency. 69 is A4 (440 Hz), 60 is middle C.
export const hz = (midi: number): number => 440 * 2 ** ((midi - 69) / 12)

// A small seeded random generator (mulberry32). It gives the same "random" pluck each time.
function random(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

// Calls fn(time in seconds) once per sample and collects the results.
const samples = (seconds: number, fn: (t: number) => number): number[] =>
  Array.from({ length: Math.floor(seconds * RATE) }, (_, i) => fn(i / RATE))

// The recipe most instruments share: sine waves at freq * ratio, each at its level, with
// a vibrato that fades in over 0.4 s and an optional fade-out (decay per second).
// Dividing by the sum of the levels keeps the peak at or below 1.
const partials = (freq: number, seconds: number, parts: number[][], attack: number, vibrato = 0, rate = 5, decay = 0): number[] => {
  const total = parts.reduce((sum, [, level]) => sum + level!, 0)
  let phase = 0
  return samples(seconds, t => {
    phase += (freq * (1 + vibrato * Math.min(1, t / 0.4) * Math.sin(2 * Math.PI * rate * t))) / RATE
    let sum = 0
    for (const [ratio, level] of parts) sum += level! * Math.sin(2 * Math.PI * ratio! * phase)
    return (Math.min(1, t / attack) * Math.exp(-decay * t) * sum) / total
  })
}

// Levels for harmonics 1, 2, 3... -> [ratio, level] pairs for partials().
const harmonics = (...levels: number[]): number[][] => levels.map((level, i) => [i + 1, level])
// Bowed strings: harmonic k at level k^-power, a sawtooth when power is 1.
const bowed = (power: number, count: number): number[][] => Array.from({ length: count }, (_, i) => [i + 1, (i + 1) ** -power])

// A struck string: slightly sharp harmonics, with the upper ones fading faster.
export const piano = (freq: number, seconds: number): number[] =>
  samples(seconds, t => {
    let sum = 0
    for (let k = 1; k <= 7; k++)
      sum += (Math.exp(-t * (1.6 + k * 1.4)) / k ** 1.2) * Math.sin(2 * Math.PI * freq * k * Math.sqrt(1 + 0.0004 * k * k) * t)
    return (Math.min(1, t / 0.0025) * sum) / 1.7
  })

// Tonewheel organ: fixed sine drawbars, a quick key click, and a slow Leslie wobble.
export const organ = (freq: number, seconds: number): number[] => {
  const drawbars = [[0.5, 0.5], [1, 1], [2, 0.6], [3, 0.4], [4, 0.3], [6, 0.15]]
  return samples(seconds, t => {
    let sum = 0
    for (const [h, level] of drawbars) sum += level! * Math.sin(2 * Math.PI * freq * h! * t)
    return (Math.min(1, t / 0.005) * (1 + 0.08 * Math.sin(2 * Math.PI * 6 * t)) * sum) / 2.05
  })
}

// Plucked string (Karplus-Strong). It starts with one period of noise, then replays
// that period, averaging each sample with its neighbour so it mellows and dies away.
// loss (just under 1) sets how long it rings, and noise how bright the pluck is.
const pluck = (freq: number, seconds: number, loss: number, noise: number): number[] => {
  const n = Math.floor(seconds * RATE)
  const period = Math.max(2, Math.round(RATE / freq - 0.5))
  const rand = random(Math.floor(freq))
  const out = new Array<number>(n + period).fill(0)
  let mean = 0
  for (let i = 0; i < period; i++) {
    const shape = 1 - 2 * Math.abs(-1 + (2 * i) / (period - 1)) // the string pulled into a triangle
    out[i] = (1 - noise) * shape + noise * (rand() * 2 - 1) // plus noise for the bright "pick"
    mean += out[i]! / period
  }
  let peak = 0
  for (let i = 0; i < period; i++) peak = Math.max(peak, Math.abs((out[i]! -= mean)))
  for (let i = period; i < n + period; i++) out[i] = loss * 0.5 * (out[i - period]! + (out[i - period - 1] ?? 0))
  return out.slice(0, n).map(s => s / peak) // the pluck is the loudest moment
}
export const guitar = (freq: number, seconds: number) => pluck(freq, seconds, 0.996, 0.3)
export const harp = (freq: number, seconds: number) => pluck(freq, seconds, 0.998, 0.1)

// Brass buzz: a sawtooth that opens from muffled to bright, with vibrato fading in.
export const trumpet = (freq: number, seconds: number): number[] => {
  let phase = 0
  return samples(seconds, t => {
    phase += (freq * (1 + 0.006 * Math.min(1, t / 0.4) * Math.sin(2 * Math.PI * 5.5 * t))) / RATE
    const brightness = 2 + 6 * Math.min(1, t / 0.08)
    let sum = 0
    for (let k = 1; k <= 14; k++) sum += (Math.sin(2 * Math.PI * k * phase) / k) * Math.exp(-((k / brightness) ** 2))
    return (Math.min(1, t / 0.03) * sum) / 1.4
  })
}

// Almost a pure sine wave, with breath noise (stronger at the start) and a gentle vibrato.
export const flute = (freq: number, seconds: number): number[] => {
  const rand = random(Math.floor(freq))
  let phase = 0
  let breath = 0
  return samples(seconds, t => {
    phase += (freq * (1 + 0.004 * Math.min(1, t / 0.5) * Math.sin(2 * Math.PI * 5 * t))) / RATE
    breath += ((rand() * 2 - 1) - breath) / 8 // smoothed (low-passed) noise
    const tone = Math.sin(2 * Math.PI * phase) + 0.25 * Math.sin(4 * Math.PI * phase) + 0.08 * Math.sin(6 * Math.PI * phase)
    return (Math.min(1, t / 0.08) * (tone + (0.1 + 0.25 * Math.exp(-t * 12)) * breath * 1.4)) / 1.3
  })
}

// Woodwinds and brass: mixes of harmonics, same numbers as synth.py.
type Fn = (freq: number, seconds: number) => number[]
export const oboe: Fn = (f, s) => partials(f, s, harmonics(1, 0.9, 0.8, 0.6, 0.45, 0.3, 0.2, 0.15), 0.04, 0.005, 5)
export const clarinet: Fn = (f, s) => partials(f, s, harmonics(1, 0.05, 0.45, 0.04, 0.25, 0.03, 0.12, 0, 0.06), 0.04, 0.002, 5)
export const bassoon: Fn = (f, s) => partials(f, s, harmonics(1, 0.8, 0.6, 0.4, 0.25, 0.12, 0.06), 0.05, 0.003, 5)
export const saxophone: Fn = (f, s) => partials(f, s, harmonics(1, 0.8, 0.65, 0.5, 0.4, 0.3, 0.25, 0.2, 0.15, 0.1), 0.03, 0.006, 5.5)
export const french_horn: Fn = (f, s) => partials(f, s, harmonics(1, 0.5, 0.25, 0.12, 0.06), 0.06, 0.002, 5)
export const trombone: Fn = (f, s) => partials(f, s, harmonics(1, 0.7, 0.5, 0.35, 0.25, 0.15, 0.1), 0.05, 0.002, 5)
export const tuba: Fn = (f, s) => partials(f, s, harmonics(1, 0.45, 0.2, 0.08), 0.06)

// Bowed strings: the bigger the instrument, the darker, slower to start, and slower the vibrato.
export const violin: Fn = (f, s) => partials(f, s, bowed(1.0, 12), 0.08, 0.007, 5.5)
export const viola: Fn = (f, s) => partials(f, s, bowed(1.2, 10), 0.09, 0.006, 5.2)
export const cello: Fn = (f, s) => partials(f, s, bowed(1.3, 10), 0.1, 0.006, 5)
export const double_bass: Fn = (f, s) => partials(f, s, bowed(1.5, 8), 0.12, 0.004, 4.5)

// Percussion: struck, so everything fades. Drums and bars have non-whole-number overtones.
export const timpani: Fn = (f, s) => partials(f, s, [[1, 1], [1.5, 0.5], [1.98, 0.3], [2.44, 0.15]], 0.003, 0, 5, 1.8)
export const xylophone: Fn = (f, s) => partials(f, s, [[1, 1], [3.93, 0.35], [9.36, 0.1]], 0.001, 0, 5, 7)

// Noise (the snare wires) over a quick thump (the drum head) tuned by the key.
export const snare_drum: Fn = (freq, seconds) => {
  const rand = random(Math.floor(freq))
  return samples(seconds, t =>
    (Math.min(1, t / 0.001) * (0.7 * (rand() * 2 - 1) * Math.exp(-t * 18) + 0.5 * Math.sin(2 * Math.PI * freq * t) * Math.exp(-t * 30))) / 1.15)
}

// A crash: noise minus its smoothed self (only the highs), ringing longer on lower keys.
export const cymbals: Fn = (freq, seconds) => {
  const rand = random(Math.floor(freq))
  let smooth = 0
  return samples(seconds, t => {
    const x = rand() * 2 - 1
    smooth += (x - smooth) / 2.5
    return (Math.min(1, t / 0.002) * Math.exp((-t * freq) / 300) * (x - smooth)) / 1.35
  })
}

// Same names and order as synth.FAMILIES.
export const INSTRUMENTS = {
  piano, organ, guitar, harp,
  violin, viola, cello, double_bass,
  flute, oboe, clarinet, bassoon, saxophone,
  trumpet, french_horn, trombone, tuba,
  timpani, snare_drum, cymbals, xylophone,
} satisfies Record<string, Fn>

// Mix notes into one buffer. Each note plays for `held` seconds, then fades out over RELEASE.
export function render(notes: Note[]): number[] {
  const end = Math.max(0, ...notes.map(n => n.at + n.held + RELEASE))
  const out = new Array<number>(Math.floor(end * RATE) + 1).fill(0)
  const r = Math.floor(RELEASE * RATE)
  for (const { at, midi, held, instrument } of notes) {
    const s = INSTRUMENTS[instrument](hz(midi), held + RELEASE)
    const start = Math.floor(at * RATE)
    s.forEach((v, i) => {
      const fade = Math.min(1, (s.length - i) / r) // ramps from 1 to 0 over the last RELEASE seconds
      if (start + i < out.length) out[start + i]! += v * NOTE_GAIN * fade
    })
  }
  const peak = out.reduce((m, v) => Math.max(m, Math.abs(v)), 0)
  return peak > 0.99 ? out.map(v => (v * 0.99) / peak) : out // only turn it down, and only if it would clip
}

// Samples -> 16-bit mono WAV file bytes. Same format as pcm() in sound-samples.ts.
export function wav(samples: number[]): Uint8Array {
  const out = new DataView(new ArrayBuffer(44 + samples.length * 2))
  const text = (at: number, s: string) => [...s].forEach((c, i) => out.setUint8(at + i, c.charCodeAt(0)))
  text(0, 'RIFF')
  out.setUint32(4, 36 + samples.length * 2, true)
  text(8, 'WAVEfmt ')
  out.setUint32(16, 16, true) // size of the format block
  out.setUint16(20, 1, true) // 1 = plain PCM
  out.setUint16(22, 1, true) // mono
  out.setUint32(24, RATE, true)
  out.setUint32(28, RATE * 2, true) // bytes per second
  out.setUint16(32, 2, true) // bytes per sample
  out.setUint16(34, 16, true) // bits per sample
  text(36, 'data')
  out.setUint32(40, samples.length * 2, true)
  samples.forEach((s, i) => out.setInt16(44 + i * 2, Math.round(Math.max(-1, Math.min(1, s)) * 32767), true))
  return new Uint8Array(out.buffer)
}

export const renderWav = (notes: Note[]): Uint8Array => wav(render(notes))
