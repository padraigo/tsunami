// music.js — core music theory model: pitches, durations, MIDI/frequency math.
// Pure, framework-free. Shared by notation, audio, pitch-detection and scoring.

const PITCH_CLASS = {
  c: 0, d: 2, e: 4, f: 5, g: 7, a: 9, b: 11,
};

// Map a VexFlow-style key ("c#/4", "eb/5", "f/4") to a MIDI note number.
// Returns null for unpitched tokens (e.g. rests).
function keyToMidi(key) {
  if (!key) return null;
  const m = String(key).trim().toLowerCase().match(/^([a-g])(#{1,2}|b{1,2}|n)?\/(-?\d+)$/);
  if (!m) return null;
  const [, letter, accidental, octaveStr] = m;
  let semitone = PITCH_CLASS[letter];
  if (accidental === '#') semitone += 1;
  else if (accidental === '##') semitone += 2;
  else if (accidental === 'b') semitone -= 1;
  else if (accidental === 'bb') semitone -= 2;
  const octave = parseInt(octaveStr, 10);
  // MIDI: C4 = 60, so midi = 12 * (octave + 1) + semitone.
  return 12 * (octave + 1) + semitone;
}

// MIDI note number -> frequency in Hz (A4 = 69 = 440 Hz, equal temperament).
function midiToFreq(midi) {
  return 440 * Math.pow(2, (midi - 69) / 12);
}

// Frequency in Hz -> nearest (possibly fractional) MIDI note number.
function freqToMidi(freq) {
  return 69 + 12 * Math.log2(freq / 440);
}

const NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'];

// MIDI number -> human-readable name like "A4".
function midiToName(midi) {
  const rounded = Math.round(midi);
  const name = NOTE_NAMES[((rounded % 12) + 12) % 12];
  const octave = Math.floor(rounded / 12) - 1;
  return `${name}${octave}`;
}

// Convert a VexFlow key ("c/4") directly to frequency. null if unpitched.
function keyToFreq(key) {
  const midi = keyToMidi(key);
  return midi == null ? null : midiToFreq(midi);
}

// Beat value (in quarter-note beats) for a VexFlow duration code.
// "w"=whole(4), "h"=half(2), "q"=quarter(1), "8"=eighth(0.5), "16"=sixteenth,
// "32"=thirty-second. A trailing "d" dots the note (x1.5), "dd" double-dots.
// A trailing "r" marks a rest and is ignored for the beat math.
const BASE_BEATS = { w: 4, h: 2, q: 1, 8: 0.5, 16: 0.25, 32: 0.125 };

function durationToBeats(duration) {
  const clean = String(duration).replace('r', '');
  const dots = (clean.match(/d/g) || []).length;
  const base = clean.replace(/d/g, '');
  let beats = BASE_BEATS[base];
  if (beats == null) beats = 1;
  // Each dot adds half of the previous increment: x1.5, x1.75, ...
  let increment = beats / 2;
  for (let i = 0; i < dots; i++) {
    beats += increment;
    increment /= 2;
  }
  return beats;
}

function isRest(duration) {
  return String(duration).includes('r');
}

// Duration of one quarter-note beat in seconds at a given tempo.
function beatSeconds(bpm) {
  return 60 / bpm;
}

// Expose on a global namespace so plain <script> tags can share it.
window.Music = {
  keyToMidi,
  midiToFreq,
  freqToMidi,
  midiToName,
  keyToFreq,
  durationToBeats,
  isRest,
  beatSeconds,
  NOTE_NAMES,
};
