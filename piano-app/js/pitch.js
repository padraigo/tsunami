// pitch.js — real-time monophonic pitch detection from the microphone using a
// normalized autocorrelation (a compact ACF/MPM-style detector). Emits the
// detected fundamental frequency (or null when no clear pitch) at the rate the
// caller polls it.

(function () {
  // Estimate the fundamental frequency of a time-domain buffer.
  // Returns frequency in Hz, or -1 when the signal is too weak/unvoiced.
  function autoCorrelate(buf, sampleRate) {
    const SIZE = buf.length;

    // Reject near-silence using RMS.
    let rms = 0;
    for (let i = 0; i < SIZE; i++) rms += buf[i] * buf[i];
    rms = Math.sqrt(rms / SIZE);
    if (rms < 0.01) return -1;

    // Trim the leading/trailing low-amplitude regions.
    const threshold = 0.2;
    let start = 0;
    let end = SIZE - 1;
    while (start < SIZE / 2 && Math.abs(buf[start]) < threshold) start++;
    while (end > SIZE / 2 && Math.abs(buf[end]) < threshold) end--;
    const trimmed = buf.slice(start, end);
    const n = trimmed.length;
    if (n < 64) return -1;

    // Autocorrelation.
    const c = new Float32Array(n);
    for (let lag = 0; lag < n; lag++) {
      let sum = 0;
      for (let i = 0; i < n - lag; i++) sum += trimmed[i] * trimmed[i + lag];
      c[lag] = sum;
    }

    // Find the first dip after the zero-lag peak, then the highest peak after.
    let d = 0;
    while (d < n - 1 && c[d] > c[d + 1]) d++;
    let maxPos = -1;
    let maxVal = -Infinity;
    for (let i = d; i < n; i++) {
      if (c[i] > maxVal) { maxVal = c[i]; maxPos = i; }
    }
    if (maxPos <= 0) return -1;

    // Parabolic interpolation around the peak for sub-sample accuracy.
    let T0 = maxPos;
    const x1 = c[maxPos - 1] || 0;
    const x2 = c[maxPos];
    const x3 = c[maxPos + 1] || 0;
    const a = (x1 + x3 - 2 * x2) / 2;
    const b = (x3 - x1) / 2;
    if (a) T0 = T0 - b / (2 * a);

    const freq = sampleRate / T0;
    if (freq < 50 || freq > 2000) return -1; // outside musical range we track
    return freq;
  }

  class PitchDetector {
    constructor() {
      this.ctx = null;
      this.analyser = null;
      this.stream = null;
      this.buffer = null;
    }

    async start() {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      this.ctx = new Ctx();
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
        },
      });
      const source = this.ctx.createMediaStreamSource(this.stream);
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 2048;
      source.connect(this.analyser);
      this.buffer = new Float32Array(this.analyser.fftSize);
    }

    // Current detected frequency (Hz) or null.
    detect() {
      if (!this.analyser) return null;
      this.analyser.getFloatTimeDomainData(this.buffer);
      const f = autoCorrelate(this.buffer, this.ctx.sampleRate);
      return f > 0 ? f : null;
    }

    stop() {
      if (this.stream) this.stream.getTracks().forEach((t) => t.stop());
      if (this.ctx) this.ctx.close();
      this.ctx = null;
      this.analyser = null;
      this.stream = null;
    }
  }

  window.PitchDetector = PitchDetector;
  window.autoCorrelate = autoCorrelate;
})();
