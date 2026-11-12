// Möbel zum Wiedererkennen (seit 0.37.6, Hinweis aus dem Test „die 3D-Objekte sind sehr abstrakt – schöner, wenn man
// erkennt, dass es ein Couchtisch ist; keine Millionen Polygone, soll flüssig laufen“): Jedes Möbel wird aus ein paar
// einfachen Körpern gebaut (Kästen, Zylinder, Kegel) – je Stück 5 bis 25 Teile, wenige Hundert Dreiecke.
// Die Abmessungen stammen aus der Welt des Simulators und ändern sich nicht: Zusammenstöße, Tiefensensor und Wege
// rechnen weiter mit dem Kasten bzw. Zylinder.
//
// Erkannt wird am Namen (Sofa, Couch, Regal, Kiste, Tisch, Pflanze, Hocker, Stuhl …) – Unbekanntes bleibt ein Kasten.

import * as THREE from './vendor/three.module.min.js';
import { rundKasten } from './formen3d.js';

const HOLZ = 0x9a7650, HOLZ_DUNKEL = 0x6e5236, METALL = 0x8d8d8d, ERDE = 0x4a3a2c, BLATT = 0x4f8a45, BLATT_HELL = 0x6fae5c;
const BUCH = [0x8e4b4b, 0x4b6a8e, 0xb08d3e, 0x5d7d52, 0x7a5a8a];

const STOFFE = new Map();                            // gleiche Farbe → gleiches Material (weniger Zeichenaufrufe)
function stoff(farbe, rauh = 0.85) {
  const c = new THREE.Color(farbe), key = `${c.getHexString()}|${rauh}`;
  if (!STOFFE.has(key)) STOFFE.set(key, new THREE.MeshStandardMaterial({ color: c, roughness: rauh, metalness: 0 }));
  return STOFFE.get(key);
}

function kasten(g, mat, sx, sy, sz, x, y, z) {
  // leicht gebrochene Kanten (seit 0.38.18): fangen Licht wie echte Möbel; je Möbel später zu wenigen Meshes verschmolzen
  // kleine Teile (Bücher, Leisten) bleiben einfache Kästen – dort sähe man die Kante nicht, kostet aber Dreiecke
  const duenn = Math.min(sx, sy, sz);
  const geo = duenn < 0.03 ? new THREE.BoxGeometry(sx, sy, sz) : rundKasten(sx, sy, sz, Math.min(0.006, 0.25 * duenn), 1);
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z);
  g.add(m);
  return m;
}

function rolle(g, mat, r0, r1, h, x, y, z, seg = 16) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(r0, r1, h, seg), mat);
  m.position.set(x, y, z);
  g.add(m);
  return m;
}

// Lokaler Rahmen: x = Breite in Welt-x, z = Tiefe in Welt-(−y). Rückseite = zur Wand (weg von der Raummitte).
function sofa(b, tone) {
  const g = new THREE.Group();
  const breit = b.sx >= b.sy;                       // die lange Seite ist die Sitzfläche
  const L = breit ? b.sx : b.sy, T = breit ? b.sy : b.sx, H = b.h;
  const bezug = stoff(tone(b.color)), kissen = stoff(new THREE.Color(tone(b.color)).multiplyScalar(1.12));
  const beine = stoff(HOLZ_DUNKEL, 0.6);
  const bein = 0.05, sitz = H * 0.48;
  kasten(g, bezug, L, sitz - bein, T, 0, bein + (sitz - bein) / 2, 0);                    // Unterbau
  const lehne = T * 0.22, arm = Math.min(0.14, L * 0.1);
  kasten(g, bezug, L, H - bein, lehne, 0, bein + (H - bein) / 2, -T / 2 + lehne / 2);     // Rückenlehne
  for (const s of [-1, 1]) kasten(g, bezug, arm, H * 0.75 - bein, T, s * (L / 2 - arm / 2), bein + (H * 0.75 - bein) / 2, 0);
  const n = L > 1.2 ? 3 : 2, frei = L - 2 * arm, w = frei / n;                            // Sitzkissen
  for (let i = 0; i < n; i++) {
    kasten(g, kissen, w - 0.015, 0.07, T - lehne - 0.02, -frei / 2 + w * (i + 0.5), sitz + 0.035, lehne / 2);
    kasten(g, kissen, w - 0.03, H * 0.35, 0.06, -frei / 2 + w * (i + 0.5), sitz + H * 0.2, -T / 2 + lehne + 0.03);
  }
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) rolle(g, beine, 0.018, 0.014, bein, sx * (L / 2 - 0.05), bein / 2, sz * (T / 2 - 0.05), 8);
  return { g };
}

function regal(b, tone) {
  const g = new THREE.Group();
  const breit = b.sx >= b.sy;
  const L = breit ? b.sx : b.sy, T = breit ? b.sy : b.sx, H = b.h;
  const holz = stoff(tone(b.color), 0.7), d = 0.02;
  for (const s of [-1, 1]) kasten(g, holz, d, H, T, s * (L / 2 - d / 2), H / 2, 0);       // Seiten
  kasten(g, holz, L, d, T, 0, H - d / 2, 0);                                               // Deckel
  kasten(g, holz, L, 0.04, T, 0, 0.02, 0);                                                 // Sockel
  kasten(g, stoff(HOLZ_DUNKEL, 0.8), L - 2 * d, H - 0.04, 0.008, 0, H / 2, -T / 2 + 0.004); // Rückwand
  const boeden = 3;
  for (let k = 1; k <= boeden; k++) {
    const y = 0.04 + (H - 0.06) * k / (boeden + 1);
    kasten(g, holz, L - 2 * d, d, T - 0.01, 0, y, 0.005);
  }
  // ein paar Bücher und eine Kiste – feste Anordnung, damit es bei jedem Start gleich aussieht
  const fach = (H - 0.06) / (boeden + 1);
  for (let k = 0; k <= boeden; k++) {
    const y0 = 0.04 + fach * k + (k ? d / 2 : 0);
    let x = -L / 2 + d + 0.02 + (k % 2) * 0.12;
    const reihe = 4 + (k * 3) % 5;
    for (let i = 0; i < reihe && x < L / 2 - 0.08; i++) {
      const bw = 0.025 + ((i * 7 + k * 3) % 4) * 0.008, bh = fach * (0.55 + ((i + k) % 3) * 0.12);
      kasten(g, stoff(BUCH[(i + k * 2) % BUCH.length], 0.75), bw, bh, T * 0.7, x + bw / 2, y0 + bh / 2, 0.01);
      x += bw + 0.004;
    }
  }
  return { g };
}

function kiste(b, tone) {
  const g = new THREE.Group();
  const holz = stoff(tone(b.color), 0.8), dunkel = stoff(new THREE.Color(tone(b.color)).multiplyScalar(0.72), 0.85);
  const H = b.h;
  kasten(g, holz, b.sx - 0.02, H - 0.02, b.sy - 0.02, 0, (H - 0.02) / 2, 0);              // Kasten
  const latten = 3;
  for (let k = 0; k < latten; k++) {                                                        // Latten rundum
    const y = H * (k + 0.5) / latten;
    kasten(g, holz, b.sx, H / latten - 0.02, 0.012, 0, y, b.sy / 2 - 0.006);
    kasten(g, holz, b.sx, H / latten - 0.02, 0.012, 0, y, -b.sy / 2 + 0.006);
    kasten(g, holz, 0.012, H / latten - 0.02, b.sy, b.sx / 2 - 0.006, y, 0);
    kasten(g, holz, 0.012, H / latten - 0.02, b.sy, -b.sx / 2 + 0.006, y, 0);
  }
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) kasten(g, dunkel, 0.03, H, 0.03, sx * (b.sx / 2 - 0.012), H / 2, sz * (b.sy / 2 - 0.012));
  return { g, dreh: 0 };
}

function tisch(b, tone) {
  const g = new THREE.Group();
  const holz = stoff(tone(b.color), 0.55), dunkel = stoff(new THREE.Color(tone(b.color)).multiplyScalar(0.7), 0.6);
  const H = b.h, platte = 0.035, bein = 0.022, rand = 0.035;
  kasten(g, holz, b.sx, platte, b.sy, 0, H - platte / 2, 0);                              // Platte
  kasten(g, dunkel, b.sx - 2 * rand + bein, 0.04, b.sy - 2 * rand + bein, 0, H - platte - 0.02, 0); // Zarge
  kasten(g, holz, b.sx - 2 * rand, 0.015, b.sy - 2 * rand, 0, H * 0.22, 0);                // Ablage unten
  // ein Buch und eine Tasse auf der Ablage bzw. Platte – kleine Hinweise, dass es ein Tisch ist
  kasten(g, stoff(BUCH[1], 0.7), b.sx * 0.4, 0.025, b.sy * 0.3, -b.sx * 0.12, H * 0.22 + 0.02, 0.01);
  // Tasse in die Ecke statt nahe der Mitte – dort stand sie in Reachys Sockel (12.11.); auf kleinen Tischen keine
  if (b.sx >= 0.45 && b.sy >= 0.45) rolle(g, stoff(0xe9e2cf, 0.4), 0.022, 0.018, 0.045, b.sx / 2 - 0.06, H + 0.0225, -(b.sy / 2 - 0.06), 12);
  for (const sx of [-1, 1]) for (const sz of [-1, 1]) {
    rolle(g, dunkel, bein / 2, bein / 2.6, H - platte, sx * (b.sx / 2 - rand), (H - platte) / 2, sz * (b.sy / 2 - rand), 8);
  }
  return { g, dreh: 0 };
}

function pflanze(c, tone) {
  const g = new THREE.Group();
  const topf = stoff(new THREE.Color(0xb86b4b).lerp(new THREE.Color(tone(c.color)), 0.25), 0.7);
  const hTopf = Math.min(0.24, c.h * 0.38);
  rolle(g, topf, c.r * 0.82, c.r * 0.62, hTopf, 0, hTopf / 2, 0, 20);
  rolle(g, topf, c.r * 0.88, c.r * 0.88, 0.025, 0, hTopf - 0.012, 0, 20);                // Rand
  rolle(g, stoff(ERDE, 0.95), c.r * 0.78, c.r * 0.78, 0.01, 0, hTopf - 0.003, 0, 16);
  rolle(g, stoff(0x5c7a3a, 0.8), 0.01, 0.012, c.h * 0.35, 0, hTopf + c.h * 0.17, 0, 6);   // Stamm
  const blatt = [stoff(BLATT, 0.75), stoff(BLATT_HELL, 0.75)];
  const n = 13;
  for (let i = 0; i < n; i++) {                                                            // Blätter: flache Kegel, rundum
    const a = i / n * Math.PI * 2, hoch = hTopf + (c.h - hTopf) * (0.35 + 0.6 * ((i * 5) % n) / n);
    const m = new THREE.Mesh(new THREE.ConeGeometry(0.035, c.r * 1.25, 5), blatt[i % 2]);
    m.scale.set(1, 1, 0.35);
    m.position.set(Math.cos(a) * c.r * 0.45, hoch, Math.sin(a) * c.r * 0.45);
    m.rotation.set(0, -a, -Math.PI / 2 + 0.55);
    m.rotation.order = 'YXZ';
    g.add(m);
  }
  const krone = new THREE.Mesh(new THREE.ConeGeometry(0.03, c.r * 0.9, 5), blatt[1]);   // Spitze oben
  krone.position.y = c.h - c.r * 0.45;
  g.add(krone);
  return { g, dreh: 0 };
}

function hocker(c, tone) {
  const g = new THREE.Group();
  const sitz = stoff(new THREE.Color(HOLZ).lerp(new THREE.Color(tone(c.color)), 0.3), 0.6), metall = new THREE.MeshStandardMaterial({ color: METALL, roughness: 0.35, metalness: 0.7 });
  rolle(g, sitz, c.r, c.r * 0.95, 0.045, 0, c.h - 0.0225, 0, 24);
  for (let i = 0; i < 4; i++) {
    const a = i / 4 * Math.PI * 2 + Math.PI / 4;
    const m = rolle(g, metall, 0.009, 0.009, c.h - 0.04, Math.cos(a) * c.r * 0.6, (c.h - 0.04) / 2, Math.sin(a) * c.r * 0.6, 6);
    m.rotation.set(Math.sin(a) * 0.12, 0, -Math.cos(a) * 0.12);
  }
  const ring = new THREE.Mesh(new THREE.TorusGeometry(c.r * 0.62, 0.006, 6, 24), metall);
  ring.rotation.x = Math.PI / 2;
  ring.position.y = c.h * 0.35;
  g.add(ring);
  return { g, dreh: 0 };
}

const BAU = [
  [/sofa|couch(?!tisch)|sessel/i, sofa],
  [/regal|schrank|shelf|bücher/i, regal],
  [/kiste|box|truhe|crate/i, kiste],
  [/tisch|table|bank/i, tisch],
  [/pflanze|plant|blume|baum/i, pflanze],
  [/hocker|stuhl|stool|chair/i, hocker],
];

// Möbel als Gruppe an seiner Stelle. b: Kasten {name, x, y, sx, sy, h, color} oder Zylinder {name, x, y, r, h, color}.
// → Gruppe oder null (unbekannt: der Aufrufer zeichnet weiter den einfachen Kasten)
export function baueMoebel(b, tone) {
  const bau = BAU.find(([muster]) => muster.test(b.name || ''));
  if (!bau) return null;
  const istZylinder = b.sx === undefined;
  const rund = bau[1] === pflanze || bau[1] === hocker;
  if (istZylinder !== rund) return null;                 // Form passt nicht zum Namen → einfacher Körper
  const { g } = bau[1](b, tone);
  if (bau[1] === sofa || bau[1] === regal) {
    // Lokal liegt die Rückseite bei −z (Welt +y). Zur Wand drehen: weg von der Raummitte entlang der kurzen Seite.
    g.rotation.y = b.sx >= b.sy ? (b.y >= 0 ? 0 : Math.PI) : (b.x >= 0 ? -Math.PI / 2 : Math.PI / 2);
  }
  g.position.set(b.x, 0, -b.y);
  return zusammenfassen(g);
}

// Teile mit gleichem Material zu einem Körper verschmelzen: aus 15–25 Teilen werden 2–6 Zeichenaufrufe (flüssig auch
// am Handy und mit Schatten). Anwählen und Kamera treffen die verschmolzenen Körper genauso.
function zusammenfassen(g) {
  const jeMaterial = new Map();
  for (const m of g.children) {
    if (!m.isMesh) continue;
    m.updateMatrix();
    const geo = m.geometry.index ? m.geometry.toNonIndexed() : m.geometry.clone();
    geo.applyMatrix4(m.matrix);
    if (!jeMaterial.has(m.material)) jeMaterial.set(m.material, []);
    jeMaterial.get(m.material).push(geo);
    m.geometry.dispose();
  }
  const neu = new THREE.Group();
  neu.position.copy(g.position);
  neu.rotation.copy(g.rotation);
  for (const [mat, teile] of jeMaterial) {
    const n = teile.reduce((s, t) => s + t.attributes.position.count, 0);
    const pos = new Float32Array(n * 3), nor = new Float32Array(n * 3);
    let k = 0;
    for (const t of teile) {
      pos.set(t.attributes.position.array, k * 3);
      nor.set(t.attributes.normal.array, k * 3);
      k += t.attributes.position.count;
      t.dispose();
    }
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    geo.setAttribute('normal', new THREE.BufferAttribute(nor, 3));
    geo.computeBoundingSphere();
    const m = new THREE.Mesh(geo, mat);
    m.castShadow = m.receiveShadow = true;
    neu.add(m);
  }
  return neu;
}
