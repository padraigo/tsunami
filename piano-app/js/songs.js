// songs.js — built-in practice pieces.
// Each song is a flat list of notes; bar lines are derived from the time
// signature so the data stays simple to author. Durations use VexFlow codes
// (w, h, q, 8, 16, dotted with "d", rests with trailing "r").
//
// A note: { keys: ["c/4"], duration: "q" }  (keys is an array to allow chords;
// for melodies it's a single element). Rests use any key + a "...r" duration.

const SONGS = [
  {
    id: 'twinkle',
    title: 'Twinkle, Twinkle, Little Star',
    clef: 'treble',
    keySignature: 'C',
    timeSignature: [4, 4],
    tempo: 100,
    notes: [
      { keys: ['c/4'], duration: 'q' }, { keys: ['c/4'], duration: 'q' },
      { keys: ['g/4'], duration: 'q' }, { keys: ['g/4'], duration: 'q' },
      { keys: ['a/4'], duration: 'q' }, { keys: ['a/4'], duration: 'q' },
      { keys: ['g/4'], duration: 'h' },
      { keys: ['f/4'], duration: 'q' }, { keys: ['f/4'], duration: 'q' },
      { keys: ['e/4'], duration: 'q' }, { keys: ['e/4'], duration: 'q' },
      { keys: ['d/4'], duration: 'q' }, { keys: ['d/4'], duration: 'q' },
      { keys: ['c/4'], duration: 'h' },
      { keys: ['g/4'], duration: 'q' }, { keys: ['g/4'], duration: 'q' },
      { keys: ['f/4'], duration: 'q' }, { keys: ['f/4'], duration: 'q' },
      { keys: ['e/4'], duration: 'q' }, { keys: ['e/4'], duration: 'q' },
      { keys: ['d/4'], duration: 'h' },
      { keys: ['g/4'], duration: 'q' }, { keys: ['g/4'], duration: 'q' },
      { keys: ['f/4'], duration: 'q' }, { keys: ['f/4'], duration: 'q' },
      { keys: ['e/4'], duration: 'q' }, { keys: ['e/4'], duration: 'q' },
      { keys: ['d/4'], duration: 'h' },
      { keys: ['c/4'], duration: 'q' }, { keys: ['c/4'], duration: 'q' },
      { keys: ['g/4'], duration: 'q' }, { keys: ['g/4'], duration: 'q' },
      { keys: ['a/4'], duration: 'q' }, { keys: ['a/4'], duration: 'q' },
      { keys: ['g/4'], duration: 'h' },
      { keys: ['f/4'], duration: 'q' }, { keys: ['f/4'], duration: 'q' },
      { keys: ['e/4'], duration: 'q' }, { keys: ['e/4'], duration: 'q' },
      { keys: ['d/4'], duration: 'q' }, { keys: ['d/4'], duration: 'q' },
      { keys: ['c/4'], duration: 'h' },
    ],
  },
  {
    id: 'ode-to-joy',
    title: 'Ode to Joy (Beethoven)',
    clef: 'treble',
    keySignature: 'C',
    timeSignature: [4, 4],
    tempo: 120,
    notes: [
      { keys: ['e/4'], duration: 'q' }, { keys: ['e/4'], duration: 'q' },
      { keys: ['f/4'], duration: 'q' }, { keys: ['g/4'], duration: 'q' },
      { keys: ['g/4'], duration: 'q' }, { keys: ['f/4'], duration: 'q' },
      { keys: ['e/4'], duration: 'q' }, { keys: ['d/4'], duration: 'q' },
      { keys: ['c/4'], duration: 'q' }, { keys: ['c/4'], duration: 'q' },
      { keys: ['d/4'], duration: 'q' }, { keys: ['e/4'], duration: 'q' },
      { keys: ['e/4'], duration: 'qd' }, { keys: ['d/4'], duration: '8' },
      { keys: ['d/4'], duration: 'h' },
      { keys: ['e/4'], duration: 'q' }, { keys: ['e/4'], duration: 'q' },
      { keys: ['f/4'], duration: 'q' }, { keys: ['g/4'], duration: 'q' },
      { keys: ['g/4'], duration: 'q' }, { keys: ['f/4'], duration: 'q' },
      { keys: ['e/4'], duration: 'q' }, { keys: ['d/4'], duration: 'q' },
      { keys: ['c/4'], duration: 'q' }, { keys: ['c/4'], duration: 'q' },
      { keys: ['d/4'], duration: 'q' }, { keys: ['e/4'], duration: 'q' },
      { keys: ['d/4'], duration: 'qd' }, { keys: ['c/4'], duration: '8' },
      { keys: ['c/4'], duration: 'h' },
    ],
  },
  {
    id: 'c-major-scale',
    title: 'C Major Scale (note values demo)',
    clef: 'treble',
    keySignature: 'C',
    timeSignature: [4, 4],
    tempo: 90,
    notes: [
      { keys: ['c/4'], duration: 'w' },
      { keys: ['d/4'], duration: 'h' }, { keys: ['e/4'], duration: 'h' },
      { keys: ['f/4'], duration: 'q' }, { keys: ['g/4'], duration: 'q' },
      { keys: ['a/4'], duration: 'q' }, { keys: ['b/4'], duration: 'q' },
      { keys: ['c/5'], duration: '8' }, { keys: ['b/4'], duration: '8' },
      { keys: ['a/4'], duration: '8' }, { keys: ['g/4'], duration: '8' },
      { keys: ['f/4'], duration: '8' }, { keys: ['e/4'], duration: '8' },
      { keys: ['d/4'], duration: '8' }, { keys: ['c/4'], duration: '8' },
      { keys: ['c/4'], duration: 'h' }, { keys: ['c/4'], duration: 'hr' },
    ],
  },
];

window.SONGS = SONGS;
