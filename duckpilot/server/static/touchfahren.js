// Fahren per Touch (Handy, Tablet): Steuerkreuz auf der Bühne. Liefert die gewünschte Fahrt; die Tastatur-Schleife
// in app.js schickt sie zusammen mit Tastatur und Gamepad (seit 0.38.17 aus app.js ausgelagert)
import { $ } from './ui.js';

export function initTouchFahren({ send }) {
const touchDrive = { vx: 0, vyaw: 0, id: null };
  const pad = $('drive-pad'), knob = $('drive-knob');
  if (!pad) return touchDrive;
  const R = 44;
  const move = (e) => {
    const r = pad.getBoundingClientRect();
    let dx = e.clientX - (r.left + r.width / 2), dy = e.clientY - (r.top + r.height / 2);
    const len = Math.hypot(dx, dy);
    if (len > R) { dx *= R / len; dy *= R / len; }
    knob.style.transform = `translate(${dx}px, ${dy}px)`;
    const fx = -dy / R, fy = -dx / R;
    touchDrive.vx = Math.abs(fx) < 0.18 ? 0 : (fx > 0 ? fx * 0.22 : fx * 0.12);
    touchDrive.vyaw = Math.abs(fy) < 0.18 ? 0 : fy * 0.9;
  };
  const end = () => {
    touchDrive.vx = touchDrive.vyaw = 0; touchDrive.id = null;
    knob.style.transform = '';
    pad.classList.remove('is-active');
    send({ type: 'drive', vx: 0, vy: 0, vyaw: 0 });
  };
  pad.addEventListener('pointerdown', (e) => {
    e.preventDefault(); e.stopPropagation();
    touchDrive.id = e.pointerId;
    try { pad.setPointerCapture(e.pointerId); } catch { /* egal */ }
    pad.classList.add('is-active');
    move(e);
  });
  pad.addEventListener('pointermove', (e) => { if (e.pointerId === touchDrive.id) move(e); });
  pad.addEventListener('pointerup', end);
  pad.addEventListener('pointercancel', end);
  return touchDrive;
}
