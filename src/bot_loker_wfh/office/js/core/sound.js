// ---------- sound: lo-fi music + effects, synthesized with Web Audio (no audio files) ----------
import { pick } from './util.js';

export const Snd = (() => {
  let ctx = null, music, sfx, noise, crackle = null, timer = null, nextBar = 0, bar = 0, on = false;
  const CHORDS = [[53, 57, 60, 64], [52, 55, 59, 62], [50, 53, 57, 60], [48, 52, 55, 59]]; // Fmaj7 Em7 Dm7 Cmaj7
  const MELODY = [72, 74, 76, 79, 81, 84];
  const BEAT = 60 / 72;
  const hz = m => 440 * 2 ** ((m - 69) / 12);
  function init() {
    ctx = new (window.AudioContext || window.webkitAudioContext)();
    const master = ctx.createGain(); master.gain.value = 0.8; master.connect(ctx.destination);
    const warm = ctx.createBiquadFilter(); warm.type = 'lowpass'; warm.frequency.value = 1700; warm.connect(master);
    music = ctx.createGain(); music.gain.value = 0; music.connect(warm);
    sfx = ctx.createGain(); sfx.gain.value = 0.55; sfx.connect(master);
    noise = ctx.createBuffer(1, ctx.sampleRate, ctx.sampleRate);
    const d = noise.getChannelData(0); for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
  }
  function note(freq, t, dur, { type = 'sine', gain = 0.15, out = sfx, attack = 0.01, glide } = {}) {
    const o = ctx.createOscillator(), g = ctx.createGain();
    o.type = type; o.frequency.setValueAtTime(freq, t);
    if (glide) o.frequency.exponentialRampToValueAtTime(glide, t + dur);
    g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(gain, t + attack);
    g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    o.connect(g); g.connect(out); o.start(t); o.stop(t + dur + 0.05);
  }
  function hit(t, dur, gain, freq, out = sfx) {
    const src = ctx.createBufferSource(), f = ctx.createBiquadFilter(), g = ctx.createGain();
    src.buffer = noise; f.type = 'bandpass'; f.frequency.value = freq;
    g.gain.setValueAtTime(gain, t); g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
    src.connect(f); f.connect(g); g.connect(out); src.start(t, Math.random() * 0.5, dur + 0.05);
  }
  function scheduleBar(t) {
    const ch = CHORDS[bar % 4];
    ch.forEach(m => note(hz(m), t, BEAT * 4, { type: 'triangle', gain: 0.03, out: music, attack: 0.5 }));
    note(hz(ch[0] - 12), t, BEAT * 2, { gain: 0.09, out: music, attack: 0.02 });
    note(hz(ch[0] - 12), t + BEAT * 2.5, BEAT * 1.4, { gain: 0.07, out: music, attack: 0.02 });
    for (let b = 0; b < 4; b++) {
      const bt = t + b * BEAT;
      if (b % 2 === 0) note(110, bt, 0.28, { gain: 0.22, out: music, glide: 42 }); // kick
      else hit(bt + 0.02, 0.2, 0.1, 1600, music); // soft snare
      hit(bt, 0.04, 0.035, 7000, music); hit(bt + BEAT * 0.6, 0.04, 0.025, 7000, music); // swung hats
    }
    for (let k = 0; k < 4; k++) if (Math.random() < 0.45) note(hz(pick(MELODY)), t + BEAT * k + (Math.random() < 0.5 ? 0 : BEAT * 0.5), BEAT * 1.3, { gain: 0.045, out: music, attack: 0.005 });
    bar++;
  }
  function tick() { while (nextBar < ctx.currentTime + 1.2) { scheduleBar(nextBar); nextBar += BEAT * 4; } }
  function start() {
    if (!ctx) init();
    ctx.resume(); on = true;
    music.gain.cancelScheduledValues(ctx.currentTime);
    music.gain.linearRampToValueAtTime(1, ctx.currentTime + 2);
    nextBar = ctx.currentTime + 0.1; timer = setInterval(tick, 250); tick();
    // vinyl crackle
    const buf = ctx.createBuffer(1, ctx.sampleRate * 2, ctx.sampleRate), d = buf.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() < 0.0012 ? Math.random() * 2 - 1 : 0;
    crackle = ctx.createBufferSource(); crackle.buffer = buf; crackle.loop = true;
    const cg = ctx.createGain(); cg.gain.value = 0.12; crackle.connect(cg); cg.connect(music); crackle.start();
  }
  function stop() {
    on = false; clearInterval(timer);
    if (!ctx) return;
    music.gain.cancelScheduledValues(ctx.currentTime);
    music.gain.linearRampToValueAtTime(0, ctx.currentTime + 0.6);
    if (crackle) { crackle.stop(ctx.currentTime + 0.7); crackle = null; }
  }
  const FX = {
    click: t => note(1200, t, 0.05, { gain: 0.05 }),
    pop: t => note(620, t, 0.14, { gain: 0.18, glide: 980 }),
    chime: t => [72, 76, 79, 84].forEach((m, i) => note(hz(m), t + i * 0.09, 0.6, { type: 'triangle', gain: 0.1 })),
    coin: t => { note(hz(88), t, 0.1, { type: 'square', gain: 0.05 }); note(hz(93), t + 0.09, 0.35, { type: 'square', gain: 0.05 }); FX.chime(t + 0.2); },
    sad: t => [67, 63, 60].forEach((m, i) => note(hz(m), t + i * 0.2, 0.4, { type: 'triangle', gain: 0.1 })),
    ding: t => { note(hz(84), t, 0.9, { gain: 0.1 }); note(hz(79), t + 0.2, 1.1, { gain: 0.09 }); },
    swish: t => hit(t, 0.35, 0.25, 3200),
    boop: t => note(240, t, 0.3, { type: 'triangle', gain: 0.12, glide: 140 }),
    step: t => hit(t, 0.05, 0.05, 700),
    clap: t => { hit(t, 0.08, 0.3, 1500); hit(t + 0.05, 0.1, 0.2, 1200); },
  };
  return {
    get on() { return on; },
    toggle() { on ? stop() : start(); return on; },
    start() { if (!on) start(); },
    play(name) { if (on && ctx) FX[name](ctx.currentTime + 0.01); },
  };
})();
