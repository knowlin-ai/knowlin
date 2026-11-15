// Bittle X in der 3D-Ansicht (seit 0.38.59). Gezeichnet nach Fotos, ohne Dateien von Petoi: flacher Rumpf, vier Beine
// mit Schulter und Knie (Knie zeigen zur Körpermitte wie beim echten Bittle), Kopf vorn, der sich seitlich dreht.
// Gleiche Schnittstelle wie die übrigen Figuren: root, body, headRoll, beakTip, povNode, update(st, dt).
// Seit 0.38.65 („Bello wie das Original“): Maße nach Petois offenem Simulationsmodell (bittle_simple.xml, MIT) – nur die
// Zahlen, keine Dateien. Laufen je Gangart aus `st.gait_phase` und `st.gangart` (Traben, Krabbeln, Hoppeln); die Rumpfhöhe
// kommt aus den Beinen (der tiefste Fuß, das tiefste Knie oder die Rumpfunterseite steht auf dem Boden), nur Sprünge,
// Salti und Rollen setzen sie selbst.
// Koordinaten wie in duck3d.js: Simulator x = vorn, y = links, z = oben → three.js X = x, Y = z, Z = -y.
import * as THREE from './vendor/three.module.min.js';
import { allesVerschmelzen, rundKasten, stoff, teil } from './formen3d.js';

const F = { rumpf: 0xe9e7e2, dunkel: 0x2b2d31, akzent: 0xf0962c, auge: 0x15171a };
// Petois Modell: Hüften ±7,35 cm vorn/hinten und ±4,85 cm seitlich, Oberschenkel 4,6 cm, Unterschenkel 5,5 cm,
// Rumpfplatte 12,7 × 9 cm
export const MASSE = { hueftX: 0.0735, hueftZ: 0.0485, oben: 0.046, unten: 0.055, laenge: 0.127, breite: 0.09, dicke: 0.034 };
const OBEN = MASSE.oben, UNTEN = MASSE.unten;
const HUEFT_Y = -0.006;                     // Hüftachse unter der Rumpfmitte
const FUSS_R = 0.007;                       // Fußkugel
const BEINE = [                             // [x vorn, z rechts, vorn?]: vorn links, vorn rechts, hinten links, hinten rechts
  [MASSE.hueftX, -MASSE.hueftZ, true], [MASSE.hueftX, MASSE.hueftZ, true],
  [-MASSE.hueftX, -MASSE.hueftZ, false], [-MASSE.hueftX, MASSE.hueftZ, false],
];
const STAND = { s: 0.45, k: -0.85 };        // Schulter und Knie im Stand (rad), vorn; hinten gespiegelt

const glatt = (x) => { const c = Math.max(0, Math.min(1, x)); return c * c * (3 - 2 * c); };
const huelle = (p, rein = 0.2, raus = 0.82) => Math.min(glatt(p / rein), 1 - glatt((p - raus) / (1 - raus)));
const welle = (p, mal) => 0.5 - 0.5 * Math.cos(2 * Math.PI * mal * p);

// Knie und Fuß eines Beins relativ zur Hüfte (Schulter s, Knie k; Drehung um Z wie in three.js)
const knieLage = (s) => [OBEN * Math.sin(s), -OBEN * Math.cos(s)];
const fussLage = (s, k) => [OBEN * Math.sin(s) + UNTEN * Math.sin(s + k), -OBEN * Math.cos(s) - UNTEN * Math.cos(s + k)];

// Rumpfhöhe, bei der der tiefste Punkt (Fußkugel, Knie, Rumpfecke) gerade den Boden berührt – Neigung n (+ = vorn hoch)
export function bodenHoehe(s, k, n = 0) {
  const c = Math.cos(n), si = Math.sin(n);
  const welt = (x, y) => x * si + y * c;    // Höhe eines Rumpfpunkts nach der Neigung
  let tief = Infinity;
  BEINE.forEach(([x], i) => {
    const [kx, ky] = knieLage(s[i]), [fx, fy] = fussLage(s[i], k[i]);
    tief = Math.min(tief, welt(x + fx, HUEFT_Y + fy) - FUSS_R, welt(x + kx, HUEFT_Y + ky) - 0.006);
  });
  for (const x of [-MASSE.laenge / 2, MASSE.laenge / 2]) tief = Math.min(tief, welt(x, -MASSE.dicke / 2));
  return -tief;
}

// Höhe der Fußsohlen über dem Boden bei Rumpfhöhe y (für Prüfungen: welche Füße stehen gerade auf?)
export function fussHoehen(s, k, n, y) {
  const c = Math.cos(n), si = Math.sin(n);
  return BEINE.map(([x], i) => { const [fx, fy] = fussLage(s[i], k[i]); return y + (x + fx) * si + (HUEFT_Y + fy) * c - FUSS_R; });
}

// Neigung, bei der Vorder- und Hinterfüße zugleich aufstehen (seit 0.38.65 – mit Petois Beinlängen hingen sonst im Sitzen
// die Vorderpfoten und beim Strecken die Hinterpfoten in der Luft). baue(n) → Pose {s, k}; gesucht wird n, bei dem der
// tiefste Vorderfuß so hoch steht wie der tiefste Hinterfuß.
export function neigungFuer(baue, von = -1.3, bis = 1.3) {
  const abstand = (n) => { const p = baue(n), y = bodenHoehe(p.s, p.k, n), h = fussHoehen(p.s, p.k, n, y);
    return Math.min(h[0], h[1]) - Math.min(h[2], h[3]); };
  let lo = von, hi = bis;
  for (let i = 0; i < 40; i++) { const m = (lo + hi) / 2; if (abstand(m) > 0) hi = m; else lo = m; }
  return (lo + hi) / 2;
}
// Pose so neigen, dass vorn und hinten je ein Fuß aufsteht (Beinwinkel bleiben relativ zum Rumpf)
const ausgleichen = (pose) => ({ ...pose, n: neigungFuer(() => pose) });
// Sitzen: Vorderbeine senkrecht in der Welt, Hinterbeine unter den Körper geklappt (Oberschenkel 0,9 rad zur Senkrechten)
const sitzBeine = (n) => ({ s: [-n, -n, 0.9 - n, 0.9 - n], k: [0, 0, -1.9, -1.9] });
export const SITZ = neigungFuer(sitzBeine, 0.1, 1.2);       // Rumpfneigung im Sitzen (rad, vorn hoch)

// Gangarten (seit 0.38.65, nach Petois Gangarten; Namen wie backends/bittle.py GANGARTEN): Versatz der Beine im Takt,
// Anteil des Schritts in der Luft, Ausschlag der Schulter, Kniehub, Ducken (Beine stärker eingeknickt), Wippen des Rumpfs.
// Traben: diagonale Paare; Krabbeln: ein Bein nach dem anderen (hinten links, vorn links, hinten rechts, vorn rechts),
// drei Füße fast immer am Boden; Hoppeln: vorn und hinten paarweise.
export const GANGARTEN = {
  traben: { versatz: [0, Math.PI, Math.PI, 0], luft: 0.45, schritt: 0.024, hub: 0.022, ducken: 0, wippen: 0 },
  krabbeln: { versatz: [Math.PI / 2, 3 * Math.PI / 2, 0, Math.PI], luft: 0.22, schritt: 0.018, hub: 0.016, ducken: 1, wippen: 0 },
  hoppeln: { versatz: [0, 0, Math.PI, Math.PI], luft: 0.4, schritt: 0.03, hub: 0.026, ducken: 0.3, wippen: 0.12 },
};

// Ein Bein im Schritt: vor (+1) in der Luft, zurück (−1) am Boden – am Boden gleichmäßig, damit der Fuß nicht rutscht
function schritt(p, luft) {
  const u = (((p % (2 * Math.PI)) + 3 * Math.PI) % (2 * Math.PI)) - Math.PI;     // −π … π, Mitte der Luftphase bei 0
  const a = Math.PI * luft;
  if (Math.abs(u) < a) { const q = (u + a) / (2 * a); return { vor: -Math.cos(Math.PI * q), hub: Math.sin(Math.PI * q) }; }
  const t = (((u - a) % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI) / (2 * Math.PI - 2 * a);
  return { vor: 1 - 2 * t, hub: 0 };
}

// Beinwinkel für einen Fußpunkt (x vor, y nach oben, relativ zur Hüfte) – zwei Glieder, Knie zur Körpermitte
export function beinFuer(x, y, vorn) {
  const d2 = x * x + y * y;
  const c = Math.max(-1, Math.min(1, (d2 - OBEN * OBEN - UNTEN * UNTEN) / (2 * OBEN * UNTEN)));
  const k = (vorn ? -1 : 1) * Math.acos(c);
  const s = Math.atan2(x, -y) - Math.atan2(UNTEN * Math.sin(k), OBEN + UNTEN * Math.cos(k));
  return [s, k];
}

// Beinwinkel im Gang: Phase ph, Richtung +1 vorwärts / -1 rückwärts, Ausschlag-Faktor (0 = auf der Stelle). Die Füße
// laufen auf Bahnen: am Boden auf gleicher Höhe nach hinten, in der Luft im Bogen nach vorn – so stehen die Stützbeine
// wirklich auf und rutschen nicht.
export function gangBeine(gang, ph, richtung = 1, weit = 1) {
  const g = GANGARTEN[gang] || GANGARTEN.traben;
  const s = [], k = [];
  BEINE.forEach(([, , vorn], i) => {
    const seite = vorn ? 1 : -1;
    const [x0, y0] = fussLage((STAND.s + 0.25 * g.ducken) * seite, (STAND.k - 0.5 * g.ducken) * seite);
    const b = schritt(ph + g.versatz[i], g.luft);
    const [si, ki] = beinFuer(x0 + g.schritt * weit * richtung * b.vor, y0 + g.hub * b.hub, vorn);
    s.push(si); k.push(ki);
  });
  return { s, k, n: g.wippen * Math.sin(ph) };
}

// Bellos Tricks (seit 0.38.61, nach Petois eingebauten Tricks; Namen wie backends/bittle.py TRICKS).
// Je Trick und Fortschritt p (0…1): Schulter s und Knie k je Bein [vl, vr, hl, hr], Rumpfhöhe y, Neigung n
// (+ = vorn hoch), Kippen r (zur Seite), Kopf kd (drehen) und kp (heben), e = wie weit die Pose gilt (0 = Stand, 1 = Pose).
const SITZEN = { ...sitzBeine(SITZ), n: SITZ };
const STEHEN = { s: [0.45, 0.45, -0.45, -0.45], k: [-0.85, -0.85, 0.85, 0.85], n: 0 };
const STAND_Y = bodenHoehe(STEHEN.s, STEHEN.k, 0);
// Männchen: Rumpf steil (n = 1), Hinterbeine wie beim Sitzen unter dem Körper, Vorderpfoten angewinkelt vor der Brust
const MAENNCHEN = { s: [0.3, 0.3, -0.1, -0.1], k: [-1.5, -1.5, -1.9, -1.9], n: 1.0 };
export const TRICKS = {
  pfote: (p) => { const w = 0.25 * Math.sin(2 * Math.PI * 3 * p);
    return { ...SITZEN, s: [1.45 + w, -SITZ, 0.9 - SITZ, 0.9 - SITZ], k: [-0.5, 0, -1.9, -1.9], e: huelle(p) }; },
  strecken: (p) => ({ ...ausgleichen({ s: [1.15, 1.15, -0.45, -0.45], k: [-0.15, -0.15, 0.85, 0.85] }), kp: 0.3, e: huelle(p, 0.3, 0.75) }),
  verbeugen: (p) => ({ ...ausgleichen({ s: [1.0, 1.0, -0.15, -0.15], k: [-2.05, -2.05, 0.35, 0.35] }), kp: 0.45, e: huelle(p, 0.25, 0.75) }),
  liegestuetze: (p) => { const u = welle((p - 0.15) / 0.7, 3) * (p > 0.15 && p < 0.85 ? 1 : 0);
    return { ...ausgleichen({ s: [0.45 + 0.5 * u, 0.45 + 0.5 * u, -0.45, -0.45], k: [-0.85 - 0.95 * u, -0.85 - 0.95 * u, 0.85, 0.85] }),
      e: huelle(p, 0.12, 0.88) }; },
  platz: (p) => ({ s: [1.25, 1.25, -1.25, -1.25], k: [-2.4, -2.4, 2.4, 2.4], n: 0, kd: 0.3 * Math.sin(2 * Math.PI * p), e: huelle(p, 0.2, 0.85) }),
  tot_stellen: (p) => ({ s: [0.25, 0.3, -0.3, -0.25], k: [-0.2, -0.3, 0.3, 0.2], y: MASSE.breite / 2 + 0.008, n: 0, r: 1.45, e: huelle(p, 0.18, 0.86) }),
  boxen: (p) => { const a = Math.sin(2 * Math.PI * 4 * p), b = Math.sin(2 * Math.PI * 4 * p + Math.PI);
    return { ...SITZEN, n: SITZ * 1.25, s: [1.15 + 0.45 * a, 1.15 + 0.45 * b, 0.9 - SITZ, 0.9 - SITZ], k: [-0.7, -0.7, -1.9, -1.9], e: huelle(p) }; },
  umschauen: (p) => ({ s: [0.45, 0.45, -0.45, -0.45], k: [-0.85, -0.85, 0.85, 0.85], n: 0,
    kd: 0.95 * Math.sin(2 * Math.PI * p), e: huelle(p, 0.1, 0.9) }),
  handstand: (p) => ({ s: [1.3, 1.3, 0.2, 0.2], k: [0, 0, -0.6, -0.6], n: -1.3, kp: 1.15, e: huelle(p, 0.3, 0.75) }),
  // Salto: Rumpf dreht einmal ganz herum (n bis 2π) und fliegt dabei hoch; Beine angezogen; wirkt direkt, nicht geglättet
  salto: (p) => { const q = glatt((p - 0.18) / 0.62);
    return { s: [1.1, 1.1, -1.1, -1.1], k: [-1.9, -1.9, 1.9, 1.9], y: STAND_Y + 0.12 * Math.sin(Math.PI * q), n: (2 * Math.PI * q) % (2 * Math.PI),
      e: huelle(p, 0.15, 0.85), direkt: p > 0.15 && p < 0.85 }; },
  // Seit 0.38.64 nach Petois OpenCat-Fähigkeiten (Kürzel dahinter). Weltwinkel eines Beins = s + n.
  maennchen: (p) => ({ ...MAENNCHEN, kp: -0.8, e: huelle(p, 0.25, 0.8) }),                                        // hu
  high_five: (p) => ({ ...SITZEN, s: [1.95, -SITZ, 0.9 - SITZ, 0.9 - SITZ], k: [-0.2, 0, -1.9, -1.9], kp: 0.25, e: huelle(p, 0.25, 0.8) }), // fiv
  jubeln: (p) => { const a = Math.sin(2 * Math.PI * 4 * p);                                                        // chr
    return { ...MAENNCHEN, s: [0.5 + 0.55 * a, 0.5 - 0.55 * a, MAENNCHEN.s[2], MAENNCHEN.s[3]], k: [-0.6, -0.6, -1.9, -1.9], kp: -0.6, e: huelle(p, 0.2, 0.82) }; },
  nicken: (p) => ({ ...STEHEN, kp: 0.35 * Math.sin(2 * Math.PI * 3 * p), e: huelle(p, 0.1, 0.9) }),                // nd
  schnueffeln: (p) => ({ ...ausgleichen({ s: [0.65, 0.65, -0.25, -0.25], k: [-1.3, -1.3, 0.85, 0.85] }),        // snf
    kp: -0.25, kd: 0.5 * Math.sin(2 * Math.PI * 2 * p), e: huelle(p, 0.15, 0.85) }),
  kratzen: (p) => ({ ...SITZEN, s: [-SITZ, -SITZ, 1.55 + 0.25 * Math.sin(2 * Math.PI * 8 * p), 0.9 - SITZ],           // scrh
    k: [0, 0, -1.2, -1.9], kd: 0.35, e: huelle(p, 0.2, 0.82) }),
  graben: (p) => { const a = Math.sin(2 * Math.PI * 5 * p);                                                         // dg
    return { ...ausgleichen({ s: [0.9 + 0.5 * a, 0.9 - 0.5 * a, -0.15, -0.15], k: [-1.6 - 0.4 * a, -1.6 + 0.4 * a, 0.85, 0.85] }), kp: 0.1, e: huelle(p, 0.15, 0.85) }; },
  kicken: (p) => { const u = welle(p, 2);                                                                           // kc
    return { ...STEHEN, s: [0.45, 0.45, -0.45, -0.45 - 1.0 * u], k: [-0.85, -0.85, 0.85, 0.85 - 0.8 * u], n: -0.12 * u, e: huelle(p, 0.1, 0.9) }; },
  springen: (p) => { const c = glatt(p / 0.35) * (1 - glatt((p - 0.35) / 0.08)), j = Math.sin(Math.PI * Math.max(0, Math.min(1, (p - 0.4) / 0.3)));  // jmp
    return { s: [0.45 + 0.5 * c, 0.45 + 0.5 * c, -0.45 - 0.5 * c, -0.45 - 0.5 * c], k: [-0.85 - 0.9 * c, -0.85 - 0.9 * c, 0.85 + 0.9 * c, 0.85 + 0.9 * c],
      hoch: 0.05 * j, n: 0, e: huelle(p, 0.08, 0.9), direkt: p > 0.38 && p < 0.72 }; },
  tisch: (p) => ({ s: [0, 0, 0, 0], k: [0, 0, 0, 0], n: 0, kp: 0, e: huelle(p, 0.2, 0.85) }),  // tbl
  schlafen: (p) => ({ s: [1.25, 1.25, -1.25, -1.25], k: [-2.4, -2.4, 2.4, 2.4], hoch: 0.002 * Math.sin(2 * Math.PI * 3 * p), n: 0,  // zz
    kp: -0.45, kd: 0, e: huelle(p, 0.15, 0.9) }),
  frontsalto: (p) => { const q = glatt((p - 0.18) / 0.62);                                                         // ff
    return { s: [1.1, 1.1, -1.1, -1.1], k: [-1.9, -1.9, 1.9, 1.9], y: STAND_Y + 0.12 * Math.sin(Math.PI * q), n: -((2 * Math.PI * q) % (2 * Math.PI)),
      e: huelle(p, 0.15, 0.85), direkt: p > 0.15 && p < 0.85 }; },
  // Seit 0.38.65: Bewegungen nach Petois Kürzeln. Die Beine laufen im Takt des Tricks, den Weg macht der Simulator.
  rueckwaerts: (p) => ({ ...gangBeine('traben', 2 * Math.PI * 7 * p, -1), e: huelle(p, 0.1, 0.9) }),                // bk
  auf_der_stelle: (p) => ({ ...gangBeine('traben', 2 * Math.PI * 7 * p, 1, 0.15), e: huelle(p, 0.1, 0.9) }),     // vt
  moonwalk: (p) => ({ ...gangBeine('traben', 2 * Math.PI * 6 * p, 1, 0.8), kp: 0.2, e: huelle(p, 0.12, 0.88) }),   // mw
  umarmen: (p) => ({ ...MAENNCHEN, s: [0.95, 0.95, MAENNCHEN.s[2], MAENNCHEN.s[3]], k: [-2.1, -2.1, -1.9, -1.9],    // hg
    kp: -0.5, kd: 0.15 * Math.sin(2 * Math.PI * p), e: huelle(p, 0.25, 0.8) }),
  komm_her: (p) => { const w = Math.sin(2 * Math.PI * 4 * p);                                                      // cmh
    return { ...SITZEN, s: [1.25 + 0.3 * w, -SITZ, 0.9 - SITZ, 0.9 - SITZ], k: [-1.2 - 0.6 * Math.max(0, w), 0, -1.9, -1.9],
      kp: 0.2, e: huelle(p, 0.2, 0.85) }; },
  // Rollen: einmal über die linke Seite um die Längsachse, Beine angezogen; wirkt direkt, nicht geglättet
  rollen: (p) => { const q = glatt((p - 0.2) / 0.6);                                                               // rl
    return { s: [1.25, 1.25, -1.25, -1.25], k: [-2.4, -2.4, 2.4, 2.4], n: 0, r: (2 * Math.PI * q) % (2 * Math.PI),
      y: MASSE.breite / 2 + 0.006 + 0.01 * Math.sin(Math.PI * q), e: huelle(p, 0.18, 0.86), direkt: p > 0.2 && p < 0.8 }; },
};

export class Bittle {
  constructor() {
    this.root = new THREE.Group();
    const rumpf = stoff(F.rumpf, 'shell'), dunkel = stoff(F.dunkel, 'servo'), akzent = stoff(F.akzent, 'plastic');
    this.body = new THREE.Group();
    this.root.add(this.body);
    teil(this.body, rundKasten(MASSE.laenge, MASSE.dicke, MASSE.breite * 0.82, 0.012, 3), rumpf, 0, 0, 0);
    teil(this.body, rundKasten(0.09, 0.006, 0.05, 0.003, 2), akzent, 0, MASSE.dicke / 2 + 0.002, 0);  // Deckel mit Platine
    // Hüftträger zwischen Rumpf und Schultern (die Platte ist 9 cm breit, die Hüften sitzen außen)
    for (const x of [-MASSE.hueftX, MASSE.hueftX]) teil(this.body, rundKasten(0.022, 0.016, MASSE.breite, 0.004, 2), rumpf, x * 0.94, HUEFT_Y, 0);
    // Beine: Schultergelenk (Drehung um Z), darunter Knie
    this.beine = BEINE.map(([x, z, vorn]) => {
      const schulter = new THREE.Group();
      schulter.position.set(x, HUEFT_Y, z);
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
    this.headYaw.position.set(MASSE.laenge / 2 + 0.008, 0.016, 0);
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
    // Gang je Gangart; rückwärts schwingen die Beine andersherum
    const gang = laeuft ? gangBeine(st.gangart || 'traben', st.gait_phase || 0, (t.vx || 0) < -0.01 ? -1 : 1) : null;
    const trick = wach && TRICKS[st.skill] ? TRICKS[st.skill](Math.max(0, Math.min(1, st.skill_progress || 0))) : null;
    this.beine.forEach((b, i) => {
      const seite = b.vorn ? 1 : -1;                     // Knie zeigen zur Mitte: vorn nach hinten, hinten nach vorn
      let s = STAND.s * seite, kn = STAND.k * seite;
      if (gang) { s = gang.s[i]; kn = gang.k[i]; }
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
    // Neigung: sitzend vorn hoch, beim Hoppeln wippend, im Trick aus der Pose
    let neigung = SITZ * this._sitz + (gang ? gang.n : 0), kippen = 0;
    if (trick) {
      neigung += (trick.n - neigung) * trick.e;
      kippen = (trick.r || 0) * (trick.direkt ? 1 : trick.e);
      if (trick.kd !== undefined) this.headYaw.rotation.y = trick.kd * trick.e;
      if (trick.kp !== undefined) this.headPitch.rotation.z = trick.kp * trick.e;   // Kopf heben (nach vorn schauen)
    }
    // Höhe: der tiefste Punkt steht auf dem Boden; Sprünge und Rollen geben sie vor
    let y = bodenHoehe(this._s, this._k, neigung);
    if (trick) {
      if (trick.y !== undefined) y += (trick.y - y) * (trick.direkt ? 1 : trick.e);
      y += (trick.hoch || 0) * trick.e;
    }
    if (!trick || !trick.direkt) {                        // sanft hinein und heraus; beim Salto direkt
      this._y = this._y === undefined ? y : this._y + (y - this._y) * Math.min(1, dt * 10);
      this._n = this._n === undefined ? neigung : this._n + (neigung - this._n) * Math.min(1, dt * 10);
      y = this._y; neigung = this._n;
    } else { this._y = y; this._n = neigung; }
    const fallZiel = st.fallen ? (st.fall_side || 1) * 1.4 : 0;
    this._fall += (fallZiel - this._fall) * Math.min(1, dt * (st.fallen ? 9 : 3));
    if (Math.abs(this._fall) > 0.05) y = Math.max(MASSE.breite / 2, y * Math.cos(this._fall));
    this.body.position.y = y;
    this.body.rotation.set(this._fall + kippen, 0, neigung, 'XYZ');
  }
}
