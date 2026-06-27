// app.js — UI controller wiring the song model, notation rendering, audio
// playback, metronome, microphone pitch detection and scoring together.

(function () {
  const Music = window.Music;
  const Notation = window.Notation;
  const Scorer = window.Scorer;

  const engine = new window.AudioEngine();
  const detector = new window.PitchDetector();

  // ----- DOM ---------------------------------------------------------------
  const el = (id) => document.getElementById(id);
  const sheet = el('sheet');
  const songSelect = el('song-select');
  const tempoRange = el('tempo');
  const tempoLabel = el('tempo-label');
  const metronomeToggle = el('metronome-toggle');
  const countInToggle = el('countin-toggle');
  const listenBtn = el('listen-btn');
  const practiceBtn = el('practice-btn');
  const stopBtn = el('stop-btn');
  const statusEl = el('status');
  const liveNote = el('live-note');
  const scorePanel = el('score-panel');

  // ----- State -------------------------------------------------------------
  let song = window.SONGS[0];
  let schedule = [];
  let bpm = song.tempo;
  let running = false;
  let rafId = null;
  let mode = null;          // 'listen' | 'practice'
  let perfStart = 0;        // ctx time when note beat 0 begins
  let samples = [];         // {t, midi} recorded during practice
  let lastColors = {};      // scoring colours to keep after a run

  function beatsPerBar() {
    return Notation.beatsPerMeasure(song.timeSignature);
  }

  function totalBeats() {
    if (!schedule.length) return 0;
    const last = schedule[schedule.length - 1];
    return last.startBeat + last.beats;
  }

  // ----- Rendering ---------------------------------------------------------
  function rerender(highlightIndex = -1, colors = lastColors) {
    schedule = Notation.render(sheet, song, { highlightIndex, colors });
  }

  function populateSongs() {
    window.SONGS.forEach((s, i) => {
      const opt = document.createElement('option');
      opt.value = String(i);
      opt.textContent = s.title;
      songSelect.appendChild(opt);
    });
  }

  function loadSong(index) {
    song = window.SONGS[index];
    bpm = song.tempo;
    tempoRange.value = String(bpm);
    tempoLabel.textContent = `${bpm} BPM`;
    lastColors = {};
    scorePanel.hidden = true;
    rerender();
  }

  // ----- Transport ---------------------------------------------------------
  function setRunning(state) {
    running = state;
    listenBtn.disabled = state;
    practiceBtn.disabled = state;
    songSelect.disabled = state;
    stopBtn.disabled = !state;
  }

  function stop() {
    running = false;
    mode = null;
    if (rafId) cancelAnimationFrame(rafId);
    rafId = null;
    engine.stopAll();
    detector.stop();
    setRunning(false);
    statusEl.textContent = 'Stopped.';
    liveNote.textContent = '';
    rerender(-1, lastColors);
  }

  // The animation loop: advance the highlight and (in practice) record pitch.
  function tick() {
    if (!running) return;
    const now = engine.currentTime;
    const spb = Music.beatSeconds(bpm);
    const elapsedBeats = (now - perfStart) / spb;

    // Which note are we on?
    let activeIndex = -1;
    if (elapsedBeats >= 0) {
      for (const item of schedule) {
        if (elapsedBeats >= item.startBeat &&
            elapsedBeats < item.startBeat + item.beats) {
          activeIndex = item.index;
          break;
        }
      }
    }

    if (mode === 'practice' && elapsedBeats >= 0) {
      const f = detector.detect();
      if (f) {
        const midi = Music.freqToMidi(f);
        samples.push({ t: elapsedBeats * spb, midi });
        liveNote.textContent = `♪ ${Music.midiToName(midi)} (${f.toFixed(0)} Hz)`;
      }
    }

    rerender(activeIndex, lastColors);

    if (elapsedBeats >= totalBeats()) {
      finish();
      return;
    }
    rafId = requestAnimationFrame(tick);
  }

  function finish() {
    if (mode === 'practice') {
      const result = Scorer.grade(schedule, bpm, samples);
      lastColors = Scorer.colorsFromResults(result.results);
      showScore(result);
    }
    stop();
    statusEl.textContent = 'Done.';
  }

  function showScore(result) {
    const r = Scorer.rating(result.accuracy);
    scorePanel.hidden = false;
    scorePanel.innerHTML = `
      <div class="score-big">${result.accuracy}%</div>
      <div class="score-rating">${r.label}</div>
      <div class="score-detail">${result.correct} of ${result.scored} notes correct.
        Green = right pitch, red = wrong, grey = missed.</div>`;
  }

  // ----- Modes -------------------------------------------------------------
  async function startListen() {
    engine.ensure();
    setRunning(true);
    mode = 'listen';
    samples = [];
    lastColors = {};
    scorePanel.hidden = true;

    const lead = 0.25;
    const spb = Music.beatSeconds(bpm);
    const countIn = countInToggle.checked ? beatsPerBar() : 0;
    const base = engine.currentTime + lead;
    perfStart = base + countIn * spb;

    if (metronomeToggle.checked) {
      engine.scheduleMetronome(countIn + totalBeats(), bpm, base, beatsPerBar());
    }
    engine.playSchedule(schedule, bpm, perfStart);

    statusEl.textContent = countIn ? 'Count-in…' : 'Playing…';
    running = true;
    rafId = requestAnimationFrame(tick);
  }

  async function startPractice() {
    engine.ensure();
    statusEl.textContent = 'Requesting microphone…';
    try {
      await detector.start();
    } catch (e) {
      statusEl.textContent = 'Microphone access denied. Practice needs the mic.';
      return;
    }

    setRunning(true);
    mode = 'practice';
    samples = [];
    lastColors = {};
    scorePanel.hidden = true;

    const lead = 0.25;
    const spb = Music.beatSeconds(bpm);
    // Always give a one-bar count-in before practice so the player can prepare.
    const countIn = beatsPerBar();
    const base = engine.currentTime + lead;
    perfStart = base + countIn * spb;

    if (metronomeToggle.checked) {
      engine.scheduleMetronome(countIn + totalBeats(), bpm, base, beatsPerBar());
    }

    statusEl.textContent = 'Count-in… get ready to play!';
    running = true;
    rafId = requestAnimationFrame(tick);
  }

  // ----- Events ------------------------------------------------------------
  songSelect.addEventListener('change', (e) => loadSong(parseInt(e.target.value, 10)));
  tempoRange.addEventListener('input', (e) => {
    bpm = parseInt(e.target.value, 10);
    tempoLabel.textContent = `${bpm} BPM`;
  });
  listenBtn.addEventListener('click', startListen);
  practiceBtn.addEventListener('click', startPractice);
  stopBtn.addEventListener('click', stop);
  window.addEventListener('resize', () => { if (!running) rerender(-1, lastColors); });

  // ----- Init --------------------------------------------------------------
  populateSongs();
  loadSong(0);
  statusEl.textContent = 'Pick a song, then Listen or Practice.';

  // Expose a little for debugging / headless verification.
  window.PianoApp = { engine, detector, get schedule() { return schedule; } };
})();
