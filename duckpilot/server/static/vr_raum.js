// Raum aus der Quest (seit 0.50, Knowlin Lab): Die Brille erkennt Boden und Flächen (WebXR „plane-detection“). Daraus
// werden Maße im Rahmen des Simulators – Ursprung ist der Platz, an dem du den Roboter hingestellt hast (`anker`):
// x = rechts, y = −z der Brille. Zurück gehen nur Zahlen (Bodenpunkte, Kästen für Tisch, Sofa …) – keine Bilder.
import * as THREE from './vendor/three.module.min.js';

const m4 = new THREE.Matrix4(), v = new THREE.Vector3();

export function vermessen(frame, raum, anker) {
  const flaechen = frame && frame.detectedPlanes;
  if (!flaechen || !flaechen.size) return null;
  anker.updateMatrixWorld(true);
  const inv = new THREE.Matrix4().copy(anker.matrixWorld).invert();
  const alle = [];
  for (const f of flaechen) {
    const lage = frame.getPose(f.planeSpace, raum);
    if (!lage) continue;
    m4.fromArray(lage.transform.matrix);
    const punkte = f.polygon.map((p) => {
      v.set(p.x, p.y, p.z).applyMatrix4(m4).applyMatrix4(inv);
      return [v.x, -v.z, v.y];
    });
    alle.push({ art: f.semanticLabel || '', waagrecht: f.orientation === 'horizontal', punkte });
  }
  const waagrecht = alle.filter((f) => f.waagrecht);
  if (!waagrecht.length) return null;
  const hoehe = (f) => f.punkte.reduce((s, p) => s + p[2], 0) / f.punkte.length;
  const boden = waagrecht.find((f) => f.art === 'floor') || waagrecht.reduce((a, b) => (hoehe(a) <= hoehe(b) ? a : b));
  const h0 = hoehe(boden);
  const moebel = waagrecht.filter((f) => f !== boden && hoehe(f) - h0 > 0.15).map((f) => {
    const xs = f.punkte.map((p) => p[0]), ys = f.punkte.map((p) => p[1]);
    const r = (n) => Math.round(n * 1000) / 1000;
    return { art: f.art, x: r((Math.max(...xs) + Math.min(...xs)) / 2), y: r((Math.max(...ys) + Math.min(...ys)) / 2),
      breite: r(Math.max(...xs) - Math.min(...xs)), tiefe: r(Math.max(...ys) - Math.min(...ys)), hoehe: r(hoehe(f) - h0) };
  });
  return { boden: boden.punkte.slice(0, 64).map((p) => [Math.round(p[0] * 1000) / 1000, Math.round(p[1] * 1000) / 1000]),
    flaechen: moebel.slice(0, 24) };
}
