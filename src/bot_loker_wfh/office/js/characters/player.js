// ---------- the player (owner): look (systems/prefs.js) and position (systems/positions.js) live in Supabase ----------
import * as THREE from 'three';
import { add } from '../core/factory.js';
import { Snd } from '../core/sound.js';
import { clamp, pick } from '../core/util.js';
import { derive } from '../data/stats.js';
import { say } from '../fx/bubbles.js';
import { burst } from '../fx/particles.js';
import { $ } from '../ui/dom.js';
import { Char } from './char.js';
import { MOODS } from './body.js';
import { staff } from './team.js';

export const myLook = { name: 'Owner', skin: '#f1c9a5', hair: '#3b2a20', shirt: '#ffb26b', pants: '#4a5a7a' };
export const me = new Char(
  myLook.name,
  { skin: myLook.skin, hair: myLook.hair, shirt: myLook.shirt, pants: myLook.pants },
  0, 2, 9,
);
me.speed = 3.6; me.energy = 80; me.joy = 60; me.isMe = true; me.idle = 0; me.hoopScore = 0;
export const ring = add(new THREE.TorusGeometry(0.55, 0.05, 6, 24), 0xffb26b, 0, 0.05, 0, me.p.root, { cast: false }); ring.rotation.x = Math.PI / 2;

export function updateMe(dt) {
  const moving = me.walking;
  me.stepT = (me.stepT || 0) + (moving ? dt : 0);
  if (me.stepT > 0.36) { me.stepT = 0; Snd.play('step'); }
  me.energy = clamp(me.energy - dt * (moving ? 0.45 : 0.06), 0, 100);
  if (me.spot && !me.walking) {
    me.energy = clamp(me.energy + (me.spot.energy || 0) * dt * 0.6, 0, 100);
    me.joy = clamp(me.joy + (me.spot.joy || 1) * dt * 0.5, 0, 100);
  }
  const team = staff.reduce((a, c) => a + (c.perfNow?.score || 0), 0) / staff.length;
  const d = derive();
  const baseline = clamp(team * 100 + d.interview * 10 + d.offer * 30, 15, 95);
  me.joy += (baseline - me.joy) * dt * 0.01;
  const m = me.energy < 15 ? 'ngantuk' : me.energy < 35 ? 'lelah' : me.joy > 80 ? 'semangat' : me.joy > 55 ? 'senang' : me.joy < 25 ? 'sedih' : 'fokus';
  if (me.mood !== m) { me.setMood(m); $('meFace').textContent = MOODS[m].emo; $('meMood').textContent = MOODS[m].label; }
  $('meEnergy').style.width = me.energy + '%';
  $('meEnergy').style.background = me.energy < 35 ? 'var(--low)' : me.energy < 60 ? 'var(--mid)' : 'var(--accent-2)';
  // idle behaviour
  if (me.eating && me.spot?.kind === 'makan' && !me.walking) {
    me.eating.left -= dt;
    if (me.eating.left <= 0) {
      const f = me.eating.food; me.eating = null; me.spot.plate.visible = false;
      me.energy = clamp(me.energy + f.energy, 0, 100); me.joy = clamp(me.joy + f.joy, 0, 100);
      burst(new THREE.Vector3(me.pos.x, me.y, me.pos.z), [f.icon, '😋', '✨'], 6); say(me, 'Kenyang! 😋', 2.5); Snd.play('chime');
      me.pose = 'sit';
    }
  } else if (me.eating && !me.spot) me.eating = null;
  me.idle = moving || me.emote || me.spot ? 0 : me.idle + dt;
  if (me.idle > 25) { me.idle = 0; me.doEmote(me.energy < 35 ? 'stretch' : 'nod', 2); say(me, me.energy < 35 ? 'Hoaam… ngopi dulu kali ya ☕' : pick(['Hmm, cek kinerja tim ah 📊', 'Semoga hari ini ada panggilan 🤞', 'Main ke taman yuk 🌳'])); }
}
