// Bausteine für die einfachen Verkörperungen (eigene Entwürfe, keine CAD-Daten): abgerundete Kästen, Materialien
// wie beim Originalmodell und Zusammenfassen gleicher Materialien je Gelenk – wenige Zeichenaufrufe, weiche Formen.
import * as THREE from './vendor/three.module.min.js';
import { mergeGeometries, mergeVertices } from './vendor/BufferGeometryUtils.js';

// Oberflächen (Originalmodelle: Art je Teil aus dem Bake-Skript, Farbe aus dem CAD; einfache Modelle: von Hand)
export const FINISH = {
  shell: { roughness: 0.42, clearcoat: 0.35, clearcoatRoughness: 0.35 },          // lackierte Schale
  plastic: { roughness: 0.55 },                                                    // gedruckte Teile
  servo: { roughness: 0.48, clearcoat: 0.15, clearcoatRoughness: 0.5 },            // XL330
  dark: { roughness: 0.6 },
  rubber: { roughness: 0.85, sheen: 0.4, sheenRoughness: 0.8 },                    // Sohle (TPU)
  soft: { roughness: 0.8, sheen: 0.5, sheenRoughness: 0.7 },                       // weicher Schnabel
  metal: { roughness: 0.32, metalness: 0.9 },
  glass: { roughness: 0.06, metalness: 0.1, clearcoat: 1, clearcoatRoughness: 0.03 },
};

// Farben der Microduck wie bei Pollen (seit 0.38.19); null = Farbe des Modells lassen (Cream)
export const FARBEN = { cream: null, graphite: 0x4a4d53, lavender: 0xc6b3e6, sky: 0xa6cbe9 };

// Abgerundeter Kasten: flache Seiten aus einem Viereck, Kanten mit k Schritten gerundet.
// verjuengen(x, y, z) → [sy, sz] verformt danach (z. B. Kopf vorn flacher); Normalen werden neu berechnet.
export function rundKasten(w, h, d, r, k = 4, verjuengen = null) {
  const halb = [w / 2, h / 2, d / 2];
  const rr = Math.min(r, ...halb.map((v) => v * 0.999));
  const n = 2 * k + 1;
  const g = new THREE.BoxGeometry(1, 1, 1, n, n, n);
  const pos = g.attributes.position;
  const v = new THREE.Vector3(), innen = new THREE.Vector3(), dir = new THREE.Vector3();
  const lage = (u, h2) => {                     // Gitterindex → Lage: k Schritte je Rundung, eine flache Mitte
    const j = Math.round((u + 0.5) * n);
    return j <= k ? -h2 + rr * (j / k) : h2 - rr * ((n - j) / k);
  };
  for (let i = 0; i < pos.count; i++) {
    v.fromBufferAttribute(pos, i);
    v.set(lage(v.x, halb[0]), lage(v.y, halb[1]), lage(v.z, halb[2]));
    innen.set(THREE.MathUtils.clamp(v.x, -halb[0] + rr, halb[0] - rr), THREE.MathUtils.clamp(v.y, -halb[1] + rr, halb[1] - rr),
      THREE.MathUtils.clamp(v.z, -halb[2] + rr, halb[2] - rr));
    dir.subVectors(v, innen);
    if (dir.lengthSq() > 1e-12) v.copy(innen).addScaledVector(dir.normalize(), rr);
    if (verjuengen) { const [sy, sz] = verjuengen(v.x / halb[0], v.y / halb[1], v.z / halb[2]); v.y *= sy; v.z *= sz; }
    pos.setXYZ(i, v.x, v.y, v.z);
  }
  g.deleteAttribute('normal');
  g.deleteAttribute('uv');
  const glatt = mergeVertices(g, 1e-6);
  g.dispose();
  glatt.computeVertexNormals();
  return glatt;
}

const MATS = new Map();
// Material nach Farbe und Oberfläche (FINISH wie beim Originalmodell); gleiche Angaben → dasselbe Material
export function stoff(farbe, art = 'plastic') {
  const key = `${farbe}|${art}`;
  if (!MATS.has(key)) {
    MATS.set(key, new THREE.MeshPhysicalMaterial({ color: new THREE.Color(farbe), ...(FINISH[art] || FINISH.plastic) }));
  }
  return MATS.get(key);
}

// Teil anlegen: Geometrie, Material, Lage (und Drehung) in der Gruppe
export function teil(gruppe, geo, mat, x = 0, y = 0, z = 0, rx = 0, ry = 0, rz = 0) {
  const m = new THREE.Mesh(geo, mat);
  m.position.set(x, y, z);
  m.rotation.set(rx, ry, rz);
  m.castShadow = true;
  m.receiveShadow = true;
  gruppe.add(m);
  return m;
}

// Alle Teile direkt in dieser Gruppe mit gleichem Material zu einem Mesh zusammenfassen (Untergruppen = Gelenke
// bleiben beweglich). Spart Zeichenaufrufe – auch im Schattenbild, das jedes Teil noch einmal zeichnet.
export function verschmelzen(gruppe) {
  const nachMat = new Map();
  for (const c of [...gruppe.children]) {
    if (!c.isMesh || c.userData.einzeln) continue;
    c.updateMatrix();
    let g = c.geometry.clone();
    g.applyMatrix4(c.matrix);
    for (const name of Object.keys(g.attributes)) if (name !== 'position' && name !== 'normal') g.deleteAttribute(name);
    if (!g.index) g = mergeVertices(g, 1e-7);
    if (!nachMat.has(c.material)) nachMat.set(c.material, []);
    nachMat.get(c.material).push(g);
    gruppe.remove(c);
  }
  for (const [mat, geos] of nachMat) {
    const ein = mergeGeometries(geos);
    geos.forEach((g) => g.dispose());
    const m = new THREE.Mesh(ein, mat);
    m.castShadow = true;
    m.receiveShadow = true;
    gruppe.add(m);
  }
}

// Ganzen Baum zusammenfassen (jede Gruppe für sich)
export function allesVerschmelzen(wurzel) {
  const gruppen = [];
  wurzel.traverse((o) => { if (!o.isMesh) gruppen.push(o); });
  gruppen.forEach(verschmelzen);
}
