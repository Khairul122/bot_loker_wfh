// a walking, emoting character: staff and the player are both Char
import * as THREE from 'three';
import { scene } from '../core/engine.js';
import { cyl, tag, emojiTex } from '../core/factory.js';
import { Snd } from '../core/sound.js';
import { FH, V, rand } from '../core/util.js';
import { route, inR } from '../world/navigation.js';
import { spots } from '../world/spots.js';
import { makeBody, MOODS } from './body.js';

export const chars = [];
export class Char {
  constructor(name, look, level, x, z) {
    this.name = name; this.look = look; this.p = makeBody(look);
    scene.add(this.p.root);
    this.level = level; this.pos = V(x, z); this.y = level * FH; this.ry = 0;
    this.path = []; this.speed = 2.6; this.pose = 'stand'; this.spot = null;
    this.emote = null; this.emoteT = 0; this.mood = 'senang'; this.t = rand(0, 10);
    this.bubble = new THREE.Sprite(new THREE.SpriteMaterial({ map: emojiTex('😊'), depthWrite: false }));
    this.bubble.scale.set(0.7, 0.7, 1); this.bubble.position.y = 2.35; this.p.root.add(this.bubble);
    this.platform = cyl(0.8, 0.8, 0.08, 0xffffff, 0, -0.05, 0, this.p.root, { cast: false }); this.platform.visible = false;
    this.setMood('senang');
    tag(this.p.root, { kind: 'char', char: this });
    chars.push(this);
  }
  setLook(look) {
    this.look = look;
    this.p.skull.material.color.set(look.skin); this.p.hair.material.color.set(look.hair);
    this.p.torso.material.color.set(look.shirt);
    this.p.arms.forEach(a => { a.children[0].material.color.set(look.shirt); a.children[1].material.color.set(look.skin); });
    this.p.legs.forEach(l => l.children[0].material.color.set(look.pants));
  }
  setMood(m, showEmo) {
    const mm = MOODS[m]; this.mood = m;
    for (const k in this.p.mouth) this.p.mouth[k].visible = false;
    const f = mm.face === 'sleep' ? 'flat' : mm.face; this.p.mouth[f].visible = true;
    this.p.cheeks.forEach(c => c.visible = !!mm.cheeks);
    this.p.eyes.forEach(e => e.scale.y = mm.face === 'sleep' ? 0.15 : 1);
    this.showEmo(showEmo || mm.emo);
  }
  showEmo(e) { this.bubble.material.map = emojiTex(e); this.bubble.material.needsUpdate = true; this.emoPulse = 1; }
  doEmote(kind, dur = 2.2) { this.emote = kind; this.emoteT = dur; }
  face(x, z) { this.targetRy = Math.atan2(x - this.pos.x, z - this.pos.z); }
  leaveSpot() { if (this.spot) { this.spot.by = null; this.spot = null; } this.pose = 'stand'; }
  stop() { spots.forEach(s => { if (s.by === this) s.by = null; }); this.spot = null; this.pose = 'stand'; this.path = []; this.onArrive = null; }
  // via: waypoints from outside to just inside a room/desk/house; box: that room's footprint.
  // The next trip out of it walks the same waypoints backwards instead of through a wall.
  goTo(level, x, z, onArrive, { via = [], box } = {}) {
    if (this.ride) { this.pendingGo = [level, x, z, onArrive, { via, box }]; return; }
    const exit = this.exitPts();
    this.stop(); this.emote = null;
    const start = exit.length ? exit[exit.length - 1] : this.pos;
    const path = exit.map(p => ({ p }));
    path.push(...route(this.level, start, level, via.length ? via[0] : V(x, z)));
    via.slice(1).forEach(p => path.push({ p }));
    if (via.length) path.push({ p: V(x, z) });
    this.path = path; this.onArrive = onArrive;
    this.inside = via.length ? { level, via, box, at: V(x, z) } : null;
  }
  exitPts() {
    const i = this.inside;
    if (!i || i.level !== this.level) return [];
    const near = i.box ? inR(this.pos.x, this.pos.z, i.box, 0.2) : Math.hypot(this.pos.x - i.at.x, this.pos.z - i.at.z) < 1.2;
    return near ? [...i.via].reverse() : [];
  }
  carry(obj) { this.drop(); obj.position.set(0, -0.52, 0.2); this.p.arms[1].add(obj); this.carrying = obj; }
  drop() { if (this.carrying) { this.carrying.parent?.remove(this.carrying); this.carrying = null; } }
  update(dt, t) {
    this.t += dt;
    const P = this.p; let walking = false;
    const step = this.path[0];
    if (step) {
      if (step.ride !== undefined) {
        if (!this.ride) { this.ride = { from: this.level * FH, to: step.ride * FH, u: 0, dur: 0.6 + 0.35 * Math.abs(step.ride - this.level) }; this.platform.visible = true; }
        this.ride.u += dt / this.ride.dur;
        const u = Math.min(1, this.ride.u), e = u * u * (3 - 2 * u);
        this.y = this.ride.from + (this.ride.to - this.ride.from) * e;
        if (u >= 1) {
          this.level = step.ride; this.y = this.level * FH; this.ride = null; this.platform.visible = false; this.path.shift();
          if (this.isMe) Snd.play('ding');
          if (this.pendingGo) { const g = this.pendingGo; this.pendingGo = null; this.goTo(...g); }
        }
      } else {
        const dx = step.p.x - this.pos.x, dz = step.p.z - this.pos.z, dist = Math.hypot(dx, dz);
        const sp = this.speed * (this.mood === 'lelah' || this.mood === 'ngantuk' ? 0.7 : this.mood === 'semangat' ? 1.25 : 1);
        if (dist < 0.08) this.path.shift();
        else { const k = Math.min(1, sp * dt / dist); this.pos.x += dx * k; this.pos.z += dz * k; this.targetRy = Math.atan2(dx, dz); walking = true; }
      }
      if (!this.path.length) { const cb = this.onArrive; this.onArrive = null; cb && cb(this); }
    }
    if (this.kbWalk) { walking = true; this.kbWalk = false; }
    if (this.targetRy !== undefined) { let d = this.targetRy - this.ry; d = Math.atan2(Math.sin(d), Math.cos(d)); this.ry += d * Math.min(1, dt * 10); }
    this.walking = walking;
    // ---- pose & animation ----
    const s = Math.sin(this.t * 9);
    let bodyY = 0, legA = 0, armL = 0, armR = 0, armLz = 0, armRz = 0, headX = 0, headZ = 0, bodyRx = 0, rootY = this.y, extraRy = 0;
    if (walking) { legA = s * 0.6; armL = -s * 0.5; armR = s * 0.5; bodyY = Math.abs(s) * 0.05; }
    else if (this.pose === 'sit' || this.pose === 'work') {
      bodyY = -0.18; legA = -1.45; P.legs.forEach(l => l.rotation.x = legA);
      if (this.pose === 'work' && this.mood !== 'ngantuk') { armL = -1.1 + Math.sin(this.t * 14) * 0.1; armR = -1.1 + Math.sin(this.t * 14 + 1.5) * 0.1; }
      else { armL = armR = -0.3; }
    } else if (this.pose === 'floor') { bodyY = -0.6; legA = -1.5; armL = armR = 0.3; }
    else if (this.pose === 'lie') { bodyRx = -Math.PI / 2; bodyY = 0.95; legA = 0; armL = armR = 0; }
    else if (this.pose === 'swing' && this.spot) {
      const sw = this.spot.swing; const a = Math.sin(t * 2.2) * 0.55; sw.rotation.x = a;
      const wp = new THREE.Vector3(); sw.getWorldPosition(wp);
      const off = new THREE.Vector3(0, -2.4, 0).applyAxisAngle(new THREE.Vector3(1, 0, 0), a);
      this.pos.x = wp.x; this.pos.z = wp.z + off.z; rootY = wp.y + off.y - 0.2;
      legA = -1.4 + a; armL = armR = -2.6; bodyY = 0.05;
    } else if (this.pose === 'shoot') { const u = (this.t % 2.4) / 2.4; bodyY = u < 0.3 ? -0.1 : u < 0.5 ? 0.35 : 0; armL = armR = u < 0.5 ? -2.6 : -0.4; }
    else if (this.pose === 'play') { this.swingT = Math.max(0, (this.swingT || 0) - dt); armR = -0.9 - Math.sin(this.swingT / 0.35 * Math.PI) * 1.1; armRz = 0.3; bodyY = Math.abs(Math.sin(this.t * 3)) * 0.06; }
    else if (this.pose === 'eat') { const b = Math.max(0, Math.sin(this.t * 3)); bodyY = -0.18; legA = -1.45; armL = -0.6; armR = -1.5 - b * 1.0; headX = 0.12 - b * 0.15; }
    else if (this.pose === 'wash') { armL = armR = -1.1 + Math.sin(this.t * 9) * 0.12; headX = 0.35; }
    else if (this.pose === 'dance') { bodyY = Math.abs(Math.sin(this.t * 5)) * 0.25; extraRy = Math.sin(this.t * 2.5) * 0.9; armL = -2.4 + Math.sin(this.t * 10) * 0.4; armR = -2.4 - Math.sin(this.t * 10) * 0.4; }
    else {
      // idle by mood
      const m = this.mood;
      if (m === 'semangat') { bodyY = Math.max(0, Math.sin(this.t * 4)) * 0.18; armLz = armRz = 0.3; }
      else if (m === 'senang') { extraRy = Math.sin(this.t * 1.2) * 0.12; armLz = armRz = 0.12; }
      else if (m === 'lelah') { headX = 0.3; bodyRx = 0.12; armL = armR = 0.1; }
      else if (m === 'sedih') { headX = 0.5; bodyRx = 0.18; }
      else if (m === 'ngantuk') { headX = 0.25 + Math.sin(this.t * 1.3) * 0.2; headZ = 0.15; }
    }
    if (this.mood === 'ngantuk' && (this.pose === 'work' || this.pose === 'sit')) { headX = 0.45 + Math.sin(this.t * 1.3) * 0.15; }
    // emotes override upper body
    if (this.emote) {
      this.emoteT -= dt; const e = this.emote, u = this.t;
      if (e === 'wave') { armR = -2.8; armRz = 0.4 + Math.sin(u * 12) * 0.35; }
      else if (e === 'cheer') { armL = armR = -2.9; bodyY += Math.abs(Math.sin(u * 7)) * 0.3; }
      else if (e === 'jump') { bodyY += Math.abs(Math.sin(u * 6)) * 0.55; armL = armR = -2.5; }
      else if (e === 'dance') { bodyY += Math.abs(Math.sin(u * 5)) * 0.25; extraRy = Math.sin(u * 2.5) * 1.2; armL = -2.4 + Math.sin(u * 10) * 0.4; armR = -2.4 - Math.sin(u * 10) * 0.4; }
      else if (e === 'high5') { armR = -2.6; armRz = -0.2; bodyRx = -0.1; }
      else if (e === 'nod') { headX = Math.sin(u * 8) * 0.25; }
      else if (e === 'sigh') { headX = 0.45; bodyRx = 0.15; }
      else if (e === 'startle') { bodyY += Math.max(0, Math.sin(u * 10)) * 0.4; armL = armR = -1.6; }
      else if (e === 'drink') { armR = -2.0; headX = -0.25; }
      else if (e === 'stretch') { armL = armR = -3.0; bodyRx = -0.12; headX = -0.2; }
      else if (e === 'give') { armL = armR = -1.45; bodyRx = 0.1; }
      if (this.emoteT <= 0) this.emote = null;
    }
    if (this.carrying && !this.emote) armR = walking ? -1.0 : -1.25;
    if (!walking && !['sit', 'work', 'floor', 'swing', 'eat'].includes(this.pose)) P.legs.forEach(l => l.rotation.x = 0);
    else P.legs.forEach((l, i) => l.rotation.x = walking ? (i ? -legA : legA) : legA);
    P.arms[0].rotation.x = armL; P.arms[1].rotation.x = armR;
    P.arms[0].rotation.z = -armLz; P.arms[1].rotation.z = armRz;
    P.head.rotation.x = headX; P.head.rotation.z = headZ;
    P.body.position.y = bodyY; P.body.rotation.x = bodyRx;
    P.root.position.set(this.pos.x, rootY, this.pos.z);
    P.root.rotation.y = this.ry + extraRy;
    // blink
    if (this.mood !== 'ngantuk') { const b = (this.t % 4) < 0.12 ? 0.15 : 1; P.eyes.forEach(e => e.scale.y = b); }
    // bubble pulse
    this.emoPulse = Math.max(0, (this.emoPulse || 0) - dt * 2);
    const sc = 0.6 + this.emoPulse * 0.35 + Math.sin(this.t * 2) * 0.03;
    this.bubble.scale.set(sc, sc, 1);
    this.bubble.position.y = 2.25 + Math.sin(this.t * 2) * 0.06;
  }
}
