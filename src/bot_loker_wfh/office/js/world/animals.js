// ---------- Animated Animals (GLTF/GLB models in 3D world) ----------
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { AnimationMixer } from 'three';
import { scene } from '../core/engine.js';

const loader = new GLTFLoader();
const mixers = [];
const animalInstances = [];

const SPECIES = [
  { id: 'deer', file: 'assets/animals/deer.glb', scale: 0.9, pos: [14, 0, -24], area: 'taman', wanderR: 6 },
  { id: 'rabbit', file: 'assets/animals/rabbit.glb', scale: 0.45, pos: [-12, 0, -22], area: 'taman', wanderR: 4 },
  { id: 'bird', file: 'assets/animals/bird.glb', scale: 0.6, pos: [0, 16, -18], area: 'sky' },
  { id: 'cat', file: 'assets/animals/cat.glb', scale: 0.55, pos: [-6, 0, -14], area: 'rumah', wanderR: 3 },
  { id: 'dog', file: 'assets/animals/dog.glb', scale: 0.55, pos: [6, 0, -14], area: 'rumah', wanderR: 4 },
];

export async function initAnimals() {
  for (const cfg of SPECIES) {
    try {
      const gltf = await loader.loadAsync(cfg.file);
      const model = gltf.scene;
      model.scale.setScalar(cfg.scale);
      model.position.set(...cfg.pos);

      model.traverse(node => {
        if (node.isMesh) {
          node.castShadow = true;
          node.receiveShadow = true;
        }
      });

      let mixer = null;
      if (gltf.animations && gltf.animations.length > 0) {
        mixer = new AnimationMixer(model);
        const action = mixer.clipAction(gltf.animations[0]);
        action.play();
        mixers.push(mixer);
      }

      scene.add(model);
      animalInstances.push({ cfg, model, mixer, origin: [...cfg.pos], heading: Math.random() * Math.PI * 2 });
    } catch (err) {
      console.warn(`Failed to load animal model (${cfg.id}):`, err);
    }
  }
}

export function updateAnimals(dt, t) {
  mixers.forEach(m => m.update(dt));

  animalInstances.forEach(item => {
    const { cfg, model, origin } = item;

    if (cfg.id === 'bird') {
      // Circle flight path in the sky above park
      const radius = 18;
      const speed = 0.4;
      const x = origin[0] + radius * Math.cos(t * speed);
      const z = origin[2] + radius * Math.sin(t * speed) * 0.7;
      const y = origin[1] + Math.sin(t * 1.2) * 1.5;

      const dx = -radius * Math.sin(t * speed) * speed;
      const dz = radius * Math.cos(t * speed) * 0.7 * speed;
      model.rotation.y = Math.atan2(dx, dz);
      model.position.set(x, y, z);
    } else if (cfg.id === 'rabbit') {
      // Gentle hopping animation and slight wander
      const hop = Math.abs(Math.sin(t * 3.5)) * 0.35;
      model.position.y = origin[1] + hop;
      model.rotation.y = Math.sin(t * 0.5) * 0.6;
    } else {
      // Ground animals (deer, cat, dog): slow subtle idle motion
      model.rotation.y = Math.sin(t * 0.3 + origin[0]) * 0.35;
      model.position.y = origin[1] + Math.sin(t * 1.5) * 0.04;
    }
  });
}
