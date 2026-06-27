// notation.js — render a song as engraved sheet music with VexFlow, and
// expose a flat note index so the rest of the app (audio, highlighting,
// scoring) can address individual notes.
//
// Depends on the global `Vex` (VexFlow 4, loaded via <script>) and window.Music.

(function () {
  const Music = window.Music;

  // Build the flat schedule of notes for a song: one entry per note in order,
  // with timing/pitch metadata. This is the canonical ordering used everywhere.
  function buildSchedule(song) {
    const schedule = [];
    let beatCursor = 0; // in quarter-note beats from the start of the piece
    song.notes.forEach((n, index) => {
      const beats = Music.durationToBeats(n.duration);
      const rest = Music.isRest(n.duration);
      const midi = rest ? null : Music.keyToMidi(n.keys[0]);
      schedule.push({
        index,
        keys: n.keys,
        duration: n.duration,
        beats,
        isRest: rest,
        midi,
        midis: rest ? [] : n.keys.map(Music.keyToMidi),
        startBeat: beatCursor,
      });
      beatCursor += beats;
    });
    return schedule;
  }

  // Quarter-note beats contained in one measure of the given time signature.
  function beatsPerMeasure(timeSignature) {
    const [num, den] = timeSignature;
    return (num * 4) / den;
  }

  // Group the flat schedule into measures so each renders as its own stave.
  function groupMeasures(schedule, timeSignature) {
    const perMeasure = beatsPerMeasure(timeSignature);
    const measures = [];
    let current = [];
    let acc = 0;
    const EPS = 1e-6;
    for (const item of schedule) {
      current.push(item);
      acc += item.beats;
      if (acc >= perMeasure - EPS) {
        measures.push(current);
        current = [];
        acc = 0;
      }
    }
    if (current.length) measures.push(current);
    return measures;
  }

  // Construct a VexFlow StaveNote for a scheduled note, applying accidentals,
  // dots, and an optional highlight colour.
  function makeStaveNote(VF, item, color) {
    const keys = item.isRest ? ['b/4'] : item.keys;
    const note = new VF.StaveNote({
      keys,
      duration: item.duration,
      clef: 'treble',
    });

    if (!item.isRest) {
      item.keys.forEach((key, i) => {
        const m = key.toLowerCase().match(/^[a-g](#{1,2}|b{1,2})/);
        if (m) {
          const acc = m[1].includes('#') ? (m[1].length === 2 ? '##' : '#')
            : (m[1].length === 2 ? 'bb' : 'b');
          note.addModifier(new VF.Accidental(acc), i);
        }
      });
    }

    const dots = (item.duration.replace('r', '').match(/d/g) || []).length;
    for (let i = 0; i < dots; i++) {
      VF.Dot.buildAndAttach([note], { all: true });
    }

    if (color) {
      note.setStyle({ fillStyle: color, strokeStyle: color });
    }
    return note;
  }

  // Render the whole song. `opts`:
  //   highlightIndex : flat index of the note to highlight (current beat)
  //   colors         : { [flatIndex]: cssColor } for scoring feedback
  function render(container, song, opts = {}) {
    const VF = Vex.Flow;
    const { highlightIndex = -1, colors = {} } = opts;

    container.innerHTML = '';
    const schedule = buildSchedule(song);
    const measures = groupMeasures(schedule, song.timeSignature);

    const width = Math.max(container.clientWidth || 800, 480);
    const measuresPerLine = width >= 760 ? 4 : 2;
    const lineHeight = 120;
    const leftPad = 10;
    const topPad = 10;
    const usableWidth = width - leftPad * 2;

    const lines = Math.ceil(measures.length / measuresPerLine);
    const renderer = new VF.Renderer(container, VF.Renderer.Backends.SVG);
    renderer.resize(width, topPad * 2 + lines * lineHeight);
    const context = renderer.getContext();

    measures.forEach((measure, mIdx) => {
      const lineIdx = Math.floor(mIdx / measuresPerLine);
      const posInLine = mIdx % measuresPerLine;
      const isFirstInLine = posInLine === 0;

      // The first stave on each line is wider to fit the clef/key/time glyphs.
      const firstExtra = 40;
      const baseWidth = usableWidth / measuresPerLine;
      const x = leftPad + posInLine * baseWidth + (isFirstInLine ? 0 : firstExtra / measuresPerLine);
      const staveWidth = baseWidth - (isFirstInLine ? 0 : firstExtra / measuresPerLine)
        + (isFirstInLine ? 0 : 0);
      const y = topPad + lineIdx * lineHeight;

      const stave = new VF.Stave(x, y, baseWidth);
      if (isFirstInLine) {
        stave.addClef(song.clef || 'treble');
        if (mIdx === 0) {
          if (song.keySignature && song.keySignature !== 'C') {
            stave.addKeySignature(song.keySignature);
          }
          stave.addTimeSignature(`${song.timeSignature[0]}/${song.timeSignature[1]}`);
        }
      }
      stave.setContext(context).draw();

      const staveNotes = measure.map((item) => {
        let color = colors[item.index] || null;
        if (item.index === highlightIndex) color = '#e8590c';
        return makeStaveNote(VF, item, color);
      });

      const voice = new VF.Voice({
        num_beats: beatsPerMeasure(song.timeSignature),
        beat_value: 4,
      }).setMode(VF.Voice.Mode.SOFT);
      voice.addTickables(staveNotes);

      // Auto-beam consecutive eighths/sixteenths where it makes sense.
      let beams = [];
      try {
        beams = VF.Beam.generateBeams(staveNotes);
      } catch (e) {
        beams = [];
      }

      new VF.Formatter()
        .joinVoices([voice])
        .format([voice], baseWidth - 20);
      voice.draw(context, stave);
      beams.forEach((b) => b.setContext(context).draw());
    });

    return schedule;
  }

  window.Notation = { render, buildSchedule, groupMeasures, beatsPerMeasure };
})();
