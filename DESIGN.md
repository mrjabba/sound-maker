---
name: sound-maker
description: A one-window desktop synth where every note rises from the keys as a bar in its family's color.
colors:
  keys-amber: "#f2a541"
  strings-vermilion: "#e4572e"
  winds-teal: "#4fb0c6"
  brass-gold: "#c9b458"
  perc-green: "#8fbf5a"
  rec-red: "#ff5a4e"
  graphite-ground: "#17191d"
  graphite-panel: "#1d2025"
  graphite-lane: "#23262c"
  black-lane: "#131519"
  grid-line: "#2c3038"
  bar-line: "#404550"
  ink: "#e8e6e1"
  dim: "#8a8d96"
  faint: "#525660"
  ivory: "#e8e6e1"
  ebony: "#0c0d10"
typography:
  label:
    fontFamily: "Barlow Semi Condensed"
    fontSize: "15px"
    fontWeight: 600
  label-small:
    fontFamily: "Barlow Semi Condensed"
    fontSize: "14px"
    fontWeight: 600
  body:
    fontFamily: "Barlow Semi Condensed"
    fontSize: "14px"
    fontWeight: 500
  hint:
    fontFamily: "Barlow Semi Condensed"
    fontSize: "16px"
    fontWeight: 500
rounded:
  underline: "1px"
  bar: "3px"
  key: "4px"
  control: "6px"
spacing:
  gap: "4px"
  inset: "12px"
  margin: "16px"
components:
  button:
    backgroundColor: "{colors.graphite-lane}"
    textColor: "{colors.ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    height: "36px"
  button-disabled:
    backgroundColor: "{colors.graphite-lane}"
    textColor: "{colors.faint}"
  button-record-stop:
    backgroundColor: "#5c2224"
    textColor: "{colors.ink}"
  family-tab:
    backgroundColor: "{colors.graphite-panel}"
    textColor: "{colors.dim}"
    typography: "{typography.label}"
    width: "74px"
    height: "36px"
  family-tab-active:
    backgroundColor: "{colors.graphite-lane}"
    textColor: "{colors.ink}"
  export-button:
    backgroundColor: "{colors.graphite-lane}"
    textColor: "{colors.ink}"
    typography: "{typography.label-small}"
    width: "52px"
    height: "36px"
  instrument:
    backgroundColor: "{colors.graphite-ground}"
    textColor: "{colors.dim}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    width: "122px"
  instrument-selected:
    backgroundColor: "{colors.keys-amber}"
    textColor: "{colors.graphite-ground}"
  key-white:
    backgroundColor: "{colors.ivory}"
    textColor: "{colors.graphite-ground}"
    rounded: "{rounded.key}"
  key-black:
    backgroundColor: "{colors.ebony}"
    textColor: "{colors.ink}"
    rounded: "{rounded.key}"
    height: "94px"
  status-bar:
    backgroundColor: "{colors.graphite-panel}"
    textColor: "{colors.dim}"
    typography: "{typography.body}"
---

# Design System: sound-maker

All values live as constants and draw helpers at the top of `app.py` (the "look" and "drawing helpers" sections). This file describes them. If the two disagree, `app.py` is right and this file needs updating.

## Overview

**Creative North Star: "Notes You Can See"**

The window is a dark graphite instrument for playing in the evening with the lights low. The main area is the piano roll sitting on a full-width keyboard. Every note you play shows up as a bar in its family's color. The bar rises from the key, and its height matches how long you held the note. Everything else stays grey and quiet so the bars are the only bright things on screen.

It is dense and flat. One small window (1000x720) holds the whole loop: a top strip for transport, families and exports, a row for instruments and octave, the roll over the keys, and a status line. There are no shadows, gradients, or decoration. Depth comes only from small steps between the greys.

**Key Characteristics:**
- Graphite greys for structure. The five family hues are the only colors.
- Flat filled rectangles with small corner radii.
- Barlow Semi Condensed everywhere, in two weights and a narrow size range (14 to 16px).
- Motion only where it carries meaning: bars rise, the grid scrolls with them, and the record dot pulses.

## Colors

The window is graphite and grey. Five family hues and one transport red are the only saturated colors.

### Primary (family hues)
- **Keys Amber**: Keys & plucked family.
- **Strings Vermilion**: Strings family.
- **Winds Teal**: Woodwinds family.
- **Brass Gold**: Brass family.
- **Perc Green**: Percussion family.

The current family's hue fills the selected instrument and draws its tab underline. Every bar and lit key takes the hue of the instrument that played it, so a take that mixes families shows several hues at once.

### Secondary
- **Rec Red**: used only for the transport. It is the record dot, which pulses while recording, and a 3px rule along the top of the keys while recording. The Stop button sits on a dark red fill (`#5c2224`).

### Neutral
- **Graphite Ground**: the window background, unselected instrument buttons, and the text color on lit keys and the selected instrument.
- **Graphite Panel**: the top strip, the status bar, and inactive family tabs.
- **Graphite Lane**: buttons and the roll surface, one step lighter than the ground.
- **Black Lane**: the darker strip of roll above each black key, also the 2px outline around every bar.
- **Grid Line**: beat lines and the lane edges at E|F and B|C.
- **Bar Line**: every fourth beat, slightly brighter than the beat lines.
- **Ink**: main text. **Dim**: secondary text, unselected labels, and the status message. **Faint**: labels on disabled controls and the Trim light when off.
- **Ivory / Ebony**: white and black piano keys.

### Named Rules
**The Family Owns the Color Rule.** A saturated color must mean a family. The only places hues appear are the tabs, the selected instrument, bars, and lit keys. New features use greys unless they show which family something belongs to.

**The One Red Rule.** Rec Red is the only color outside the family hues, and it means "recording now". Don't use it for errors, warnings, or emphasis.

**The Muted Hairline Rule.** An inactive family tab gets a 1px hairline in its hue mixed 50/50 with Graphite Panel. The active tab gets a 4px underline at full strength. This lets you see every family's color at a glance without the inactive tabs competing with the active one.

## Typography

**Font:** Barlow Semi Condensed, bundled in `fonts/`. Medium is loaded as `"ui"` and SemiBold as `"bold"`.

**Character:** a narrow grotesque, so labels fit the tight control strip and stay readable at small sizes on a dark background.

**Retina rendering:** fonts are loaded at 30px with a global font scale of 0.5, then drawn at 14 to 16px. All sizes below are drawn sizes.

### Hierarchy
- **Label** (SemiBold, 15px): button labels, family tabs, instrument names, the octave range, and note names on the keys.
- **Label Small** (SemiBold, 14px): export labels, Trim, and the keyboard-letter hint on each key.
- **Body** (Medium, 14px): the status line and the live readout.
- **Hint** (Medium, 16px): the one-line prompt in the empty roll, before the first note.

### Named Rules
**The Narrow Ramp Rule.** Text is drawn at 14, 15, or 16px, and hierarchy comes from weight and color (Ink, Dim, Faint), not size. The window has no headings.

## Layout

The window is a fixed 1000x720 canvas with absolute pixel boxes (left, top, right, bottom), stacked top to bottom:

1. **Top strip** (64px, Panel): Record, Play, five family tabs, five exports, and Trim at the right edge. Controls are 36px tall at y 14 to 50.
2. **Instrument row** (44px): one button per instrument in the current family (122px wide on a 128px pitch), with the octave control (down, range, up) on the right.
3. **Roll**: fills the space between the instrument row and the keys, inset 16px from each side.
4. **Keys** (152px tall): 8 white keys across the roll's full width, and 5 black keys (60% of a white key's width, 94px tall) centered on the white-key seams.
5. **Status bar** (Panel): the hover help or status message on the left, then the readout.

The outer margin is 16px. Text sits 12px in from a box edge when aligned left or right. Exports are spaced 4px apart. The roll's lanes line up exactly with the keys below them.

**The Fixed Anchor Rule.** Readout segments start at fixed x positions (note at W−400, take at W−290, BPM right-aligned), so ticking numbers never shift the line.

## Elevation & Depth

None. There are no shadows or gradients. Depth comes from the grey steps: Black Lane < Ground < Panel < Lane, and buttons lighten on hover. Draw order handles overlap: white keys before black keys, and white-key bars before black-key bars.

**The Flat Fill Rule.** Every element is a solid filled rectangle, circle, triangle, or line. Don't add a shadow, glow, or gradient to make something stand out. Use color or a lighter grey step instead.

## Shapes

Small, consistent radii: 6px on buttons and instrument chips, 4px on piano keys, 3px on bars, 1px on the active tab underline. Icons are drawn as geometry rather than glyphs: a circle for record, a triangle for Play and the octave arrows, two 2px lines for the export check mark, and a 3.5px dot for the Trim light. White keys are separated by a 2px Ground line.

## Components

### Buttons
Flat and quiet. All buttons go through one `button()` helper.
- **Shape:** 6px radius, 36px tall in the top strip.
- **States:** hover lightens the fill by 12 per RGB channel, pressing darkens it by 8. Disabled buttons keep their fill, ignore hover and press, and draw their label in Faint.
- **Help:** hovering a control with a `HELP` entry puts that sentence in the status bar (Ink) instead of the status message (Dim).
- **Record / Stop:** a red dot plus the label. While recording, the button becomes Stop on a dark red fill and the dot pulses (alpha 150 to 255, about 1 Hz).
- **Play:** a triangle plus the label. Disabled with no take, or while recording.

### Family Tabs
74px wide on a 78px pitch. Active: Lane fill, Ink label, 4px full-hue underline inset 8px. Inactive: Panel fill, Dim label, a muted 1px hairline inset 18px (see The Muted Hairline Rule). Labels are shortened: Keys, Strings, Winds, Brass, Perc.

### Exports
WAV, PY, TS, MID (52px) and SCORE (66px). Disabled until there is a finished take, and disabled again while recording. Each format saved from the current take gets a check mark after its label, drawn as lines and centered with the label. The checks stay until the next take.

### Trim Toggle
A plain button, not a switch: a small dot (Ink when on, Faint when off) and the label "Trim on" (Ink) or "Trim off" (Dim).

### Instrument Chips
Unselected: Ground fill, Dim label, normal hover. Selected: filled with the family hue, label in Ground.

### Piano Roll (signature)
- Lane surface in Graphite Lane, a Black Lane strip above each black key, and a Grid Line edge where two white keys touch with no black key between them.
- A beat grid at `BPM` that rises with the bars, so notes played on the beat line up with it. Every fourth line is Bar Line.
- A bar's top marks when the note started and its bottom when it ended. Both rise at `SPEED` (120 px/s). While a note is held, its bottom stays on the keys.
- Bars are inset 6px (white) or 4px (black) inside their lane, with a 3px radius and a 2px Black Lane outline. White-key bars are drawn first so black-key bars sit on top.
- While recording, a 3px Rec Red rule runs along the bottom edge of the roll, just above the keys.
- Before the first note, the roll shows a single Hint line in Dim.

### Keys
Ivory and Ebony, 4px radius. A key lights up in the sounding bar's hue while its note plays, from your own playing or the take playing back. Each key shows its keyboard letter (Label Small) above its note name (Label), placed 10px from the left edge.

## Do's and Don'ts

### Do:
- **Do** take every color from the constants at the top of `app.py`, and add new ones there with a comment saying where they're used.
- **Do** keep saturated color for family identity, and Rec Red for recording only.
- **Do** draw new controls with `button()` so they get the same hover, press, disabled, and help behavior.
- **Do** add a `HELP` sentence for every new control.
- **Do** dim a control (Faint label) when it can't be used, rather than hiding it.
- **Do** give live-updating text a fixed left edge.

### Don't:
- **Don't** add a sixth accent color for UI chrome such as selection, focus, or links. Selection is shown with Lane fill, Ink text, or the family hue.
- **Don't** use Rec Red for errors or warnings.
- **Don't** add shadows, glows, or gradients.
- **Don't** draw text below 14px or above 16px.
- **Don't** use font glyphs for icons. Draw them with the circle, triangle, and line helpers.
