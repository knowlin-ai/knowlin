// Punktwolke des Tiefensensors: Messpunkte der letzten Minute im Raum.
// Die Backends liefern je Zustand bis zu 64 Punkte [x, y, z] (Meter, Odometrie-Rahmen, z über dem
// Boden). PointStore sammelt sie in einem Ringpuffer; CloudLayer zeichnet sie in eine three.js-Szene.
// Dashboard und 3D-Ansicht haben je eine eigene Ebene über demselben Speicher.
import * as THREE from './vendor/three.module.min.js';

const LIFE = 60;          // s, so lange bleibt ein Punkt sichtbar und verblasst dabei
const CAP = 16000;        // Punkte im Puffer (≈ 250 Bilder)
const EVERY = 0.25;       // s, höchstens vier Bilder pro Sekunde sammeln
const FLOOR = 0.03;       // m, darunter gilt ein Punkt als Boden

// Höhe → Farbe: Carbon-Blau, je höher desto heller. Boden neutral grau.
const RAMP = ['#0f62fe', '#4589ff', '#78a9ff', '#a6c8ff', '#d0e2ff', '#edf5ff'].map((c) => new THREE.Color(c));
const GROUND = new THREE.Color('#6a6a6a');
export const CLOUD_TOP = 0.5;   // m, ab hier hellste Farbe

function heightColor(z, out) {
  if (z < FLOOR) return out.copy(GROUND);
  const k = Math.min(1, (z - FLOOR) / (CLOUD_TOP - FLOOR)) * (RAMP.length - 1);
  const i = Math.min(RAMP.length - 2, Math.floor(k));
  return out.copy(RAMP[i]).lerp(RAMP[i + 1], k - i);
}

export class PointStore {
  constructor() {
    this.pos = new Float32Array(CAP * 3);
    this.born = new Float32Array(CAP).fill(-1e9);
    this.head = 0;
    this.count = 0;
    this.version = 0;
    this._sig = '';
    this._at = -1e9;
  }

  // st: DuckState aus dem WebSocket. Gleiche Bilder (Ente steht still) werden nicht doppelt gesammelt.
  add(st, now = performance.now() / 1000) {
    const pts = st && st.perception && st.perception.points;
    if (!pts || !pts.length || st.fallen) return;
    if (now - this._at < EVERY) return;
    const tof = st.perception.tof_mm || [];
    const sig = `${tof.join(',')}|${st.x.toFixed(2)}|${st.y.toFixed(2)}|${st.yaw.toFixed(2)}|${(st.head?.head_yaw ?? 0).toFixed(2)}`;
    if (sig === this._sig) return;
    this._sig = sig;
    this._at = now;
    for (const p of pts) {
      const i = this.head;
      this.pos[i * 3] = p[0];
      this.pos[i * 3 + 1] = p[1];
      this.pos[i * 3 + 2] = p[2];
      this.born[i] = now;
      this.head = (i + 1) % CAP;
      this.count = Math.min(CAP, this.count + 1);
    }
    this.version++;
  }

  clear() {
    this.born.fill(-1e9);
    this.count = 0;
    this.head = 0;
    this._sig = '';
    this.version++;
  }

  // Punkte, die noch leben (für die Anzeige „n Punkte“)
  alive(now = performance.now() / 1000) {
    let n = 0;
    for (let i = 0; i < this.count; i++) if (now - this.born[i] < LIFE) n++;
    return n;
  }
}

// Runde, weich begrenzte Punkte statt Quadrate
let sprite = null;
function dotTexture() {
  if (sprite) return sprite;
  const c = document.createElement('canvas');
  c.width = c.height = 64;
  const g = c.getContext('2d');
  g.fillStyle = '#fff';
  g.beginPath();
  g.arc(32, 32, 28, 0, Math.PI * 2);
  g.fill();
  sprite = new THREE.CanvasTexture(c);
  return sprite;
}

export class CloudLayer {
  // size: Punktgröße in Metern; background: Farbe, in die alte Punkte verblassen
  constructor(store, { size = 0.03, background = '#262626' } = {}) {
    this.store = store;
    this.bg = new THREE.Color(background);
    const geo = new THREE.BufferGeometry();
    this.positions = new THREE.BufferAttribute(new Float32Array(CAP * 3), 3);
    this.colors = new THREE.BufferAttribute(new Float32Array(CAP * 3), 3);
    this.positions.setUsage(THREE.DynamicDrawUsage);
    this.colors.setUsage(THREE.DynamicDrawUsage);
    geo.setAttribute('position', this.positions);
    geo.setAttribute('color', this.colors);
    geo.setDrawRange(0, 0);
    this.points = new THREE.Points(geo, new THREE.PointsMaterial({
      size, sizeAttenuation: true, vertexColors: true, map: dotTexture(), alphaTest: 0.5, transparent: false,
    }));
    this.points.frustumCulled = false;
    this._seen = -1;
    this._fadeAt = 0;
    this._c = new THREE.Color();
  }

  set visible(v) { this.points.visible = !!v; }
  get visible() { return this.points.visible; }

  // Weltkoordinaten (x, y, z↑) → Szene (x, z, −y), wie die übrige 3D-Ansicht
  update(now = performance.now() / 1000) {
    if (!this.points.visible) return;
    const s = this.store;
    // neu zeichnen, wenn Punkte dazukamen, sonst zweimal pro Sekunde fürs Verblassen
    if (s.version === this._seen && now - this._fadeAt < 0.5) return;
    this._seen = s.version;
    this._fadeAt = now;
    const p = this.positions.array, c = this.colors.array;
    for (let i = 0; i < s.count; i++) {
      const age = now - s.born[i];
      const x = s.pos[i * 3], y = s.pos[i * 3 + 1], z = s.pos[i * 3 + 2];
      if (age >= LIFE) {
        p[i * 3] = 0; p[i * 3 + 1] = -100; p[i * 3 + 2] = 0;   // unter dem Boden, unsichtbar
        continue;
      }
      p[i * 3] = x; p[i * 3 + 1] = z; p[i * 3 + 2] = -y;
      heightColor(z, this._c).lerp(this.bg, Math.pow(age / LIFE, 1.5) * 0.85);
      c[i * 3] = this._c.r; c[i * 3 + 1] = this._c.g; c[i * 3 + 2] = this._c.b;
    }
    this.positions.needsUpdate = true;
    this.colors.needsUpdate = true;
    this.points.geometry.setDrawRange(0, s.count);
  }
}
