// ---------- Animated Animals (GLTF/GLB models in 3D world) ----------
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { AnimationMixer, Box3, Vector3 } from 'three';
import { scene } from '../core/engine.js';

const loader = new GLTFLoader();
const mixers = [];
const animalInstances = [];

// Real-world scale. A character stands about 1.95 units tall for a 1.7 m adult, so 1 m = 1.15 units.
// `meters` is the real length of the animal's longest dimension (nose to tail, or wingspan for the bird);
// the model is scaled so that dimension matches, which keeps height and width in true proportion too.
const UNITS_PER_METER = 1.95 / 1.7;
const SPECIES = [
  { id: 'deer', file: 'assets/animals/deer.glb', meters: 1.7, pos: [14, 0, -24], area: 'taman' },
  { id: 'rabbit', file: 'assets/animals/rabbit.glb', meters: 0.45, pos: [-12, 0, -22], area: 'taman' },
  { id: 'bird', file: 'assets/animals/bird.glb', meters: 0.65, pos: [0, 16, -18], area: 'sky' },
  { id: 'cat', file: 'assets/animals/cat.glb', meters: 0.42, pos: [-6, 0, -14], area: 'rumah' },
  { id: 'dog', file: 'assets/animals/dog.glb', meters: 0.95, pos: [6, 0, -14], area: 'rumah' },
];

export async function initAnimals() {
  const tempVec = new Vector3();

  for (const cfg of SPECIES) {
    try {
      const gltf = await loader.loadAsync(cfg.file);
      const model = gltf.scene;

      // Auto-normalize scale using Box3 bounding box
      const box = new Box3().setFromObject(model);
      box.getSize(tempVec);
      const maxDim = Math.max(tempVec.x, tempVec.y, tempVec.z);
      if (maxDim > 0) {
        const finalScale = cfg.meters * UNITS_PER_METER / maxDim;
        model.scale.setScalar(finalScale);
      } else {
        model.scale.setScalar(0.05);
      }

      // Ground feet at y=0 if on ground, or keep sky altitude if flying
      box.setFromObject(model);
      const minY = box.min.y;
      const groundY = cfg.id === 'bird' ? cfg.pos[1] : (cfg.pos[1] - minY);
      model.position.set(cfg.pos[0], groundY, cfg.pos[2]);

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
      animalInstances.push({ cfg, model, mixer, baseY: groundY, origin: [...cfg.pos] });
    } catch (err) {
      console.warn(`Failed to load animal model (${cfg.id}):`, err);
    }
  }
}

export function updateAnimals(dt, t) {
  mixers.forEach(m => m.update(dt));

  animalInstances.forEach(item => {
    const { cfg, model, origin, baseY } = item;

    if (cfg.id === 'bird') {
      // Circle flight path in the sky above park
      const radius = 18;
      const speed = 0.4;
      const x = origin[0] + radius * Math.cos(t * speed);
      const z = origin[2] + radius * Math.sin(t * speed) * 0.7;
      const y = baseY + Math.sin(t * 1.2) * 1.5;

      const dx = -radius * Math.sin(t * speed) * speed;
      const dz = radius * Math.cos(t * speed) * 0.7 * speed;
      model.rotation.y = Math.atan2(dx, dz);
      model.position.set(x, y, z);
    } else if (cfg.id === 'rabbit') {
      // Gentle hopping animation and slight wander
      const hop = Math.abs(Math.sin(t * 3.5)) * 0.2; // a real rabbit hops about 0.15-0.3 m
      model.position.y = baseY + hop;
      model.rotation.y = Math.sin(t * 0.5) * 0.6;
    } else {
      // Ground animals (deer, cat, dog): slow subtle idle motion
      model.rotation.y = Math.sin(t * 0.3 + origin[0]) * 0.35;
      model.position.y = baseY + Math.sin(t * 1.5) * 0.015;
    }
  });
}
