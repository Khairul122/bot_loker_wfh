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
// the plate shows on the table while someone eats
function showPlate(seat, food) { seat.plate.material.map = emojiTex(food.icon, false); seat.plate.material.needsUpdate = true; seat.plate.visible = true; }
export function goEat(c, seat = pick(freeSeats()), food = pick(FOODS), timer = rand(12, 20)) {
  if (!seat) return false;
  c.state = 'break'; c.timer = 999; c.afterBreak = null;
  const at = pick(ORDER_AT);
  c.goTo(KANTIN, at.x, at.z, () => {
    c.targetRy = Math.PI; say(c, `${food.name} satu ya bu 🙏`, 2.5);
    setTimeout(() => {
      if (c.state !== 'break' || (seat.by && seat.by !== c)) return goBack(c);
      c.carry(foodSprite(food.icon));
      sendTo(c, seat, () => { c.drop(); showPlate(seat, food); c.timer = timer; });
    }, 1500);
  });
  seat.by = c; // reserved while queuing (goTo's stop() released everything first)
  return true;
}
// the owner orders too, optionally treating a colleague at the same table
export function playerEat(food, mate) {
  const free = freeSeats();
  const pair = mate && free.find(a => free.some(b => b !== a && b.table === a.table));
  const seat = pair || free[0];
  if (!seat) { toast('Kantin lagi penuh, coba sebentar lagi 🍛'); return; }
  me.leaveSpot();
  const at = ORDER_AT[1];
  me.goTo(KANTIN, at.x, at.z, () => {
    me.targetRy = Math.PI; say(me, `${food.name} satu ya bu 🙏`, 2.5); Snd.play('pop');
    setTimeout(() => {
      me.carry(foodSprite(food.icon));
      sendTo(me, seat, () => { me.drop(); showPlate(seat, food); me.eating = { food, left: 7 }; say(me, 'Selamat makan! 😋', 2.5); });
    }, 1200);
  });
  seat.by = me;
  if (mate) {
    const seat2 = free.find(s => s !== seat && s.table === seat.table) || free.find(s => s !== seat);
    if (seat2) goEat(mate, seat2, pick(FOODS), rand(25, 35));
  }
}
