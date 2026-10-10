// ---------- pingpong: a real rally between whoever stands at both ends ----------
import * as THREE from 'three';
import { clock } from '../core/engine.js';
import { Snd } from '../core/sound.js';
import { rand, pick, clamp } from '../core/util.js';
import { pball } from '../world/arena.js';
import { spots } from '../world/spots.js';
import { me } from '../characters/player.js';
import { staff } from '../characters/team.js';
import { say } from '../fx/bubbles.js';
import { burst } from '../fx/particles.js';
import { $ } from '../ui/dom.js';
import { sendTo } from './routine.js';

export const pingSpots = spots.filter(s => s.kind === 'ping');
const pong = { players: null, u: 0, from: 0, hits: 0, len: 5, score: [0, 0], pause: 0, wait: 0 };
export function joinPong(c, spot, timer = rand(30, 50)) {
  if (spot.by || ['chat', 'report', 'sleep'].includes(c.state)) return;
  c.state = 'break'; c.afterBreak = null; c.timer = timer;
  sendTo(c, spot, () => say(c, pick(['Ayo! 🏓', 'Siap servis! 🏓']), 2));
}
export function updatePong(dt) {
  const [a, b] = pingSpots.map(s => s.by && s.by.spot === s && s.by.pose === 'play' ? s.by : null);
  if (!a || !b) {
    pong.players = null; pball.visible = false;
    const alone = a || b;
    pong.wait = alone ? pong.wait + dt : 0;
    if (alone && pong.wait > 3) { pong.wait = -25; invitePartner(alone); }
    return;
  }
  if (!pong.players || pong.players[0] !== a || pong.players[1] !== b) Object.assign(pong, { players: [a, b], score: [0, 0], hits: 0, u: 0, from: 0, pause: 1, len: 3 + Math.floor(Math.random() * 7) });
  pball.visible = true;
  const xs = [32.6, 35.4];
  if (pong.pause > 0) { pong.pause -= dt; pball.position.set(xs[pong.from], 1.2 + Math.abs(Math.sin(pong.pause * 6)) * 0.2, 4); return; }
  pong.u += dt / 0.7;
  const k = Math.min(pong.u, 1), miss = pong.hits >= pong.len;
  const x0 = xs[pong.from], x1 = xs[1 - pong.from];
  pball.position.set(x0 + (x1 - x0) * k * (miss ? 1.3 : 1), 0.86 + Math.abs(Math.sin(k * Math.PI * 2)) * 0.32 - (miss ? Math.max(0, k - 0.75) * 3 : 0), 4 + (miss ? k * 0.5 : 0));
  if (pong.u < 1) return;
  pong.u = 0;
  const [p0, p1] = pong.players, mine = p0 === me || p1 === me;
  if (!miss) { pong.hits++; pong.from = 1 - pong.from; pong.players[pong.from].swingT = 0.35; if (mine) Snd.play('click'); return; }
  const w = pong.from, winner = pong.players[w], loser = pong.players[1 - w];
  pong.score[w]++;
  winner.doEmote('cheer', 1.3); loser.doEmote('sigh', 1.1);
  say(winner, `${pong.score[0]} - ${pong.score[1]} ${pick(['Yes! 🏓', 'Poin! 😎', 'Hehe 😆'])}`, 2.2);
  if (mine) { Snd.play(winner === me ? 'chime' : 'boop'); $('score').textContent = `🏓 ${pong.score[pong.players.indexOf(me)]}-${pong.score[1 - pong.players.indexOf(me)]}`; }
  if (pong.score[w] >= 5) {
    say(winner, 'Menang! 🏆', 3); burst(new THREE.Vector3(winner.pos.x, 0, winner.pos.z), ['🏆', '🎉', '✨'], 8);
    if (winner === me) me.joy = clamp(me.joy + 15, 0, 100);
    if (winner.def) { winner.boost = 2; winner.boostUntil = clock.elapsedTime + 60; }
    pong.score = [0, 0];
  }
  Object.assign(pong, { hits: 0, from: 1 - w, pause: 1.3, len: 3 + Math.floor(Math.random() * 7) });
}
export function invitePartner(c) {
  const other = pingSpots.find(s => !s.by); if (!other) return;
  const mate = pick(staff.filter(s => s !== c && s.state === 'work' && s.mood !== 'ngantuk'));
  if (!mate) return;
  say(c, `${mate.name}, main pingpong yuk! 🏓`, 3);
  setTimeout(() => joinPong(mate, other, c === me ? rand(70, 100) : rand(25, 40)), 1200);
}
