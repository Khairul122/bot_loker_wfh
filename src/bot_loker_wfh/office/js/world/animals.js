// ---------- Procedural Low-Poly Three.js Animals (Wildlife, Pond Water Wading Physics & Duck Fleeing Bugfix) ----------
import * as THREE from 'three';
import { scene } from '../core/engine.js';
import { box, cyl, sph, group } from '../core/factory.js';
import { rand } from '../core/util.js';
import { me } from '../characters/player.js';
import { say } from '../fx/bubbles.js';
import { burst } from '../fx/particles.js';
import { Snd } from '../core/sound.js';

const animalInstances = [];
let wasInWater = false;
let waterRippleTimer = 0;

// Territory bounds
const TERRITORIES = {
  taman: { minX: -36, maxX: 36, minZ: -35, maxZ: -18 },
  rumah: { minX: -24, maxX: 24, minZ: -16, maxZ: -8 },
};

function pickTarget(area) {
  const t = TERRITORIES[area] || TERRITORIES.taman;
  return { x: rand(t.minX, t.maxX), z: rand(t.minZ, t.maxZ) };
}

// ---------- 1. Rusa (Deer) Builder ----------
function createDeer(x, z, variant = 'male') {
  const g = group(x, 0, z);
  const isMale = variant === 'male';
  const bodyColor = isMale ? 0x9a6238 : 0xb45309;

  box(0.48, 0.55, 0.95, bodyColor, 0, 0.72, 0, g);
  box(0.42, 0.35, 0.7, 0xfef08a, 0, 0.58, 0.05, g);
  if (!isMale) {
    sph(0.04, 0xffffff, -0.12, 1.02, -0.1, g);
    sph(0.04, 0xffffff, 0.12, 1.02, 0.1, g);
    sph(0.04, 0xffffff, 0.0, 1.02, -0.3, g);
  }

  const neck = box(0.24, 0.55, 0.26, bodyColor, 0, 1.15, 0.35, g); neck.rotation.x = -0.2;
  const head = group(0, 1.45, 0.42, g);
  box(0.22, 0.22, 0.32, bodyColor, 0, 0, 0, head);
  box(0.18, 0.16, 0.2, 0x451a03, 0, -0.03, 0.2, head);
  sph(0.03, 0x000000, 0, 0.04, 0.3, head);

  const earL = box(0.18, 0.06, 0.08, bodyColor, -0.16, 0.08, -0.05, head); earL.rotation.z = -0.3;
  const earR = box(0.18, 0.06, 0.08, bodyColor, 0.16, 0.08, -0.05, head); earR.rotation.z = 0.3;

  if (isMale) {
    const aL = cyl(0.025, 0.025, 0.45, 0xfef08a, -0.1, 0.26, -0.05, head); aL.rotation.z = -0.35; aL.rotation.x = -0.2;
    const aR = cyl(0.025, 0.025, 0.45, 0xfef08a, 0.1, 0.26, -0.05, head); aR.rotation.z = 0.35; aR.rotation.x = -0.2;
    cyl(0.02, 0.02, 0.2, 0xfef08a, -0.18, 0.32, 0.02, head).rotation.z = 0.4;
    cyl(0.02, 0.02, 0.2, 0xfef08a, 0.18, 0.32, 0.02, head).rotation.z = -0.4;
  }

  const legFL = cyl(0.05, 0.04, 0.55, 0x78350f, -0.18, 0.28, 0.32, g);
  const legFR = cyl(0.05, 0.04, 0.55, 0x78350f, 0.18, 0.28, 0.32, g);
  const legBL = cyl(0.05, 0.04, 0.55, 0x78350f, -0.18, 0.28, -0.32, g);
  const legBR = cyl(0.05, 0.04, 0.55, 0x78350f, 0.18, 0.28, -0.32, g);
  const tail = sph(0.07, 0xffffff, 0, 0.85, -0.5, g);

  return { root: g, head, legs: [legFL, legFR, legBL, legBR], tail, walkSpeed: 1.4, runSpeed: 3.2 };
}

// ---------- 2. Burung (Bird) Builder ----------
function createBird(x, y, z, variant = 'cyan') {
  const g = group(x, y, z);
  const mainColor = variant === 'scarlet' ? 0xdc2626 : 0x0284c7;
  const subColor = variant === 'scarlet' ? 0xf87171 : 0x38bdf8;
  const wingColor = variant === 'scarlet' ? 0x991b1b : 0x0369a1;

  const body = sph(0.18, mainColor, 0, 0, 0, g); body.scale.set(0.8, 0.8, 1.4);
  const head = sph(0.12, subColor, 0, 0.1, 0.18, g);
  const beak = box(0.08, 0.08, 0.14, 0xf59e0b, 0, 0.08, 0.28, g); beak.rotation.x = 0.2;
  const wingL = group(-0.16, 0.04, 0, g); box(0.32, 0.03, 0.18, wingColor, -0.16, 0, 0, wingL);
  const wingR = group(0.16, 0.04, 0, g); box(0.32, 0.03, 0.18, wingColor, 0.16, 0, 0, wingR);
  const tail = box(0.12, 0.02, 0.25, wingColor, 0, -0.02, -0.24, g); tail.rotation.x = -0.2;

  return { root: g, head, wingL, wingR, flySpeed: 6.0 };
}

// ---------- 3. Kelinci (Rabbit) Builder ----------
function createRabbit(x, z, variant = 'white') {
  const g = group(x, 0, z);
  const colorMap = { white: 0xf8fafc, brown: 0xa16207, gray: 0x64748b };
  const furColor = colorMap[variant] || 0xf8fafc;

  sph(0.13, furColor, 0, 0.12, 0, g);
  const head = sph(0.09, furColor, 0, 0.21, 0.08, g);
  const earL = box(0.035, 0.16, 0.03, furColor, -0.04, 0.3, 0.06, g); earL.rotation.z = -0.15;
  box(0.02, 0.12, 0.015, 0xf472b6, -0.04, 0.3, 0.07, g).rotation.z = -0.15;
  const earR = box(0.035, 0.16, 0.03, furColor, 0.04, 0.3, 0.06, g); earR.rotation.z = 0.15;
  box(0.02, 0.12, 0.015, 0xf472b6, 0.04, 0.3, 0.07, g).rotation.z = 0.15;
  sph(0.045, 0xffffff, 0, 0.08, -0.12, g);
  const legL = sph(0.05, furColor, -0.08, 0.04, 0, g);
  const legR = sph(0.05, furColor, 0.08, 0.04, 0, g);

  return { root: g, head, earL, earR, legs: [legL, legR], walkSpeed: 1.1, runSpeed: 2.6 };
}

// ---------- 4. Kucing (Cat) Builder ----------
function createCat(x, z, variant = 'orange') {
  const g = group(x, 0, z);
  const isTuxedo = variant === 'tuxedo';
  const furColor = isTuxedo ? 0x1e293b : 0xf97316;
  const earColor = isTuxedo ? 0x0f172a : 0xea580c;

  box(0.22, 0.22, 0.42, furColor, 0, 0.18, 0, g);
  box(0.2, 0.14, 0.3, 0xffffff, 0, 0.13, 0, g);
  const head = sph(0.12, furColor, 0, 0.28, 0.16, g);
  const earL = box(0.05, 0.07, 0.04, earColor, -0.07, 0.38, 0.15, g); earL.rotation.z = -0.2;
  const earR = box(0.05, 0.07, 0.04, earColor, 0.07, 0.38, 0.15, g); earR.rotation.z = 0.2;
  sph(0.02, 0x15803d, -0.04, 0.3, 0.24, g); sph(0.02, 0x15803d, 0.04, 0.3, 0.24, g);
  const legFL = cyl(0.035, 0.03, 0.15, 0xffffff, -0.08, 0.075, 0.14, g);
  const legFR = cyl(0.035, 0.03, 0.15, 0xffffff, 0.08, 0.075, 0.14, g);
  const legBL = cyl(0.035, 0.03, 0.15, 0xffffff, -0.08, 0.075, -0.14, g);
  const legBR = cyl(0.035, 0.03, 0.15, 0xffffff, 0.08, 0.075, -0.14, g);
  const tailPivot = group(0, 0.24, -0.2, g);
  const tailMesh = cyl(0.025, 0.015, 0.26, earColor, 0, 0.12, -0.08, tailPivot); tailMesh.rotation.x = -0.6;

  return { root: g, head, legs: [legFL, legFR, legBL, legBR], tailPivot, walkSpeed: 1.2, runSpeed: 3.0 };
}

// ---------- 5. Anjing (Dog) Builder ----------
function createDog(x, z, variant = 'beagle') {
  const g = group(x, 0, z);
  const isGolden = variant === 'golden';
  const furColor = isGolden ? 0xeab308 : 0xd97706;
  const earColor = isGolden ? 0xca8a04 : 0x451a03;

  box(0.28, 0.32, 0.54, furColor, 0, 0.28, 0, g);
  box(0.26, 0.22, 0.42, 0xfef08a, 0, 0.21, 0, g);
  const head = group(0, 0.44, 0.22, g);
  box(0.22, 0.22, 0.24, isGolden ? 0xca8a04 : 0x92400e, 0, 0, 0, head);
  box(0.15, 0.13, 0.16, 0xffffff, 0, -0.03, 0.15, head);
  sph(0.032, 0x000000, 0, 0.02, 0.23, head);
  const earL = box(0.05, 0.18, 0.09, earColor, -0.13, -0.02, 0, head); earL.rotation.z = 0.15;
  const earR = box(0.05, 0.18, 0.09, earColor, 0.13, -0.02, 0, head); earR.rotation.z = -0.15;
  const legFL = cyl(0.045, 0.038, 0.22, 0xffffff, -0.1, 0.11, 0.18, g);
  const legFR = cyl(0.045, 0.038, 0.22, 0xffffff, 0.1, 0.11, 0.18, g);
  const legBL = cyl(0.045, 0.038, 0.22, 0xffffff, -0.1, 0.11, -0.18, g);
  const legBR = cyl(0.045, 0.038, 0.22, 0xffffff, 0.1, 0.11, -0.18, g);
  const tailPivot = group(0, 0.36, -0.26, g);
  const tailMesh = cyl(0.03, 0.015, 0.24, furColor, 0, 0.1, -0.06, tailPivot); tailMesh.rotation.x = -0.5;

  return { root: g, head, legs: [legFL, legFR, legBL, legBR], tailPivot, walkSpeed: 1.5, runSpeed: 3.6 };
}

// ---------- 6. Bebek (Pond Duck & Duckling) Builder ----------
function createDuck(x, z, variant = 'mallard') {
  const g = group(x, 0.1, z);
  const isDuckling = variant === 'duckling';
  const scale = isDuckling ? 0.55 : 0.95;
  g.scale.setScalar(scale);

  let bodyColor = 0xffffff;
  let headColor = 0xffffff;
  let beakColor = 0xf97316;

  if (variant === 'mallard') {
    bodyColor = 0x78350f;
    headColor = 0x065f46;
    beakColor = 0xf59e0b;
  } else if (variant === 'duckling') {
    bodyColor = headColor = 0xfde047;
    beakColor = 0xf97316;
  }

  const body = sph(0.24, bodyColor, 0, 0.14, 0, g); body.scale.set(0.85, 0.75, 1.25);
  box(0.26, 0.12, 0.28, 0xffffff, 0, 0.1, 0.02, g);
  if (variant === 'mallard') {
    box(0.04, 0.1, 0.22, 0x0284c7, -0.21, 0.16, 0, g);
    box(0.04, 0.1, 0.22, 0x0284c7, 0.21, 0.16, 0, g);
  }

  const headGroup = group(0, 0.26, 0.16, g);
  const head = sph(0.13, headColor, 0, 0, 0, headGroup);
  if (variant === 'mallard') box(0.24, 0.03, 0.24, 0xffffff, 0, -0.09, 0, headGroup);
  const beak = box(0.12, 0.05, 0.16, beakColor, 0, -0.02, 0.15, headGroup); beak.rotation.x = 0.15;
  sph(0.025, 0x000000, -0.07, 0.03, 0.08, headGroup);
  sph(0.025, 0x000000, 0.07, 0.03, 0.08, headGroup);

  const tail = box(0.08, 0.08, 0.14, bodyColor, 0, 0.22, -0.28, g); tail.rotation.x = 0.4;

  return { root: g, head: headGroup, tail, swimSpeed: 1.2 };
}

// ---------- Initialize Wildlife ----------
export async function initAnimals() {
  const population = [
    { id: 'deer', inst: createDeer(14, -24, 'male'), area: 'taman', pos: [14, 0, -24], sound: 'Snort~ 🌿' },
    { id: 'deer', inst: createDeer(-18, -26, 'female'), area: 'taman', pos: [-18, 0, -26], sound: 'Squeak~ 🌿' },
    { id: 'rabbit', inst: createRabbit(-12, -22, 'white'), area: 'taman', pos: [-12, 0, -22], sound: 'Wiggle~ 🥕' },
    { id: 'rabbit', inst: createRabbit(8, -25, 'brown'), area: 'taman', pos: [8, 0, -25], sound: 'Hop hop! 🥕' },
    { id: 'rabbit', inst: createRabbit(-22, -20, 'gray'), area: 'taman', pos: [-22, 0, -20], sound: 'Sniff~ 🥕' },
    { id: 'bird', inst: createBird(0, 16, -18, 'cyan'), area: 'sky', pos: [0, 16, -18], sound: 'Chirp! 🎵' },
    { id: 'bird', inst: createBird(-10, 15, -10, 'scarlet'), area: 'sky', pos: [-10, 15, -10], sound: 'Tweet! 🎶' },
    { id: 'cat', inst: createCat(-6, -14, 'orange'), area: 'rumah', pos: [-6, 0, -14], sound: 'Meow~ 🐱' },
    { id: 'cat', inst: createCat(10, -12, 'tuxedo'), area: 'rumah', pos: [10, 0, -12], sound: 'Purr~ 🐾' },
    { id: 'dog', inst: createDog(6, -14, 'beagle'), area: 'rumah', pos: [6, 0, -14], sound: 'Guk guk! 🐕' },
    { id: 'dog', inst: createDog(-14, -12, 'golden'), area: 'rumah', pos: [-14, 0, -12], sound: 'Woof woof! 🐾' },
    // Bebek Kolam (3 ekor: Mallard, Pekin White, & Duckling)
    { id: 'duck', inst: createDuck(-30, -6, 'mallard'), area: 'pond', pos: [-30, 0.1, -6], sound: 'Kwek kwek! 🦆', offset: 0 },
    { id: 'duck', inst: createDuck(-28, -5, 'white'), area: 'pond', pos: [-28, 0.1, -5], sound: 'Quack~ 🦆', offset: 2.2 },
    { id: 'duck', inst: createDuck(-31, -7, 'duckling'), area: 'pond', pos: [-31, 0.1, -7], sound: 'Peep peep! ✨', offset: 4.4 },
  ];

  population.forEach(c => {
    const wrapper = { p: { root: c.inst.root } };

    animalInstances.push({
      id: c.id,
      data: c.inst,
      wrapper,
      sound: c.sound,
      area: c.area,
      offset: c.offset || 0,
      x: c.pos[0],
      z: c.pos[2],
      targetX: c.pos[0],
      targetZ: c.pos[2],
      state: 'idle',
      timer: rand(2, 5),
      interactCooldown: 0,
      rotY: Math.random() * Math.PI * 2,
      flyAngle: Math.random() * Math.PI * 2,
    });
  });
}

// ---------- Update Frame Loop ----------
export function updateAnimals(dt, t) {
  const humanInPond = updateWaterWading(dt);

  animalInstances.forEach(item => {
    checkOwnerInteraction(item, dt);

    if (item.id === 'bird') {
      updateBird(item, dt, t);
    } else if (item.id === 'duck') {
      updateDuck(item, dt, t, humanInPond);
    } else {
      updateGround(item, dt, t);
    }
  });
}

// ---------- Pond Water Wading Mechanics for Player ----------
function updateWaterWading(dt) {
  const distToPond = Math.hypot(me.pos.x - (-30), me.pos.z - (-6));
  const inPond = distToPond < 5.8;

  if (inPond) {
    if (!wasInWater) {
      wasInWater = true;
      me.speed = 2.0; // Slow movement inside water
      burst(new THREE.Vector3(me.pos.x, 0.1, me.pos.z), ['💦', '💧', '🌊', '✨'], 10);
      say(me, 'Byur! Airnya segar 💦', 2.5);
      try { Snd.play('pop'); } catch {}
    }

    // Legs sink into pond water
    me.p.root.position.y = -0.22;

    if (me.walking) {
      waterRippleTimer += dt;
      if (waterRippleTimer > 0.22) {
        waterRippleTimer = 0;
        burst(new THREE.Vector3(me.pos.x, 0.05, me.pos.z), ['💦', '💧'], 3);
      }
    }
  } else if (wasInWater) {
    wasInWater = false;
    me.speed = 3.6; // Restore normal speed
    me.p.root.position.y = 0; // Restore ground height
    burst(new THREE.Vector3(me.pos.x, 0.1, me.pos.z), ['💧', '✨'], 4);
    say(me, 'Naik ke darat 🌿', 2.0);
  }

  return inPond;
}

function checkOwnerInteraction(item, dt) {
  if (item.interactCooldown > 0) {
    item.interactCooldown -= dt;
    return;
  }

  const dx = me.p.root.position.x - item.x;
  const dz = me.p.root.position.z - item.z;
  const dist = Math.hypot(dx, dz);
  const maxDist = item.id === 'duck' ? 3.8 : 2.3;

  if (dist < maxDist) {
    item.interactCooldown = 6.0;
    if (item.id !== 'duck') item.state = 'follow';
    item.timer = rand(3, 5);

    say(item.wrapper, item.sound, 2.5);
    try { Snd.play('pop'); } catch {}
  }
}

// ---------- Duck Swimming & Startled Panic Dynamics (With Fan Spread Bugfix) ----------
function updateDuck(item, dt, t, humanInPond) {
  const { data } = item;
  const root = data.root;

  if (humanInPond) {
    // Calculate vector away from human player
    const dx = -30 - me.pos.x;
    const dz = -6 - me.pos.z;
    const baseAngle = Math.atan2(dx, dz);

    // Spread each duck out in a wide fan arc along pond shore using item.offset
    const spreadAngle = baseAngle + (item.offset - 2.2) * 0.45;
    const radius = 4.2 + (item.offset % 0.6);

    const duckX = -30 + Math.sin(spreadAngle) * radius;
    const duckZ = -6 + Math.cos(spreadAngle) * radius;

    item.x = duckX;
    item.z = duckZ;

    root.position.set(duckX, 0.1 + Math.abs(Math.sin(t * 10 + item.offset)) * 0.04, duckZ);
    root.rotation.y = spreadAngle;
    root.rotation.x = -0.15; // Startled tilt

    if (data.head) data.head.rotation.y = Math.sin(t * 12 + item.offset) * 0.3;
    if (item.interactCooldown <= 0) {
      item.interactCooldown = 5.0;
      say(item.wrapper, 'Byur! Ada yang nyemplung! 🦆💦', 2.5);
      try { Snd.play('pop'); } catch {}
    }
    return;
  }

  // Normal peaceful swimming loop
  const angle = t * 0.35 + item.offset;
  const radiusX = 3.2;
  const radiusZ = 2.6;
  const centerX = -30;
  const centerZ = -6;

  const x = centerX + Math.cos(angle) * radiusX;
  const z = centerZ + Math.sin(angle * 2) * radiusZ * 0.5;

  const dx = -Math.sin(angle) * radiusX;
  const dz = Math.cos(angle * 2) * radiusZ * 1.0;

  item.x = x;
  item.z = z;

  root.position.set(x, 0.08 + Math.sin(t * 3 + item.offset) * 0.025, z);
  root.rotation.y = Math.atan2(dx, dz);
  root.rotation.x = 0;

  if (data.tail) data.tail.rotation.y = Math.sin(t * 8) * 0.25;
  if (data.head) data.head.rotation.x = Math.sin(t * 1.8 + item.offset) * 0.18;
}

function updateBird(item, dt, t) {
  const { data } = item;
  const root = data.root;

  item.timer -= dt;
  if (item.timer <= 0) {
    item.state = item.state === 'perch' ? 'fly' : (Math.random() < 0.35 ? 'perch' : 'fly');
    item.timer = item.state === 'perch' ? rand(4, 8) : rand(10, 20);
  }

  if (item.state === 'perch') {
    root.position.set(0, 12.2, 1);
    root.rotation.set(0, Math.sin(t * 0.4) * 0.5, 0);
    data.wingL.rotation.z = 0.2;
    data.wingR.rotation.z = -0.2;
  } else {
    item.flyAngle += dt * 0.38;
    const x = Math.cos(item.flyAngle) * 26;
    const z = -5 + Math.sin(item.flyAngle * 0.8) * 20;
    const y = 14 + Math.sin(t * 1.5) * 2.2;

    const dx = -Math.sin(item.flyAngle) * 26 * 0.38;
    const dz = Math.cos(item.flyAngle * 0.8) * 20 * 0.8 * 0.38;

    root.position.set(x, y, z);
    root.rotation.y = Math.atan2(dx, dz);
    root.rotation.z = Math.sin(t * 2.5) * 0.25;
    root.rotation.x = Math.cos(t * 1.5) * 0.1;

    const flap = Math.sin(t * 14) * 0.65;
    data.wingL.rotation.z = flap;
    data.wingR.rotation.z = -flap;
  }
}

function updateGround(item, dt, t) {
  const { data, id } = item;
  const root = data.root;

  item.timer -= dt;
  if (item.timer <= 0) {
    const r = Math.random();
    if (r < 0.35) {
      item.state = 'idle';
      item.timer = rand(3, 7);
    } else {
      item.state = r < 0.75 ? 'walk' : 'run';
      item.timer = rand(4, 10);
      const tg = pickTarget(item.area);
      item.targetX = tg.x;
      item.targetZ = tg.z;
    }
  }

  if (item.state === 'follow') {
    item.targetX = me.p.root.position.x;
    item.targetZ = me.p.root.position.z;
  }

  if (item.state === 'idle') {
    item.rotY += Math.sin(t * 0.8) * 0.005;
    root.rotation.y = item.rotY;
    root.position.y = Math.sin(t * 2) * 0.015;

    if (data.tailPivot) {
      data.tailPivot.rotation.y = Math.sin(t * (id === 'dog' ? 10 : 3)) * 0.4;
    }
  } else {
    const speed = item.state === 'run' ? data.runSpeed : data.walkSpeed;
    const dx = item.targetX - item.x;
    const dz = item.targetZ - item.z;
    const dist = Math.hypot(dx, dz);

    if (dist < (item.state === 'follow' ? 1.4 : 0.6)) {
      item.state = 'idle';
      item.timer = rand(3, 6);
    } else {
      const targetAngle = Math.atan2(dx, dz);
      let angleDiff = targetAngle - item.rotY;
      while (angleDiff > Math.PI) angleDiff -= Math.PI * 2;
      while (angleDiff < -Math.PI) angleDiff += Math.PI * 2;

      item.rotY += angleDiff * Math.min(1.0, dt * 5.0);
      root.rotation.y = item.rotY;

      const moveDist = Math.min(dist, speed * dt);
      item.x += (dx / dist) * moveDist;
      item.z += (dz / dist) * moveDist;

      const swingFreq = item.state === 'run' ? 14 : 8;
      const swingAngle = item.state === 'run' ? 0.6 : 0.35;
      const legSwing = Math.sin(t * swingFreq) * swingAngle;

      if (data.legs && data.legs.length === 4) {
        data.legs[0].rotation.x = legSwing;
        data.legs[1].rotation.x = -legSwing;
        data.legs[2].rotation.x = -legSwing;
        data.legs[3].rotation.x = legSwing;
      } else if (data.legs && data.legs.length === 2) {
        data.legs[0].rotation.x = legSwing;
        data.legs[1].rotation.x = -legSwing;
      }

      if (id === 'rabbit') {
        const hop = Math.max(0, Math.sin(t * (item.state === 'run' ? 12 : 7))) * (item.state === 'run' ? 0.22 : 0.12);
        root.position.y = hop;
      } else {
        root.position.y = Math.abs(Math.sin(t * swingFreq)) * (item.state === 'run' ? 0.06 : 0.03);
      }

      if (data.tailPivot) {
        data.tailPivot.rotation.y = Math.sin(t * 12) * 0.5;
      }
    }
  }

  root.position.set(item.x, root.position.y, item.z);
}
