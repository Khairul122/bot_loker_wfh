// ---------- HUD: emote buttons, sound toggle, clock ----------
import { Snd } from '../core/sound.js';
import { clamp } from '../core/util.js';
import { me } from '../characters/player.js';
import { staff } from '../characters/team.js';
import { $ } from './dom.js';

document.querySelectorAll('[data-emote]').forEach(b => b.onclick = () => {
  const e = b.dataset.emote;
  if (e === 'sit') { me.path = []; me.pose = me.pose === 'floor' ? 'stand' : 'floor'; return; }
  me.leaveSpot(); me.doEmote(e, 2.5); me.joy = clamp(me.joy + 2, 0, 100); Snd.play(e === 'cheer' ? 'clap' : 'pop');
  staff.filter(c => c.level === me.level && c.pos.distanceTo(me.pos) < 6).forEach(c => setTimeout(() => c.doEmote(e === 'wave' ? 'wave' : 'cheer', 1.8), 300 + Math.random() * 400));
});

const SOUND_KEY = 'kantor-loker-sound';
function setSoundButton() { $('bSound').textContent = Snd.on ? '🔊' : '🔇'; }
$('bSound').onclick = () => {
  Snd.toggle(); setSoundButton();
  try { localStorage.setItem(SOUND_KEY, Snd.on ? '1' : '0'); } catch {}
};
// browsers only allow audio after a user gesture: resume the saved preference on the first one
let wantSound = false;
try { wantSound = localStorage.getItem(SOUND_KEY) === '1'; } catch {}
if (wantSound) {
  const resume = () => { Snd.start(); setSoundButton(); removeEventListener('pointerdown', resume); removeEventListener('keydown', resume); };
  addEventListener('pointerdown', resume); addEventListener('keydown', resume);
}

setInterval(() => { $('clock').textContent = new Date().toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }); }, 1000);
