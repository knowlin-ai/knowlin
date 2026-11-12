// Porträts der Körper für die Startseite (seit 0.38.51): aus den geladenen 3D-Modellen gerendert, auf diesem Rechner.
// Pollens Porträts dürfen nicht ins Repo (CC BY-NC-SA) – die Modelle lädt Knowlin beim ersten Start, das Bild entsteht
// hier daraus. Gleicher Ausschnitt für alle: Kopf und Oberkörper, schwarzer Grund (der Kreis schneidet zu).
import * as THREE from './vendor/three.module.min.js';
import { ladeArm, RealArm } from './arm3d.js';
import { loadModel, RealDuck } from './duckmodel.js';
import { studio } from './licht3d.js';
import { loadReachy, RealReachy } from './reachymodell.js';

const GRAD = Math.PI / 180;
// Arm in der Haltung „staunen“ (duckpilot/arm.py): aufgerichtet, Greifer offen, Reihenfolge wie arm.GELENKE
const ARM_STAUNEN = [0, -55, -20, -20, 0, 60].map((g) => g * GRAD);

// id der Kachel → Figur bauen; `von`/`bis`: welcher Anteil der Höhe unten/oben wegfällt (Reachys lange Antennen),
// `dreh`: Blickrichtung in Grad um die Hochachse (0 = von vorn)
const KOERPER = {
  duckpilot: { bau: async () => new RealDuck(await loadModel()), von: 0.42, dreh: -12 },
  'reachy-mini': { bau: async () => new RealReachy(await loadReachy()), von: 0.25, bis: 0.3, dreh: 20 },
  'open-duck-mini': { bau: async () => new RealDuck(await loadModel('/static/model/open_duck_mini.dpm')), von: 0.42, dreh: 25 },
  so101: { bau: async () => new RealArm(await ladeArm()), von: 0.25, dreh: 70, gelenke: ARM_STAUNEN },
};

export const RENDERBAR = Object.keys(KOERPER);

// Rendert das Porträt als PNG (Data-URL) oder wirft, wenn das Modell (noch) nicht da ist.
export async function portraet(id, groesse = 256, anders = {}) {
  const k = { ...KOERPER[id], ...anders };
  if (!KOERPER[id]) throw new Error(`kein Porträt für ${id}`);
  const fig = await k.bau();
  const st = { x: 0, y: 0, yaw: 0, stand_z: 0, pose: { z: 0, roll: 0, pitch: 0 }, display_joints: k.gelenke || null };
  for (let i = 0; i < 3; i++) fig.update(st, 1);            // Glättung einschwingen lassen
  const canvas = document.createElement('canvas');
  canvas.width = canvas.height = groesse;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, preserveDrawingBuffer: true });
  try {
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    const scene = new THREE.Scene();
    const { key } = studio(renderer, scene, 0x000000);
    key.castShadow = false;
    scene.add(fig.root);
    fig.root.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(fig.root);
    const groesseV = box.getSize(new THREE.Vector3());
    const unten = box.min.y + groesseV.y * k.von;
    const oben = box.max.y - groesseV.y * (k.bis || 0);
    const mitte = new THREE.Vector3((box.min.x + box.max.x) / 2, (unten + oben) / 2, (box.min.z + box.max.z) / 2);
    const hoehe = oben - unten;
    const breite = Math.max(groesseV.x, groesseV.z);
    const halb = Math.max(hoehe, breite) * 0.58;                 // etwas Rand, der Kreis schneidet die Ecken weg
    const cam = new THREE.PerspectiveCamera(24, 1, 0.01, 50);
    const abstand = halb / Math.tan(12 * GRAD);
    const w = k.dreh * GRAD;                                     // Figuren schauen in +x
    cam.position.set(mitte.x + Math.cos(w) * abstand, mitte.y + abstand * 0.12, mitte.z - Math.sin(w) * abstand);
    cam.lookAt(mitte);
    key.position.copy(cam.position).add(new THREE.Vector3(0.8, 2.2, 0.4));
    renderer.render(scene, cam);
    return canvas.toDataURL('image/png');
  } finally {
    renderer.dispose();
    renderer.forceContextLoss();
  }
}
