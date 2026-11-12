// SO-101-Arm in der 3D-Ansicht (seit 0.38.47, Etappe G5) – offenes Modell von TheRobotStudio (Apache-2.0), gebacken in
// `static/model/so101.dpm` (duckpilot/modell/so101.py). Steht wie Reachy fest auf einer Fläche; die Gelenkwinkel kommen
// als `display_joints` in der Reihenfolge von `head.joints` (Radiant, „neue Kalibrierung“: Null = Mitte des Bereichs).
// Seit 0.38.48 steht er auf seiner Werkbank; Würfel und Kisten kommen als `werkbank` im Rahmen des Sockels.
// Schnittstelle wie die übrigen Figuren: root, body, headRoll (Greifer), beakTip (zwischen den Backen), update(st, dt).
import * as THREE from './vendor/three.module.min.js';
import { FINISH, loadModel } from './duckmodel.js';
import { allesVerschmelzen } from './formen3d.js';

export const ARM_URL = '/static/model/so101.dpm';
export const ladeArm = () => loadModel(ARM_URL);

const v3 = (a) => new THREE.Vector3(a[0], a[1], a[2]);
const _tip = new THREE.Vector3();

// Offene Kiste aus fünf Brettchen (seit 0.38.48, Werkbank): Boden bei z = 0, im MJCF-Rahmen (z oben)
function kiste(k) {
  const g = new THREE.Group();
  const holz = new THREE.MeshPhysicalMaterial({ color: 0xc9a77c, ...FINISH.plastic });
  const d = 0.004;
  const brett = (sx, sy, sz, x, y, z) => {
    const m = new THREE.Mesh(new THREE.BoxGeometry(sx, sy, sz), holz);
    m.position.set(x, y, z); m.castShadow = m.receiveShadow = true; g.add(m);
  };
  brett(k.s, k.s, d, 0, 0, d / 2);
  for (const sgn of [-1, 1]) {
    brett(d, k.s, k.h, sgn * (k.s - d) / 2, 0, k.h / 2);
    brett(k.s, d, k.h, 0, sgn * (k.s - d) / 2, k.h / 2);
  }
  g.position.set(k.x, k.y, 0);
  return g;
}
// Tic-Tac-Toe-Feld (seit 0.38.54): dunkle Linien auf der Werkbank, je Feld eine unsichtbare Fläche zum Anklicken
function spielfeld(felder) {
  const g = new THREE.Group();
  const linie = new THREE.MeshBasicMaterial({ color: 0x3a2c1f });
  const xs = felder.map((f) => f.x), ys = felder.map((f) => f.y);
  const schritt = Math.abs(xs[3] - xs[0]), x0 = Math.min(...xs), y0 = Math.min(...ys);
  const breite = schritt * 3, mx = x0 + schritt, my = y0 + schritt;
  const matte = new THREE.Mesh(new THREE.BoxGeometry(breite + 0.01, breite + 0.01, 0.0008),
    new THREE.MeshPhysicalMaterial({ color: 0xeee3cf, ...FINISH.plastic }));   // helle Unterlage: Feld gut sichtbar
  matte.position.set(mx, my, 0.0004); matte.receiveShadow = true; g.add(matte);
  for (const k of [-0.5, 0.5]) {
    const a = new THREE.Mesh(new THREE.BoxGeometry(0.004, breite, 0.0012), linie);
    a.position.set(mx + k * schritt, my, 0.0009); g.add(a);
    const b = new THREE.Mesh(new THREE.BoxGeometry(breite, 0.004, 0.0012), linie);
    b.position.set(mx, my + k * schritt, 0.0009); g.add(b);
  }
  const leer = new THREE.MeshBasicMaterial({ transparent: true, opacity: 0, depthWrite: false });
  for (const f of felder) {
    const m = new THREE.Mesh(new THREE.PlaneGeometry(schritt * 0.95, schritt * 0.95), leer);
    m.position.set(f.x, f.y, 0.0016);
    m.userData.werkstueck = { name: f.name, art: 'feld' };
    g.add(m);
  }
  return g;
}
const q4 = (q) => new THREE.Quaternion(q[1], q[2], q[3], q[0]);   // MJCF w x y z

export class RealArm {
  constructor(model) {
    const { head } = model;
    this.head = head;
    this.istArm = true;
    this.root = new THREE.Group();               // Lage auf der Fläche, Ausrichtung
    this.body = new THREE.Group();
    this.root.add(this.body);
    this.mj = new THREE.Group();                 // MJCF: z oben → three.js: y oben
    this.mj.rotation.x = -Math.PI / 2;
    this.body.add(this.mj);
    const geos = head.meshes.map((m) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(model.positions.slice(m.v[0] * 3, (m.v[0] + m.v[1]) * 3), 3));
      g.setAttribute('normal', new THREE.BufferAttribute(model.normals.slice(m.v[0] * 3, (m.v[0] + m.v[1]) * 3), 3, true));
      g.setIndex(new THREE.BufferAttribute(model.indices.slice(m.i[0], m.i[0] + m.i[1]), 1));
      g.computeBoundingSphere();
      return g;
    });
    const mats = new Map();
    const matFor = (rgb, finish) => {
      const key = `${rgb.join(',')}|${finish}`;
      if (!mats.has(key)) {
        const c = new THREE.Color().setRGB(rgb[0], rgb[1], rgb[2], THREE.SRGBColorSpace);
        mats.set(key, new THREE.MeshPhysicalMaterial({ color: c, ...(FINISH[finish] || FINISH.plastic) }));
      }
      return mats.get(key);
    };
    this.joints = {};
    this.axes = {};
    this.sites = {};
    const nodes = [];
    head.bodies.forEach((b, i) => {
      const frame = new THREE.Group();
      frame.position.copy(v3(b.pos));
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
    allesVerschmelzen(this.mj);
    this.headRoll = this.joints.wrist_roll || this.body;
    // Greifmitte wie in duckpilot/arm_kinematik.py: 12 mm vom „gripperframe“ zur beweglichen Backe
    this.beakTip = this.headRoll;
    if (this.sites.gripperframe) {
      this.beakTip = new THREE.Object3D();
      this.beakTip.position.copy(this.sites.gripperframe.position).add(new THREE.Vector3(0.012, 0, 0));
      this.sites.gripperframe.parent.add(this.beakTip);
    }
    this.povNode = this.beakTip;
    this.current = { ...head.poses.stand };
    this.setJoints(this.current);
    this.werkbank = new THREE.Group();            // Würfel und Kisten im Rahmen des Sockels (seit 0.38.48)
    this.mj.add(this.werkbank);
    this.wuerfel = new Map();
    this.kistenGebaut = '';
  }

  _werkbank(wb) {
    const schluessel = JSON.stringify(wb.kisten || []);
    if (schluessel !== this.kistenGebaut) {
      this.kistenGebaut = schluessel;
      for (const c of [...this.werkbank.children]) if (c.userData.kiste) this.werkbank.remove(c);
      for (const k of wb.kisten || []) {
        const g = kiste(k);
        g.userData.kiste = true;
        g.traverse((o) => { o.userData.werkstueck = { name: k.name, art: 'kiste' }; });   // anklickbar (seit 0.38.53)
        this.werkbank.add(g);
      }
    }
    const feldSchluessel = JSON.stringify((wb.felder || []).map((f) => f.name));
    if (feldSchluessel !== this.felderGebaut) {   // Spiel beginnt oder endet
      this.felderGebaut = feldSchluessel;
      if (this.spielfeld) { this.werkbank.remove(this.spielfeld); this.spielfeld = null; }
      if ((wb.felder || []).length) { this.spielfeld = spielfeld(wb.felder); this.werkbank.add(this.spielfeld); }
    }
    const da = new Set((wb.dinge || []).map((d) => d.name));
    for (const [name, m] of this.wuerfel) if (!da.has(name)) { this.werkbank.remove(m); this.wuerfel.delete(name); }
    const a = wb.wuerfel || 0.03;
    for (const d of wb.dinge || []) {
      let m = this.wuerfel.get(d.name);
      if (!m) {
        m = new THREE.Mesh(new THREE.BoxGeometry(a, a, a),
          new THREE.MeshPhysicalMaterial({ color: new THREE.Color(d.farbe), ...FINISH.plastic }));
        m.castShadow = m.receiveShadow = true;
        m.userData.werkstueck = { name: d.name, art: 'wuerfel' };
        this.wuerfel.set(d.name, m);
        this.werkbank.add(m);
      }
      if (wb.haelt === d.name) {                  // im Greifer: dort, wo die Spitze ist
        this.beakTip.getWorldPosition(_tip);
        m.position.copy(this.mj.worldToLocal(_tip));
      } else {
        m.position.set(d.x, d.y, d.z);
      }
    }
  }

  setFarbe() { /* der SO-101 behält seine Druckfarbe */ }

  setJoints(values) {
    for (const [name, group] of Object.entries(this.joints)) {
      const v = values[name];
      if (v === undefined || v === null || Number.isNaN(v)) continue;
      group.quaternion.setFromAxisAngle(this.axes[name], v);
    }
  }

  update(st, dt) {
    this.root.position.set(st.x, st.stand_z || 0, -st.y);
    this.root.rotation.y = st.yaw || 0;
    const names = this.head.joints;
    const src = st.display_joints && st.display_joints.length === names.length ? st.display_joints : null;
    if (!src) return;
    const k = Math.min(1, dt * 18);               // 20-Hz-Zustand, 60-Hz-Bild: leicht glätten
    names.forEach((n, i) => { this.current[n] += (src[i] - this.current[n]) * k; });
    this.setJoints(this.current);
    if (st.werkbank && st.werkbank.dinge) {
      this.root.updateMatrixWorld(true);
      this._werkbank(st.werkbank);
    }
  }
}
