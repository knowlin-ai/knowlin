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
const glatt = (x) => { const c = Math.max(0, Math.min(1, x)); return c * c * (3 - 2 * c); };
const huelle = (p, rein = 0.2, raus = 0.82) => Math.min(glatt(p / rein), 1 - glatt((p - raus) / (1 - raus)));
const welle = (p, mal) => 0.5 - 0.5 * Math.cos(2 * Math.PI * mal * p);

// Bellos Tricks (seit 0.38.61, nach Petois eingebauten Tricks; Namen wie backends/bittle.py TRICKS).
// Je Trick und Fortschritt p (0…1): Schulter s und Knie k je Bein [vl, vr, hl, hr], Rumpfhöhe y, Neigung n
// (+ = vorn hoch), Kippen r (zur Seite), Kopf kd (drehen) und kp (heben), e = wie weit die Pose gilt (0 = Stand, 1 = Pose).
const SITZEN = { s: [-SITZ, -SITZ, 0.9 - SITZ, 0.9 - SITZ], k: [0, 0, -1.9, -1.9], y: OBEN + UNTEN - 0.052 * Math.sin(SITZ) + 0.006, n: SITZ };
const STEHEN = { s: [0.45, 0.45, -0.45, -0.45], k: [-0.85, -0.85, 0.85, 0.85], y: 0.083, n: 0 };
// Männchen: Rumpf steil (n = 1), Hinterbeine wie beim Sitzen unter dem Körper, Vorderpfoten angewinkelt vor der Brust
const MAENNCHEN = { s: [0.3, 0.3, -0.1, -0.1], k: [-1.5, -1.5, -1.9, -1.9], y: 0.057 + 0.052 * Math.sin(1.0), n: 1.0 };
const TRICKS = {
  pfote: (p) => { const w = 0.25 * Math.sin(2 * Math.PI * 3 * p);
    return { ...SITZEN, s: [1.45 + w, -SITZ, 0.9 - SITZ, 0.9 - SITZ], k: [-0.5, 0, -1.9, -1.9], e: huelle(p) }; },
  strecken: (p) => ({ s: [1.15, 1.15, -0.45, -0.45], k: [-0.15, -0.15, 0.85, 0.85], y: 0.062, n: -0.32, kp: 0.3, e: huelle(p, 0.3, 0.75) }),
  verbeugen: (p) => ({ s: [1.0, 1.0, -0.15, -0.15], k: [-2.05, -2.05, 0.35, 0.35], y: 0.058, n: -0.48, kp: 0.45, e: huelle(p, 0.25, 0.75) }),
  liegestuetze: (p) => { const u = welle((p - 0.15) / 0.7, 3) * (p > 0.15 && p < 0.85 ? 1 : 0);
    return { s: [0.45 + 0.5 * u, 0.45 + 0.5 * u, -0.45, -0.45], k: [-0.85 - 0.95 * u, -0.85 - 0.95 * u, 0.85, 0.85],
      y: 0.083 - 0.026 * u, n: -0.22 * u, e: huelle(p, 0.12, 0.88) }; },
  platz: (p) => ({ s: [1.25, 1.25, -1.25, -1.25], k: [-2.4, -2.4, 2.4, 2.4], y: 0.03, n: 0, kd: 0.3 * Math.sin(2 * Math.PI * p), e: huelle(p, 0.2, 0.85) }),
  tot_stellen: (p) => ({ s: [0.25, 0.3, -0.3, -0.25], k: [-0.2, -0.3, 0.3, 0.2], y: 0.04, n: 0, r: 1.45, e: huelle(p, 0.18, 0.86) }),
  boxen: (p) => { const a = Math.sin(2 * Math.PI * 4 * p), b = Math.sin(2 * Math.PI * 4 * p + Math.PI);
    return { ...SITZEN, n: SITZ * 1.25, s: [1.15 + 0.45 * a, 1.15 + 0.45 * b, 0.9 - SITZ, 0.9 - SITZ], k: [-0.7, -0.7, -1.9, -1.9], e: huelle(p) }; },
  umschauen: (p) => ({ s: [0.45, 0.45, -0.45, -0.45], k: [-0.85, -0.85, 0.85, 0.85], y: 0.083, n: 0.05,
    kd: 0.95 * Math.sin(2 * Math.PI * p), e: huelle(p, 0.1, 0.9) }),
  handstand: (p) => ({ s: [1.3, 1.3, 0.2, 0.2], k: [0, 0, -0.6, -0.6], y: 0.146, n: -1.3, kp: 1.15, e: huelle(p, 0.3, 0.75) }),
  // Salto: Rumpf dreht einmal ganz herum (n bis 2π) und fliegt dabei hoch; Beine angezogen; wirkt direkt, nicht geglättet
  salto: (p) => { const q = glatt((p - 0.18) / 0.62);
    return { s: [1.1, 1.1, -1.1, -1.1], k: [-1.9, -1.9, 1.9, 1.9], y: 0.083 + 0.12 * Math.sin(Math.PI * q), n: (2 * Math.PI * q) % (2 * Math.PI),
      e: huelle(p, 0.15, 0.85), direkt: p > 0.15 && p < 0.85 }; },
  // Seit 0.38.64 nach Petois OpenCat-Fähigkeiten (Kürzel dahinter). Weltwinkel eines Beins = s + n.
  maennchen: (p) => ({ ...MAENNCHEN, kp: -0.8, e: huelle(p, 0.25, 0.8) }),                                        // hu
  high_five: (p) => ({ ...SITZEN, s: [1.95, -SITZ, 0.9 - SITZ, 0.9 - SITZ], k: [-0.2, 0, -1.9, -1.9], kp: 0.25, e: huelle(p, 0.25, 0.8) }), // fiv
  jubeln: (p) => { const a = Math.sin(2 * Math.PI * 4 * p);                                                        // chr
    return { ...MAENNCHEN, s: [0.5 + 0.55 * a, 0.5 - 0.55 * a, MAENNCHEN.s[2], MAENNCHEN.s[3]], k: [-0.6, -0.6, -1.9, -1.9], kp: -0.6, e: huelle(p, 0.2, 0.82) }; },
  nicken: (p) => ({ ...STEHEN, kp: 0.35 * Math.sin(2 * Math.PI * 3 * p), e: huelle(p, 0.1, 0.9) }),                // nd
  schnueffeln: (p) => ({ s: [0.65, 0.65, -0.25, -0.25], k: [-1.3, -1.3, 0.85, 0.85], y: 0.07, n: -0.2,           // snf
    kp: -0.25, kd: 0.5 * Math.sin(2 * Math.PI * 2 * p), e: huelle(p, 0.15, 0.85) }),
  kratzen: (p) => ({ ...SITZEN, s: [-SITZ, -SITZ, 1.55 + 0.25 * Math.sin(2 * Math.PI * 8 * p), 0.9 - SITZ],           // scrh
    k: [0, 0, -1.2, -1.9], kd: 0.35, e: huelle(p, 0.2, 0.82) }),
  graben: (p) => { const a = Math.sin(2 * Math.PI * 5 * p);                                                         // dg
    return { s: [0.9 + 0.5 * a, 0.9 - 0.5 * a, -0.15, -0.15], k: [-1.6 - 0.4 * a, -1.6 + 0.4 * a, 0.85, 0.85], y: 0.07, n: -0.3, kp: 0.1, e: huelle(p, 0.15, 0.85) }; },
  kicken: (p) => { const u = welle(p, 2);                                                                           // kc
    return { ...STEHEN, s: [0.45, 0.45, -0.45, -0.45 - 1.0 * u], k: [-0.85, -0.85, 0.85, 0.85 - 0.8 * u], n: -0.12 * u, e: huelle(p, 0.1, 0.9) }; },
  springen: (p) => { const c = glatt(p / 0.35) * (1 - glatt((p - 0.35) / 0.08)), j = Math.sin(Math.PI * Math.max(0, Math.min(1, (p - 0.4) / 0.3)));  // jmp
    return { s: [0.45 + 0.5 * c, 0.45 + 0.5 * c, -0.45 - 0.5 * c, -0.45 - 0.5 * c], k: [-0.85 - 0.9 * c, -0.85 - 0.9 * c, 0.85 + 0.9 * c, 0.85 + 0.9 * c],
      y: 0.083 - 0.025 * c + 0.05 * j, n: 0, e: huelle(p, 0.08, 0.9), direkt: p > 0.38 && p < 0.72 }; },
  tisch: (p) => ({ s: [0, 0, 0, 0], k: [0, 0, 0, 0], y: OBEN + UNTEN + 0.006, n: 0, kp: 0, e: huelle(p, 0.2, 0.85) }),  // tbl
  schlafen: (p) => ({ s: [1.25, 1.25, -1.25, -1.25], k: [-2.4, -2.4, 2.4, 2.4], y: 0.03 + 0.002 * Math.sin(2 * Math.PI * 3 * p), n: 0,  // zz
    kp: -0.45, kd: 0, e: huelle(p, 0.15, 0.9) }),
  frontsalto: (p) => { const q = glatt((p - 0.18) / 0.62);                                                         // ff
    return { s: [1.1, 1.1, -1.1, -1.1], k: [-1.9, -1.9, 1.9, 1.9], y: 0.083 + 0.12 * Math.sin(Math.PI * q), n: -((2 * Math.PI * q) % (2 * Math.PI)),
      e: huelle(p, 0.15, 0.85), direkt: p > 0.15 && p < 0.85 }; },
};

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
    const trick = wach && TRICKS[st.skill] ? TRICKS[st.skill](Math.max(0, Math.min(1, st.skill_progress || 0))) : null;
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
      if (trick) { s += (trick.s[i] - s) * trick.e; kn += (trick.k[i] - kn) * trick.e; }
      if (!wach) { s = 1.25 * seite; kn = -2.4 * seite; } // stromlos: Beine eingeklappt, liegt flach
      const f = trick && trick.direkt ? 1 : Math.min(1, dt * 12);
      this._s[i] += (s - this._s[i]) * f;
      this._k[i] += (kn - this._k[i]) * f;
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
    let kippen = 0;
    if (trick) {                                          // Trick: Höhe, Neigung, Kippen und Kopf aus der Pose
      y += (trick.y - y) * trick.e;
      neigung += (trick.n - neigung) * trick.e;
      kippen = (trick.r || 0) * trick.e;
      if (trick.kd !== undefined) this.headYaw.rotation.y = trick.kd * trick.e;
      if (trick.kp !== undefined) this.headPitch.rotation.z = trick.kp * trick.e;   // Kopf heben (nach vorn schauen)
    }
    if (!trick || !trick.direkt) {                        // sanft hinein und heraus; beim Salto direkt
      this._y = this._y === undefined ? y : this._y + (y - this._y) * Math.min(1, dt * 10);
      this._n = this._n === undefined ? neigung : this._n + (neigung - this._n) * Math.min(1, dt * 10);
      y = this._y; neigung = this._n;
    } else { this._y = y; this._n = neigung; }
    if (!wach) { y = 0.028; neigung = 0; this._y = y; this._n = 0; }
    const fallZiel = st.fallen ? (st.fall_side || 1) * 1.4 : 0;
    this._fall += (fallZiel - this._fall) * Math.min(1, dt * (st.fallen ? 9 : 3));
    if (Math.abs(this._fall) > 0.05) y = Math.max(0.04, y * Math.cos(this._fall));
    this.body.position.y = y;
    this.body.rotation.set(this._fall + kippen, 0, neigung, 'XYZ');
  }
}
