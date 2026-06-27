// scorer.js — grade a student's performance against the expected schedule.
//
// During practice the app records {t, midi} samples from the pitch detector
// (t = seconds since the performance started). After the run we align those
// samples to each expected note's time window and judge pitch accuracy.

(function () {
  const Music = window.Music;

  // Build per-note time windows (seconds) from a schedule at a given tempo.
  function windows(schedule, bpm) {
    const spb = Music.beatSeconds(bpm);
    return schedule.map((item) => ({
      index: item.index,
      isRest: item.isRest,
      midi: item.midi,
      start: item.startBeat * spb,
      end: (item.startBeat + item.beats) * spb,
    }));
  }

  // The most common rounded MIDI among samples inside [start, end].
  // Returns { midi, support } where support is the fraction of in-window
  // samples agreeing (within ±0.6 semitone) with that pitch.
  function dominantPitch(samples, start, end) {
    const inWindow = samples.filter((s) => s.t >= start && s.t < end);
    if (!inWindow.length) return null;
    const counts = new Map();
    for (const s of inWindow) {
      const r = Math.round(s.midi);
      counts.set(r, (counts.get(r) || 0) + 1);
    }
    let best = null;
    let bestCount = 0;
    for (const [midi, count] of counts) {
      if (count > bestCount) { bestCount = count; best = midi; }
    }
    return { midi: best, support: bestCount / inWindow.length, count: inWindow.length };
  }

  // Grade the whole performance.
  // tolerance = allowed pitch error in semitones (default 1 → a half step).
  function grade(schedule, bpm, samples, tolerance = 1) {
    const wins = windows(schedule, bpm);
    const results = [];
    let scored = 0;
    let correct = 0;

    for (const w of wins) {
      if (w.isRest) {
        results.push({ index: w.index, status: 'rest' });
        continue;
      }
      scored++;
      const dom = dominantPitch(samples, w.start, w.end);
      if (!dom || dom.count === 0) {
        results.push({ index: w.index, status: 'missed', detected: null });
        continue;
      }
      const err = Math.abs(dom.midi - w.midi);
      // Allow octave-agnostic credit at half weight could be added; keep strict.
      if (err <= tolerance && dom.support >= 0.4) {
        correct++;
        results.push({
          index: w.index, status: 'correct',
          detected: dom.midi, expected: w.midi,
        });
      } else {
        results.push({
          index: w.index, status: 'wrong',
          detected: dom.midi, expected: w.midi,
        });
      }
    }

    const accuracy = scored ? Math.round((correct / scored) * 100) : 0;
    return { accuracy, correct, scored, results };
  }

  // Map grade results to a colour table for notation highlighting.
  function colorsFromResults(results) {
    const colors = {};
    for (const r of results) {
      if (r.status === 'correct') colors[r.index] = '#2f9e44';
      else if (r.status === 'wrong') colors[r.index] = '#e03131';
      else if (r.status === 'missed') colors[r.index] = '#adb5bd';
    }
    return colors;
  }

  // A friendly verbal rating from a numeric accuracy.
  function rating(accuracy) {
    if (accuracy >= 95) return { label: 'Virtuoso! ★★★★★', stars: 5 };
    if (accuracy >= 85) return { label: 'Excellent ★★★★', stars: 4 };
    if (accuracy >= 70) return { label: 'Good ★★★', stars: 3 };
    if (accuracy >= 50) return { label: 'Keep practicing ★★', stars: 2 };
    if (accuracy > 0) return { label: 'Needs work ★', stars: 1 };
    return { label: 'No notes detected', stars: 0 };
  }

  window.Scorer = { grade, colorsFromResults, rating, windows };
})();
