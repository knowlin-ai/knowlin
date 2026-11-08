// Das echte Microduck-Modell: Pollens CAD-Teile, aufgebaut aus dem MJCF-Baum.
// Meshes © Pollen Robotics, CC BY-NC-SA 4.0 – duckpilot verteilt sie nicht, sondern lädt sie beim ersten Start von
// github.com/pollen-robotics/microduck_rl und baut die Datei auf dem PC (duckpilot/modell). Gelenkwinkel in
// MJCF-Konvention (wie der Roboter).
import * as THREE from './vendor/three.module.min.js';
import { toCreasedNormals } from './vendor/BufferGeometryUtils.js';
import { allesVerschmelzen, FARBEN, FINISH } from './formen3d.js';

export { FINISH };

export const MODEL_URL = '/api/modell/ansicht.dpm';

// Lage des Rumpfs aus der Physik als Quaternion (MuJoCo: x vor, y links, z oben → three.js: x, z, −y).
// Gegen die Drehung des Wurzelknotens (st.yaw) verrechnet. Euler-Winkel springen kopfüber um 180° – beim Purzelbaum
// klappte die Ente deshalb mitten in der Rolle sichtbar um. Gibt false zurück, wenn der Zustand keine Lage mitbringt.
const _qWorld = new THREE.Quaternion(), _qYaw = new THREE.Quaternion(), _yAxis = new THREE.Vector3(0, 1, 0);
export function applyBodyQuat(body, st) {
  const q = st.body_q;
  if (!q || q.length !== 4) return false;
  _qWorld.set(q[1], q[3], -q[2], q[0]).normalize();
  _qYaw.setFromAxisAngle(_yAxis, st.yaw || 0).invert();
  body.quaternion.copy(_qYaw.multiply(_qWorld));
  return true;
}

export async function loadModel(url = MODEL_URL) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Modell nicht gefunden (${res.status})`);
  return parseModel(await res.arrayBuffer());
}

// Modell aus schon geladenen Bytes (seit 0.38.29: die Website lädt Odi als JSON und reicht die Bytes direkt durch)
export function parseModel(buf) {
  const dv = new DataView(buf);
  const magic = String.fromCharCode(...new Uint8Array(buf, 0, 4));
  if (magic !== 'DPM1' && magic !== 'DPM2') throw new Error('unbekanntes Modellformat');
  const n = dv.getUint32(4, true);
  const head = JSON.parse(new TextDecoder().decode(new Uint8Array(buf, 8, n)));
  let off = 8 + n;
  const align = () => { off += (4 - (off % 4)) % 4; };
  align();
  const nVert = head.meshes.reduce((s, m) => s + m.v[1], 0);
  const nIdx = head.meshes.reduce((s, m) => s + m.i[1], 0);
  if (magic === 'DPM1') {
    const positions = new Float32Array(buf, off, nVert * 3);
    const indices = new Uint16Array(buf, off + nVert * 12, nIdx);
    return { head, positions, normals: null, indices };
  }
  // DPM2: Positionen je Mesh auf seinen Quader quantisiert (uint16), Normalen int8, Indizes uint16
  const q = new Uint16Array(buf, off, nVert * 3); off += nVert * 6; align();
  const normals = new Int8Array(buf, off, nVert * 3); off += nVert * 3; align();
  const indices = new Uint16Array(buf, off, nIdx);
  const positions = new Float32Array(nVert * 3);
  for (const m of head.meshes) {
    const [v0, count] = m.v;
    for (let i = v0; i < v0 + count; i++) {
      for (let k = 0; k < 3; k++) positions[i * 3 + k] = m.min[k] + q[i * 3 + k] * m.step[k];
    }
  }
  return { head, positions, normals, indices };
}


const v3 = (a) => new THREE.Vector3(a[0], a[1], a[2]);
const q4 = (q) => new THREE.Quaternion(q[1], q[2], q[3], q[0]);   // MJCF w x y z

export class RealDuck {
  constructor(model) {
    const { head } = model;
    this.head = head;
    this.root = new THREE.Group();          // Weltposition und Gierwinkel
    this.body = new THREE.Group();          // Rumpf: Höhe, Kippen, Rollen
    this.root.add(this.body);
    this.mj = new THREE.Group();            // MJCF: z oben  →  three.js: y oben
    this.mj.rotation.x = -Math.PI / 2;
    this.body.add(this.mj);

    // Geometrien einmal bauen, Instanzen teilen sie
    const geos = head.meshes.map((m) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(model.positions.slice(m.v[0] * 3, (m.v[0] + m.v[1]) * 3), 3));
      g.setIndex(new THREE.BufferAttribute(model.indices.slice(m.i[0], m.i[0] + m.i[1]), 1));
      if (model.normals) {
        g.setAttribute('normal', new THREE.BufferAttribute(model.normals.slice(m.v[0] * 3, (m.v[0] + m.v[1]) * 3), 3, true));
        g.computeBoundingSphere();
        return g;
      }
      // altes Format: Positionen ungequantelt, Normalen hier berechnen
      g.setAttribute('position', new THREE.BufferAttribute(model.positions.slice(m.v[0], m.v[0] + m.v[1] * 3), 3));
      const creased = toCreasedNormals(g, Math.PI / 5);
      g.dispose();
      return creased;
    });
    const mats = new Map();
    this.schalen = [];                       // helle Schalen – die tragen die gewählte Farbe (Cream, Graphite, …)
    const matFor = (rgb, finish = 'plastic') => {
      const key = `${rgb.join(',')}|${finish}`;
      if (!mats.has(key)) {
        const c = new THREE.Color().setRGB(rgb[0], rgb[1], rgb[2], THREE.SRGBColorSpace);
        const m = new THREE.MeshPhysicalMaterial({ color: c, ...(FINISH[finish] || FINISH.plastic) });
        if (finish === 'shell' && Math.min(...rgb) > 0.7) this.schalen.push({ m, original: c.clone() });
        mats.set(key, m);
      }
      return mats.get(key);
    };

    this.joints = {};         // Name → Group, die ums Gelenk dreht
    this.axes = {};
    this.sites = {};
    const nodes = [];
    head.bodies.forEach((b, i) => {
      const frame = new THREE.Group();
      frame.name = b.name;
      // Der Rumpf (frei bewegliche Wurzel) liegt im Rumpfursprung: seine Startposition im MJCF (z = 0,12 m)
      // ist die Höhe über dem Boden, und die setzt update() – sonst stünde sie doppelt drin und die Ente schwebte.
      if (b.parent >= 0) frame.position.copy(v3(b.pos));
      frame.quaternion.copy(q4(b.quat));
      const joint = new THREE.Group();
      frame.add(joint);
      (b.parent < 0 ? this.mj : nodes[b.parent]).add(frame);
      nodes[i] = joint;
      if (b.joint) {
        this.joints[b.joint] = joint;
        this.axes[b.joint] = v3(b.axis).normalize();
      }
      for (const [name, pos] of Object.entries(b.sites || {})) {
        const s = new THREE.Object3D();
        s.position.copy(v3(pos));
        joint.add(s);
        this.sites[name] = s;
      }
    });
    for (const p of head.parts) {
      const mesh = new THREE.Mesh(geos[p.mesh], matFor(p.rgb, p.finish));
      mesh.position.copy(v3(p.pos));
      mesh.quaternion.copy(q4(p.quat));
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      nodes[p.body].add(mesh);
    }
    // Gleiche Materialien je Gelenk zusammenfassen: aus 64 Teilen werden wenige Zeichenaufrufe (Bild und Schatten)
    allesVerschmelzen(this.mj);
    // Schnittstelle wie die einfache Ente
    this.headRoll = this.sites.tof || this.joints.head_roll || this.body;
    this.beakTip = this.sites.mouth_tip || this.headRoll;
    this.fallAngle = 0;
    this.current = { ...head.poses.stand, mouth: 0 };
    this._q = new THREE.Quaternion();
    this.setJoints(this.current);
    if (!this.sites.head_camera) this.povNode = this._kopfkamera();   // Open Duck: keine Kamerastelle im Modell
    this._groundRef = this._footHeight();
    // Sohle liegt etwas unter dem Fußpunkt im Modell: einmal messen, damit die Ente weder schwebt noch einsinkt
    this.root.updateMatrixWorld(true);
    this._sole = new THREE.Box3().setFromObject(this.body).min.y - this._groundRef;
    if (!Number.isFinite(this._sole) || Math.abs(this._sole) > 0.03) this._sole = 0;
  }

  // Kopfkamera ohne Stelle im Modell (Open Duck, Fund 7.11.: „Entenblick verdeckt“ – die Kamera saß im Kopf): vorn
  // mittig vor dem Kopf, Blick nach vorn wie der Rumpf in der Ruhelage (+x), oben = +y; dreht danach mit dem Kopf.
  _kopfkamera() {
    const kopf = this.joints.head_roll || this.joints.head_pitch || this.joints.head_yaw;
    if (!kopf) return null;
    this.root.updateMatrixWorld(true);
    const box = new THREE.Box3();
    kopf.traverse((o) => { if (o.isMesh) box.expandByObject(o); });
    if (box.isEmpty()) return null;
    const mitte = box.getCenter(new THREE.Vector3());
    const p = new THREE.Vector3(box.max.x + 0.008, mitte.y, mitte.z);
    const node = new THREE.Object3D();
    node.position.copy(kopf.worldToLocal(p));
    node.quaternion.copy(kopf.getWorldQuaternion(new THREE.Quaternion()).invert());
    kopf.add(node);
    return node;
  }

  // Farbe der Schalen (nur helle Schalen, das Orange bleibt)
  setFarbe(name) {
    const f = FARBEN[name];
    for (const s of this.schalen) {
      if (f == null) s.m.color.copy(s.original); else s.m.color.setHex(f);
    }
  }

  setJoints(values) {
    for (const [name, group] of Object.entries(this.joints)) {
      const v = values[name];
      if (v === undefined || v === null || Number.isNaN(v)) continue;
      const angle = name === 'mouth' ? Math.max(0, Math.min(1, v)) * 0.45 : v;   // Schnabel 0…1 → Winkel
      group.quaternion.setFromAxisAngle(this.axes[name], angle);
    }
  }

  // Tiefster Fuß relativ zum Rumpfursprung (in three.js-Höhe)
  _footHeight() {
    this.body.position.set(0, 0, 0);
    this.body.rotation.set(0, 0, 0);
    this.root.updateMatrixWorld(true);
    const inv = new THREE.Matrix4().copy(this.root.matrixWorld).invert();
    let low = Infinity;
    for (const name of ['left_foot', 'right_foot']) {
      const s = this.sites[name];
      if (!s) continue;
      const p = new THREE.Vector3();
      s.getWorldPosition(p);
      p.applyMatrix4(inv);
      low = Math.min(low, p.y);
    }
    return Number.isFinite(low) ? low : -0.11;
  }

  // Gelenkwinkel aus dem Zustand: gemessen (echter Roboter) oder vom Server berechnet
  _targets(st) {
    const names = this.head.joints;
    const src = st.display_joints && st.display_joints.length === names.length ? st.display_joints : null;
    if (!src) return null;
    const out = {};
    // Open Duck Mini (seit 0.38.4): Winkel kommen in der Konvention der Microduck – auf ihre Gelenke umrechnen
    const um = this.head.von_microduck;
    names.forEach((n, i) => { out[n] = um ? um.ziel[i] + um.vorzeichen[i] * (src[i] - um.stand[i]) : src[i]; });
    if (this.head.antennen && st.antennen && st.antennen.length === 2) {
      this.head.antennen.forEach((n, i) => { out[n] = st.antennen[i]; });   // [rechts, links] wie bei Reachy Mini
    }
    return out;
  }

  update(st, dt) {
    this.root.position.set(st.x, 0, -st.y);
    this.root.rotation.y = st.yaw;
    const want = this._targets(st);
    if (want) {
      const k = Math.min(1, dt * 18);           // leicht glätten: 20-Hz-Zustand, 60-Hz-Bild
      for (const n of Object.keys(want)) {
        const cur = this.current[n] ?? want[n];
        this.current[n] = cur + (want[n] - cur) * k;
      }
      this.setJoints(this.current);
    }
    // Physik-Simulator: Höhe und Lage des Rumpfs kommen aus MuJoCo
    if (st.body && st.body.length === 3) {
      const [z, roll, pitch] = st.body;
      const k = Math.min(1, dt * 20);
      this.fallAngle = 0;
      this.body.position.y += (z - this.body.position.y) * k;
      if (!applyBodyQuat(this.body, st)) this.body.rotation.set(roll, 0, -pitch, 'ZYX');
      return;
    }
    // Rumpf so hoch, dass der tiefere Fuß den Boden berührt
    const pose = st.pose || { z: 0, roll: 0, pitch: 0 };
    let pitch = pose.pitch, roll = pose.roll;
    if (st.skill === 'roulade') pitch = (st.skill_progress || 0) * Math.PI * 2;
    if (st.skill === 'ground_pick') pitch += Math.sin(Math.PI * Math.min(1, (st.skill_progress || 0) * 1.15)) * 0.35;
    const foot = this._footHeight();
    let y = this._groundRef - foot + (this._groundRef < 0 ? -this._groundRef : 0) - this._sole;
    if (st.skill === 'roulade') y += Math.sin((st.skill_progress || 0) * Math.PI) * 0.04;
    const targetFall = st.fallen ? (st.fall_side || 1) * 1.35 : 0;
    this.fallAngle += (targetFall - this.fallAngle) * Math.min(1, dt * (st.fallen ? 9 : 3));
    if (Math.abs(this.fallAngle) > 0.05) y = Math.max(0.05 * Math.abs(Math.sin(this.fallAngle)), y * Math.cos(this.fallAngle));
    this.body.position.y = y;
    this.body.rotation.set(roll + this.fallAngle, 0, -pitch, 'XYZ');
  }
}
