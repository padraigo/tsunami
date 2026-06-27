// audio.js — Web Audio playback: a lightweight piano-ish synth voice and a
// metronome click. All scheduling is done against the AudioContext clock so
// timing stays tight regardless of the JS event loop.

(function () {
  const Music = window.Music;

  class AudioEngine {
    constructor() {
      this.ctx = null;
      this.master = null;
    }

    // Lazily create the context (must follow a user gesture in browsers).
    ensure() {
      if (!this.ctx) {
        const Ctx = window.AudioContext || window.webkitAudioContext;
        this.ctx = new Ctx();
        this.master = this.ctx.createGain();
        this.master.gain.value = 0.8;
        this.master.connect(this.ctx.destination);
      }
      if (this.ctx.state === 'suspended') this.ctx.resume();
      return this.ctx;
    }

    get currentTime() {
      return this.ensure().currentTime;
    }

    // Play a single pitched note. `freq` Hz, `start` (ctx time), `dur` seconds.
    // Two detuned oscillators + a quick percussive envelope approximate a
    // plucked/struck tone without sample loading.
    playFreq(freq, start, dur, gain = 0.25) {
      const ctx = this.ensure();
      const t0 = Math.max(start, ctx.currentTime);
      const env = ctx.createGain();
      env.connect(this.master);

      const sustain = Math.max(dur - 0.04, 0.02);
      env.gain.setValueAtTime(0, t0);
      env.gain.linearRampToValueAtTime(gain, t0 + 0.008);      // fast attack
      env.gain.exponentialRampToValueAtTime(gain * 0.5, t0 + 0.12); // decay
      env.gain.setValueAtTime(gain * 0.5, t0 + sustain);
      env.gain.exponentialRampToValueAtTime(0.0001, t0 + dur); // release

      [{ type: 'triangle', detune: 0, level: 1 },
       { type: 'sine', detune: -4, level: 0.6 }].forEach((spec) => {
        const osc = ctx.createOscillator();
        osc.type = spec.type;
        osc.frequency.value = freq;
        osc.detune.value = spec.detune;
        const g = ctx.createGain();
        g.gain.value = spec.level;
        osc.connect(g).connect(env);
        osc.start(t0);
        osc.stop(t0 + dur + 0.05);
      });
    }

    // A short metronome tick. `accent` raises pitch/volume for downbeats.
    click(start, accent = false) {
      const ctx = this.ensure();
      const t0 = Math.max(start, ctx.currentTime);
      const osc = ctx.createOscillator();
      const g = ctx.createGain();
      osc.frequency.value = accent ? 1600 : 1000;
      g.gain.setValueAtTime(0, t0);
      g.gain.linearRampToValueAtTime(accent ? 0.5 : 0.3, t0 + 0.001);
      g.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.05);
      osc.connect(g).connect(this.master);
      osc.start(t0);
      osc.stop(t0 + 0.06);
    }

    // Play a whole schedule (array of {midis, beats, isRest, startBeat}) at bpm.
    // `baseTime` is the absolute AudioContext time at which beat 0 begins.
    // Returns the total duration in seconds.
    playSchedule(schedule, bpm, baseTime) {
      const ctx = this.ensure();
      const spb = Music.beatSeconds(bpm);
      const base = baseTime != null ? baseTime : ctx.currentTime + 0.1;
      let total = 0;
      schedule.forEach((item) => {
        const start = base + item.startBeat * spb;
        const dur = item.beats * spb;
        total = Math.max(total, item.startBeat * spb + dur);
        if (!item.isRest) {
          item.midis.forEach((midi) =>
            this.playFreq(Music.midiToFreq(midi), start, dur * 0.95));
        }
      });
      return total;
    }

    // Schedule metronome clicks for `beats` quarter-note beats starting at
    // `baseTime`, accenting the first beat of each measure.
    scheduleMetronome(beats, bpm, baseTime, beatsPerBar = 4) {
      const spb = Music.beatSeconds(bpm);
      for (let i = 0; i < beats; i++) {
        this.click(baseTime + i * spb, i % beatsPerBar === 0);
      }
    }

    stopAll() {
      // Recreate the master gain to silence anything still ringing.
      if (this.ctx) {
        try { this.master.disconnect(); } catch (e) { /* noop */ }
        this.master = this.ctx.createGain();
        this.master.gain.value = 0.8;
        this.master.connect(this.ctx.destination);
      }
    }
  }

  window.AudioEngine = AudioEngine;
})();
