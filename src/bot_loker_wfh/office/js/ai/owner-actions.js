// ---------- what the owner does at a spot: sit, play, shoot hoops, go home, take the lift ----------
import * as THREE from 'three';
import { animated } from '../core/factory.js';
import { Snd } from '../core/sound.js';
import { V, ELEV_X, DOOR_X, pick, clamp } from '../core/util.js';
import { ball } from '../world/arena.js';
import { spots } from '../world/spots.js';
import { me } from '../characters/player.js';
import { staff } from '../characters/team.js';
import { say } from '../fx/bubbles.js';
import { burst } from '../fx/particles.js';
import { $, toast } from '../ui/dom.js';
import { endChat } from '../ui/card.js';
import { openMenu } from '../ui/menu.js';
import { toggleReports } from '../ui/reports.js';
import { sendTo } from './routine.js';

export function sitOwner(openPanel = true) {
  const s = spots.find(x => x.kind === 'owner');
  if (openPanel) toggleReports(true);
  if (s.by === me) return;
  me.leaveSpot();
  sendTo(me, s, () => { say(me, 'Cek laporan tim dulu 📋', 2.5); Snd.play('pop'); });
}
// houses: walk in through the door
export function goHouse(h) { me.goTo(0, h.x + 0.4, h.z + 0.6, null, { via: h.via, box: h.box }); }

const SAY = { bench: 'Duduk santai dulu 😌', swing: 'Wiii~ 🎶', picnic: 'Piknik kecil 🧺', pond: 'Bebeknya lucu 🦆', ping: 'Ayo tanding! 🏓', slide: 'Seluncur! 🛝', kafe: 'Satu kopi susu ya ☕', kopi: 'Ngopi dulu ☕', hammock: 'Ngadem di atap… 😴', parasol: 'Cerah banget hari ini 🌤️', sofa: 'Empuk~ 🛋️', toilet: 'Permisi… 🚻', wastafel: 'Cuci tangan dulu 🧼', kasur: 'Rebahan dulu… 😴', tv: 'Nonton TV ah 📺', kulkas: 'Ambil minum dingin 🥤' };
export function useSpot(kindName, house) {
  endChat();
  if (kindName === 'hoop') return goShoot();
  if (kindName === 'kantin') return openMenu();
  if (kindName === 'owner') return sitOwner();
  if (kindName === 'lift') {
    me.goTo(me.level, DOOR_X, 0);
    me.path.push({ p: V(ELEV_X, 0) }); // enter through the door, not the glass
    me.onArrive = () => say(me, 'Mau ke lantai berapa? 🛗');
    return;
  }
  const cands = spots.filter(s => s.kind === kindName && (!s.by || s.by === me) && (!house || s.house === house));
  if (!cands.length) { toast('Lagi dipakai, coba yang lain 🙂'); return; }
  const dist = s => s.swing ? 0 : Math.hypot(s.x - me.pos.x, s.z - me.pos.z) + Math.abs(s.level - me.level) * 20;
  const s = cands.reduce((a, b) => dist(a) < dist(b) ? a : b);
  me.leaveSpot();
  sendTo(me, s, () => {
    say(me, SAY[s.kind] || '😊');
    Snd.play('pop');
    if (s.kind === 'kafe' || s.kind === 'kopi' || s.kind === 'kulkas') { me.energy = clamp(me.energy + (s.kind === 'kulkas' ? 15 : 30), 0, 100); burst(new THREE.Vector3(me.pos.x, me.y, me.pos.z), s.kind === 'kulkas' ? ['🥤', '🧃', '✨'] : ['☕', '💨', '✨']); }
  });
}

let shooting = false;
function goShoot() {
  const s = spots.find(x => x.kind === 'hoop');
  if (s.by && s.by !== me) { toast('Ring lagi dipakai, tunggu sebentar 🏀'); return; }
  me.leaveSpot();
  sendTo(me, s, () => { me.pose = 'stand'; shoot(); });
}
function shoot() {
  if (shooting) return; shooting = true;
  const from = new THREE.Vector3(me.pos.x + 0.2, 2.2, me.pos.z - 0.2);
  const to = new THREE.Vector3(28, 3.05, -12.55);
  const chance = 0.35 + me.energy / 250 + (me.mood === 'semangat' ? 0.15 : 0);
  const made = Math.random() < chance;
  if (!made) to.x += pick([-0.7, 0.7]);
  me.doEmote('jump', 0.8);
  let u = 0;
  const fly = (t, dt) => {
    u += dt / 1.0;
    const k = Math.min(u, 1);
    ball.position.lerpVectors(from, to, k); ball.position.y += Math.sin(k * Math.PI) * 2.6;
    if (u >= 1) {
      animated.splice(animated.indexOf(fly), 1);
      ball.position.set(to.x, 0.26, to.z + 1.5);
      shooting = false;
      Snd.play(made ? 'swish' : 'boop'); if (made) Snd.play('chime');
      if (made) { me.hoopScore++; $('score').textContent = '🏀 ' + me.hoopScore; me.joy = clamp(me.joy + 10, 0, 100); me.doEmote('cheer'); burst(to.clone().setY(1), ['🎉', '⭐', '✨'], 10); say(me, pick(['Masuk!! 🎉', 'Swish! 😎', 'Yesss!'])); staff.filter(c => c.spot?.kind?.match(/ping|slide|swing/)).forEach(c => c.doEmote('cheer')); }
      else { me.doEmote('sigh', 1.2); say(me, pick(['Yah meleset 😅', 'Dikit lagi!', 'Sekali lagi!'])); }
      setTimeout(() => { ball.position.set(me.pos.x + 0.6, 0.26, me.pos.z); }, 500);
    }
  };
  animated.push(fly);
}
