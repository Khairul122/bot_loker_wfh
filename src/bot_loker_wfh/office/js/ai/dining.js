// ---------- kantin: order at the counter, carry the tray to a seat, eat ----------
import * as THREE from 'three';
import { emojiTex } from '../core/factory.js';
import { Snd } from '../core/sound.js';
import { rand, pick } from '../core/util.js';
import { KANTIN } from '../buildings/divisions.js';
import { FOODS, ORDER_AT } from '../buildings/rooms/kantin.js';
import { spots } from '../world/spots.js';
import { me } from '../characters/player.js';
import { say } from '../fx/bubbles.js';
import { toast } from '../ui/dom.js';
import { sendTo, goBack } from './routine.js';

const foodSprite = icon => { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: emojiTex(icon, false), depthWrite: false })); s.scale.setScalar(0.45); return s; };
export const freeSeats = () => spots.filter(s => s.kind === 'makan' && !s.by);
const orderSpots = ORDER_AT.map((p, i) => ({ kind: 'kantin-antri', level: KANTIN, x: p.x, z: p.z, pose: 'stand', emo: '🍽️', id: `kantin-antri-${i}`, by: null }));
spots.push(...orderSpots);

function startOrder(c, seat, food, timer, queue, onOrder, wait = 1500) {
  c.state = 'break'; c.timer = 999; c.afterBreak = null;
  sendTo(c, queue, () => {
    c.targetRy = Math.PI;
    say(c, `${food.name} satu ya bu 🙏`, 2.5);
    onOrder?.();
    setTimeout(() => {
      if (c.state !== 'break') return;
      if (c.spot !== queue || (seat.by && seat.by !== c)) return goBack(c);
      c.carry(foodSprite(food.icon));
      sendTo(c, seat, () => { c.drop(); showPlate(seat, food); c.timer = timer; });
    }, wait);
  });
  seat.by = c;
}
// the plate shows on the table while someone eats
function showPlate(seat, food) { seat.plate.material.map = emojiTex(food.icon, false); seat.plate.material.needsUpdate = true; seat.plate.visible = true; }
export function goEat(c, seat = pick(freeSeats()), food = pick(FOODS), timer = rand(12, 20)) {
  const queue = orderSpots.find(s => !s.by);
  if (!seat || !queue) return false;
  startOrder(c, seat, food, timer, queue);
  return true;
}
// the owner orders too, optionally treating a colleague at the same table
export function playerEat(food, mate) {
  const free = freeSeats();
  const pair = mate && free.find(a => free.some(b => b !== a && b.table === a.table));
  const seat = pair || free[0];
  const queue = orderSpots.find(s => !s.by);
  if (!seat || !queue) { toast('Kantin lagi penuh, coba sebentar lagi 🍛'); return; }
  me.leaveSpot();
  startOrder(me, seat, food, 7, queue, () => Snd.play('pop'), 1200);
  if (mate) {
    const seat2 = free.find(s => s !== seat && s.table === seat.table) || free.find(s => s !== seat);
    if (seat2) goEat(mate, seat2, pick(FOODS), rand(25, 35));
  }
}
