// ---------- staff AI: work, breaks, toilet, commute home at night ----------
import * as THREE from 'three';
import { V, rand, pick, today } from '../core/util.js';
import { OWNER } from '../buildings/divisions.js';
import { stalls } from '../buildings/rooms/kantin.js';
import { spots } from '../world/spots.js';
import { me } from '../characters/player.js';
import { staffMood } from '../characters/team.js';
import { say } from '../fx/bubbles.js';
import { night } from '../systems/night.js';
import { goEat } from './dining.js';

// house furniture belongs to its occupant; the owner's room is not a lounge for staff
export function freeSpot(filter) { const list = spots.filter(s => !s.by && !s.house && s.level !== OWNER && filter(s)); return list.length ? pick(list) : null; }
export function sendTo(c, spot, onSit) {
  const target = spot.swing ? (() => { const w = new THREE.Vector3(); spot.swing.getWorldPosition(w); return V(w.x, w.z + 0.9); })() : V(spot.x, spot.z);
  c.goTo(spot.level, target.x, target.z, () => {
    if (spot.by && spot.by !== c) return; // someone took it
    spot.by = c; c.spot = spot; c.pose = spot.pose; c.targetRy = spot.ry;
    if (spot.kind === 'kopi' || spot.kind === 'kafe') c.doEmote('drink', 3);
    c.showEmo(spot.emo);
    onSit && onSit(c, spot);
  }, { via: spot.via || [], box: spot.box });
  spot.by = c;
}
export function updateStaff(c, dt, now) {
  const m = c.state === 'sleep' ? 'ngantuk' : staffMood(c, now);
  if (m !== c.mood) c.setMood(m, c.state === 'sleep' ? '💤' : undefined);
  if (c.state === 'chat' || c.state === 'report' || c.state === 'visit') return;
  // night: everyone goes home; morning: back to the desk
  if (night && (c.state === 'work' || c.state === 'back' || (c.state === 'break' && !c.path.length))) return goHome(c);
  if (!night && ['home', 'sleep', 'commute'].includes(c.state)) return wakeUp(c);
  c.timer -= dt;
  if (c.state === 'home' && c.timer <= 0 && !c.path.length) {
    c.state = 'sleep';
    sendTo(c, c.home.bed, () => { c.setMood('ngantuk', '💤'); say(c, pick(['Selamat tidur… 😴', 'Besok lanjut lagi 💤', 'Lampu dimatiin ya 🌙'])); });
    return;
  }
  if (c.state === 'work' && c.timer <= 0) {
    if (new Date().getHours() === 12 && c.ateDay !== today() && Math.random() < 0.7) { c.ateDay = today(); if (goEat(c)) return; }
    if (Math.random() < 0.1 && goToilet(c)) return;
    const p = { ngantuk: 0.8, lelah: 0.7, sedih: 0.6, fokus: 0.35, senang: 0.45, semangat: 0.5 }[c.mood];
    if (Math.random() < p) {
      const tired = c.mood === 'lelah' || c.mood === 'ngantuk';
      if (tired && c.ateDay !== today() && Math.random() < 0.4) { c.ateDay = today(); if (goEat(c)) return; }
      const spot = freeSpot(s => s !== me.spot && (tired ? (s.energy || 0) >= 6 : (s.joy || 0) >= 3 || s.kind === 'kafe'));
      if (spot) { c.state = 'break'; c.timer = rand(18, 32); sendTo(c, spot); say(c, tired ? pick(['Istirahat bentar ya 😮‍💨', 'Butuh kopi…', 'Rebahan dulu ah']) : pick(['Main dulu yuk! 🎮', 'Cari angin sebentar 🌳', 'Refreshing ~'])); return; }
    }
    c.timer = rand(20, 45);
    if (Math.random() < 0.5) say(c, pick(c.perfNow.lines));
  } else if (c.state === 'break' && c.timer <= 0 && !c.path.length) {
    c.boost = Math.max(c.boost, 1); c.boostUntil = now + 40;
    const next = c.afterBreak; c.afterBreak = null;
    next ? next(c) : goBack(c);
  }
}
function goHome(c) {
  c.state = 'commute'; c.afterBreak = null; c.drop();
  say(c, pick(['Pulang dulu ya bos 🏠', 'Sampai besok! 👋', 'Waktunya istirahat 🌙']), 3);
  sendTo(c, c.home.tv, () => { c.state = 'home'; c.timer = rand(15, 35); });
}
function wakeUp(c) {
  if (c.state === 'sleep') { c.doEmote('stretch', 2); say(c, pick(['Pagi! ☀️ Berangkat kerja', 'Hoaam… pagi bos ☀️']), 3); }
  goBack(c);
}
function goToilet(c) {
  const st = stalls.find(s => !s.spot.by); if (!st) return false;
  c.state = 'break'; c.timer = 999;
  say(c, pick(['Ke toilet bentar 🚻', 'Permisi sebentar 🚻']), 2.5);
  sendTo(c, st.spot, () => { c.timer = rand(6, 9); });
  c.afterBreak = c2 => {
    const sink = spots.find(s => s.kind === 'wastafel');
    if (sink.by && sink.by !== c2) return goBack(c2);
    c2.state = 'break'; c2.timer = 999;
    sendTo(c2, sink, () => { c2.timer = 3; });
  };
  return true;
}
export function goBack(c) {
  c.state = 'back';
  c.goTo(c.seat.level, c.seat.x, c.seat.z, () => { c.state = 'work'; c.pose = 'work'; c.targetRy = c.seat.ry; c.timer = rand(30, 60); }, { via: c.seat.via });
}
