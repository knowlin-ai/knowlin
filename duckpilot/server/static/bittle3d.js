// Bittle X in der 3D-Ansicht (seit 0.38.59). Gezeichnet nach Fotos, ohne Dateien von Petoi: flacher Rumpf, vier Beine
// mit Schulter und Knie (Knie zeigen zur Körpermitte wie beim echten Bittle), Kopf vorn, der sich seitlich dreht.
// Gleiche Schnittstelle wie die übrigen Figuren: root, body, headRoll, beakTip, povNode, update(st, dt).
// Laufen: Trab aus `st.gait_phase` (diagonale Beinpaare gegenläufig); sitzen: hinten eingeknickt; stromlos: liegt flach.
// Koordinaten wie in duck3d.js: Simulator x = vorn, y = links, z = oben → three.js X = x, Y = z, Z = -y.
import * as THREE from './vendor/three.module.min.js';
import { allesVerschmelzen, rundKasten, stoff, teil } from './formen3d.js';

const F = { rumpf: 0xe9e7e2, dunkel: 0x2b2d31, akzent: 0xf0962c, auge: 0x15171a };
const OBEN = 0.046, UNTEN = 0.05;          // Ober- und Unterschenkel
const BEINE = [                             // [x vorn, z rechts, vorn?]
  [0.052, -0.04, true], [0.052, 0.04, true], [-0.052, -0.04, false], [-0.052, 0.04, false],
];
const STAND = { s: 0.45, k: -0.85 };        // Schulter und Knie im Stand (rad), vorn; hinten gespiegelt
const SITZ = 0.45;                          // Rumpfneigung im Sitzen (rad, vorn hoch)

// Höhe der Schulter über dem Fuß für Schulter- und Kniewinkel
const hoehe = (s, k) => OBEN * Math.cos(s) + UNTEN * Math.cos(s + k);

export class Bittle {
  constructor() {
    this.root = new THREE.Group();
    const rumpf = stoff(F.rumpf, 'shell'), dunkel = stoff(F.dunkel, 'servo'), akzent = stoff(F.akzent, 'plastic');
    this.body = new THREE.Group();
    this.root.add(this.body);
    teil(this.body, rundKasten(0.14, 0.036, 0.074, 0.012, 3), rumpf, 0, 0, 0);
    teil(this.body, rundKasten(0.09, 0.006, 0.05, 0.003, 2), akzent, 0, 0.02, 0);       // Deckel mit Platine
    // Beine: Schultergelenk (Drehung um Z), darunter Knie
    this.beine = BEINE.map(([x, z, vorn]) => {
      const schulter = new THREE.Group();
      schulter.position.set(x, -0.006, z * 1.08);
      this.body.add(schulter);
      teil(schulter, new THREE.CylinderGeometry(0.009, 0.009, 0.012, 16), dunkel, 0, 0, 0, Math.PI / 2, 0, 0);
      teil(schulter, rundKasten(0.014, OBEN, 0.012, 0.004, 2), dunkel, 0, -OBEN / 2, 0);
      const knie = new THREE.Group();
      knie.position.y = -OBEN;
      schulter.add(knie);
      teil(knie, rundKasten(0.012, UNTEN, 0.01, 0.004, 2), rumpf, 0, -UNTEN / 2, 0);
      teil(knie, new THREE.SphereGeometry(0.007, 12, 8), dunkel, 0, -UNTEN, 0);
      return { schulter, knie, vorn };
    });
    // Kopf: Halsgelenk (seitlich drehen), dann leichtes Nicken mit dem Vorderkörper
    this.headYaw = new THREE.Group();
    this.headYaw.position.set(0.075, 0.016, 0);
    this.body.add(this.headYaw);
    this.headPitch = new THREE.Group();
    this.headYaw.add(this.headPitch);
    this.headRoll = new THREE.Group();
    this.headPitch.add(this.headRoll);
    teil(this.headRoll, rundKasten(0.044, 0.04, 0.05, 0.012, 3), rumpf, 0.016, 0.012, 0);
    for (const s of [-1, 1]) {
      teil(this.headRoll, new THREE.SphereGeometry(0.0065, 16, 10), stoff(F.auge, 'glass'), 0.038, 0.018, 0.012 * s);
      teil(this.headRoll, rundKasten(0.008, 0.02, 0.012, 0.003, 2), dunkel, 0.002, 0.036, 0.018 * s, 0, 0, s * 0.25);   // Ohren
    }
    this.beakTip = new THREE.Object3D();
    this.beakTip.position.set(0.05, 0.01, 0);
    this.headRoll.add(this.beakTip);
    this.povNode = new THREE.Object3D();
    this.povNode.position.set(0.04, 0.02, 0);
    this.headRoll.add(this.povNode);
    this._lage = { yaw: 0, pitch: 0 };
    this._s = BEINE.map(() => STAND.s);
    this._k = BEINE.map(() => STAND.k);
    this._sitz = 0;
    this._fall = 0;
    allesVerschmelzen(this.root);
  }

  update(st, dt) {
    this.root.position.set(st.x || 0, 0, -(st.y || 0));
    this.root.rotation.y = st.yaw || 0;
    const k = Math.min(1, dt * 10);
    const ziel = st.kopf_lage || {};
    for (const n of ['yaw', 'pitch']) this._lage[n] += ((ziel[n] || 0) - this._lage[n]) * k;
    this.headYaw.rotation.y = this._lage.yaw;
    this.headPitch.rotation.z = -this._lage.pitch;

    const wach = st.powered !== false;
    const sitzt = !!st.sitting && wach;
    this._sitz += ((sitzt ? 1 : 0) - this._sitz) * Math.min(1, dt * 4);
    const t = st.twist || {};
    const laeuft = wach && !sitzt && (Math.hypot(t.vx || 0, t.vy || 0) > 0.01 || Math.abs(t.vyaw || 0) > 0.08);
    const ph = st.gait_phase || 0;
    this.beine.forEach((b, i) => {
      const seite = b.vorn ? 1 : -1;                     // Knie zeigen zur Mitte: vorn nach hinten, hinten nach vorn
      let s = STAND.s * seite, kn = STAND.k * seite;
      if (laeuft) {                                       // Trab: Beine 0 und 3, 1 und 2 im Gleichschritt
        const p = ph + (i === 0 || i === 3 ? 0 : Math.PI);
        s += 0.32 * Math.sin(p);
        kn += -0.45 * Math.max(0, Math.cos(p)) * seite;
      }
      if (this._sitz > 0.01) {                            // sitzen: vorn senkrecht, hinten unter den Körper geklappt
        const [ss, sk] = b.vorn ? [-SITZ, 0] : [0.9 - SITZ, -1.9];
        s += (ss - s) * this._sitz;
        kn += (sk - kn) * this._sitz;
      }
      if (!wach) { s = 1.25 * seite; kn = -2.4 * seite; } // stromlos: Beine eingeklappt, liegt flach
      this._s[i] += (s - this._s[i]) * Math.min(1, dt * 12);
      this._k[i] += (kn - this._k[i]) * Math.min(1, dt * 12);
      b.schulter.rotation.z = this._s[i];
      b.knie.rotation.z = this._k[i];
    });
    // Rumpfhöhe aus den Vorderbeinen; sitzend vorn hoch, hinten tief
    const vorn = Math.max(0.02, hoehe(this._s[0], this._k[0]));
    let y = vorn + 0.006, neigung = 0;
    if (this._sitz > 0.01) {                              // Vorderfüße am Boden, Rumpf vorn hoch
      neigung = SITZ * this._sitz;
      y += ((OBEN + UNTEN) - 0.052 * Math.sin(SITZ) + 0.006 - y) * this._sitz;
    }
    if (!wach) { y = 0.028; neigung = 0; }
    const fallZiel = st.fallen ? (st.fall_side || 1) * 1.4 : 0;
    this._fall += (fallZiel - this._fall) * Math.min(1, dt * (st.fallen ? 9 : 3));
    if (Math.abs(this._fall) > 0.05) y = Math.max(0.04, y * Math.cos(this._fall));
    this.body.position.y = y;
    this.body.rotation.set(this._fall, 0, neigung, 'XYZ');
  }
}
