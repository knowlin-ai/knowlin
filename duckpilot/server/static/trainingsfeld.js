// Trainingsfeld (seit 0.38.19): viele Enten üben gleichzeitig auf unterschiedlichem Boden – so wie das echte Training
// Tausende Physik-Welten parallel rechnet (Pollens mjlab auf einer Grafikkarte, bei uns Kaggle oder der PC).
// Seit 0.38.24 wie im NVIDIA-Beitrag zur Microduck (Isaac Lab): Jede Ente hat ihr eigenes Übungsfeld – Matte, Rampe,
// Stufen, Rampe aufs Podest oder Wellen – im Raster auf einem hellen Hallenboden, Reihe für Reihe gegenläufig. Die Kamera
// beginnt nah an einer Ente, zieht auf und gleitet dann langsam über die Halle.
//
// Seit 0.38.24 (Funde „die 3D-Modelle sehen fehlerhaft aus“ und „die Bewegung ist völlig unsinnig“):
// - Bild-Enten statt vereinfachter Netze: Die Figur – das volle Originalmodell, wenn es in der 3D-Ansicht gewählt ist,
//   sonst die einfache Ente – wird einmal in allen Gangphasen und aus 16 Blickrichtungen in einen Bildbogen gezeichnet.
//   Im Feld steht dann jede Ente als ausgerichtetes Bild – volle Auflösung ohne Löcher und für die Grafikkarte so leicht
//   wie 144 Rechtecke.
// - Echte Gangart: Gelenkwinkel wie im Simulator (`sim.display_joints`), Schrittfrequenz und Tempo passen zueinander
//   (≈ 0,15 m/s, 3,2 Schritte je Sekunde), die Enten schauen in Laufrichtung (vorher liefen die Originale seitwärts).
// - Stürze wie im Reinforcement Learning: Eine Ente stolpert, kippt zur Seite, bleibt kurz liegen und wird dann – wie
//   eine Trainingswelt nach dem Sturz – an den Anfang ihres Felds zurückgesetzt (sie blendet aus und dort wieder ein).
//   Wer das Ende des Felds erreicht, beginnt ebenfalls einen neuen Durchgang. Die Sturzgefahr ist so gewählt, dass genau der Anteil
//   „ohne Sturz“ ankommt, den die Zeile darunter nennt.
// Ehrlich: Hier lernt nichts, es rechnet keine Physik. Ohne Lauf zeigt das Feld eine Lernkurve im Zeitraffer; mit einem
// Lauf spielen die Enten dessen gemessene Quote nach (training.js sagt das unter dem Feld).
import * as THREE from './vendor/three.module.min.js';
import { mergeGeometries } from './vendor/BufferGeometryUtils.js';
import { studio } from './licht3d.js';
import { loadModel, MODEL_URL, RealDuck } from './duckmodel.js';
import { Duck } from './ente3d.js';

const SCHMAL = typeof matchMedia === 'function' && matchMedia('(max-width: 671.98px)').matches;
const SPALTEN = SCHMAL ? 8 : 16, REIHEN = SCHMAL ? 5 : 9;
export const ANZAHL = SPALTEN * REIHEN;
// Jede Ente lernt auf ihrem eigenen Übungsfeld (Hinweis mit dem Bild aus dem NVIDIA-Beitrag: „jede Ente beim
// Lernen soll ja auf ihrem Testfeld lernen“): Holzplatten mit Rampe, Stufen, Podest oder Wellen und eine Matte, mit Abstand
// auf einem hellen Hallenboden, im Raster und Reihe für Reihe gegenläufig – wie die Welten in Isaac Lab
const AX = 1.12, AZ = 0.78, PL = 0.82, PB = 0.46;      // Mitte zu Mitte (quer, tief); Feld lang (Laufrichtung) × breit
const GRUND = 0xdfe3e7;                 // Halle, Dunst und Horizont
const HALLE = 0xd3d8dd, LINIE = 0xb4bac1;

// Bildbogen: Gangphasen × Blickrichtungen, dazu zwei Sturzbilder (kippt, liegt)
export const GANG = 8, BLICKE = 16, STURZ = 2;
const ZEILEN = GANG + STURZ, PX = SCHMAL ? 112 : 128;
const TEMPO = 0.15;                     // m/s – wie „lauf vor“ im Simulator
const FREQ = 2 + 2 * Math.min(1, TEMPO / 0.25);   // Schritte je Sekunde wie im Simulator (sim.py)
const RAND = 0.06;                      // so weit vor dem Ende eines Felds ist ein Durchgang geschafft
const DURCHGANG = (PL - 2 * RAND) / TEMPO;          // Sekunden für einen Durchgang über das Feld

// Übungsfelder: Höhe in Metern an der Stelle u (0…1 entlang der Laufrichtung), Farbe, wie schwer (Sturzgefahr relativ)
const klemm = (u) => Math.min(Math.max(u, 0), 0.999);
const BODEN = [
  { f: () => 0.008, farbe: 0x3d4147, schwer: 0.55 },                                       // Matte
  { f: (u) => 0.012 + klemm(u) * 0.12, farbe: 0xcaa47c, schwer: 1.0 },                     // Rampe
  { f: (u) => 0.012 + Math.floor(klemm(u) * 5) * 0.024, farbe: 0xc19a71, schwer: 1.45 },   // Stufen
  { f: (u) => 0.012 + (klemm(u) < 0.45 ? (klemm(u) / 0.45) * 0.1 : 0.1), farbe: 0xd4b088, schwer: 1.2 },   // Rampe aufs Podest
  { f: (u) => 0.012 + (Math.sin(klemm(u) * Math.PI * 6) * 0.5 + 0.5) * 0.022, farbe: 0xba9269, schwer: 1.15 },   // Wellen
];
const zahl = (i, k) => { const x = Math.sin(i * 127.1 + k * 311.7) * 43758.5453; return x - Math.floor(x); };
const art = (i) => (i * 7 + Math.floor(i / SPALTEN) * 3) % BODEN.length;
// Klares Raster wie in der Keynote (Hinweis 7.11.: „noch etwas kreuz und quer … in einem klaren Raster bzw. mit
// festen Winkeln zueinander“): alle Felder parallel, Reihe für Reihe abwechselnd hin und zurück
const platz = (i) => ({ x: ((i % SPALTEN) - (SPALTEN - 1) / 2) * AX, z: (Math.floor(i / SPALTEN) - (REIHEN - 1) / 2) * AZ,
  dreh: Math.floor(i / SPALTEN) % 2 ? Math.PI : 0 });

// Gelenkwinkel wie sim.display_joints (Reihenfolge der Microduck: links 5, Hals, Kopf ×3, Schnabel, rechts 5)
const STAND_LEG = [0, -0.0873, -0.4579, -0.0049, 0.4530], SIT_LEG = [0, 0, -0.5236, 1.0472, 0];
export function gelenke(phase, schritt = TEMPO / 0.25, fold = 0) {
  const base = STAND_LEG.map((a, k) => a + (SIT_LEG[k] - a) * fold);
  const moving = fold > 0.2 ? 0 : 1, lift = moving * Math.min(1, Math.abs(schritt));
  const beine = [[1, phase], [-1, phase + Math.PI]].map(([, ph]) => {
    const swing = Math.sin(ph), up = Math.max(0, Math.sin(ph)) * lift;
    return [base[0], base[1] + 0.05 * Math.cos(ph) * lift, base[2] + 0.22 * schritt * swing * moving,
      base[3] + 0.7 * up, base[4] + 0.3 * up - 0.18 * schritt * swing * moving];
  });
  return [...beine[0], 0.3491, 0.3491, 0, 0, 0, ...beine[1].map((v) => -v)];
}

// Zustand für eine Zeile des Bildbogens (wie ihn der Server für die 3D-Ansicht schickt)
function pose(zeile) {
  if (zeile < GANG) {
    const ph = (zeile / GANG) * Math.PI * 2;
    return { x: 0, y: 0, yaw: 0, display_joints: gelenke(ph), fallen: false,
      pose: { z: 0, roll: 0.05 * Math.sin(ph), pitch: 0.025 * Math.sin(2 * ph + 0.5) } };
  }
  const liegt = zeile === GANG + 1;
  return { x: 0, y: 0, yaw: 0, display_joints: gelenke(0, 0, liegt ? 0.35 : 0.15), fallen: true, fall_side: liegt ? 1 : 0.45,
    pose: { z: 0, roll: 0, pitch: liegt ? 0 : 0.12 } };
}

// Den Bildbogen zeichnen: eigenes kleines WebGL, damit Licht und Farben wie in der 3D-Ansicht stimmen
async function bildbogen(figur, warten) {
  const W = BLICKE * PX, H = ZEILEN * PX;
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const r = new THREE.WebGLRenderer({ canvas: c, alpha: true, antialias: true, preserveDrawingBuffer: true });
  r.setPixelRatio(1);
  r.setSize(W, H, false);
  const scene = new THREE.Scene();
  studio(r, scene, 0);
  scene.background = null;
  r.shadowMap.enabled = false;
  r.setClearColor(0x000000, 0);
  scene.add(figur.root);
  figur.update(pose(0), 1);
  figur.root.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(figur.root);
  const S = Math.max(box.max.y, box.max.x - box.min.x, box.max.z - box.min.z) * 1.3;
  const mitte = S * 0.44;
  const cam = new THREE.OrthographicCamera(-S / 2, S / 2, S / 2, -S / 2, 0.01, 10);
  const hoch = Math.sin(0.21);                              // Blick leicht von oben (≈ 12°), wie die Feldkamera
  r.setScissorTest(true);
  let takt = performance.now();
  for (let zeile = 0; zeile < ZEILEN; zeile++) {
    figur.root.position.y = 0;
    figur.update(pose(zeile), 1);
    figur.root.updateMatrixWorld(true);
    figur.root.position.y = -Math.min(0, new THREE.Box3().setFromObject(figur.root).min.y);   // nie im Boden
    figur.root.updateMatrixWorld(true);
    for (let k = 0; k < BLICKE; k++) {
      const b = (k / BLICKE) * Math.PI * 2;                 // Blickrichtung im Rahmen der Ente (vorn = +x)
      cam.position.set(Math.cos(b) * 2, mitte + hoch * 2, -Math.sin(b) * 2);
      cam.lookAt(0, mitte, 0);
      const y = H - (zeile + 1) * PX;                        // WebGL zählt von unten
      r.setViewport(k * PX, y, PX, PX);
      r.setScissor(k * PX, y, PX, PX);
      r.clear();
      r.render(scene, cam);
      if (performance.now() - takt > 12) { await warten(); takt = performance.now(); }   // Luft holen, Seite bleibt bedienbar
    }
  }
  // Ins 2D-Bild kopieren, dann das kleine WebGL wieder freigeben
  const bogen = document.createElement('canvas');
  bogen.width = W; bogen.height = H;
  bogen.getContext('2d').drawImage(c, 0, 0);
  scene.remove(figur.root);
  r.dispose();
  r.forceContextLoss();
  return { bogen, S, mitte, hoehe: box.max.y - box.min.y };
}

// Fertige Bildbögen bleiben im Browser dieses PCs (Cache Storage), damit das Feld beim nächsten Mal sofort steht.
// Schlüssel: Körper, Farbe, Bogen-Stand und Größe des Modells – ein neues Modell gibt einen neuen Bogen.
const BOGEN_STAND = 1;
async function ausDemSpeicher(schluessel) {
  try {
    const c = await caches.open('knowlin-feld');
    const res = await c.match(`/feldbogen/${encodeURIComponent(schluessel)}`);
    if (!res) return null;
    const { S, mitte, hoehe } = JSON.parse(res.headers.get('x-feld') || '{}');
    const bild = await createImageBitmap(await res.blob());
    const bogen = document.createElement('canvas');
    bogen.width = bild.width; bogen.height = bild.height;
    bogen.getContext('2d').drawImage(bild, 0, 0);
    return S && mitte ? { bogen, S, mitte, hoehe } : null;
  } catch { return null; }
}
async function inDenSpeicher(schluessel, { bogen, S, mitte, hoehe }) {
  try {
    const blob = await new Promise((ok) => bogen.toBlob(ok, 'image/png'));
    const c = await caches.open('knowlin-feld');
    await c.put(`/feldbogen/${encodeURIComponent(schluessel)}`,
      new Response(blob, { headers: { 'content-type': 'image/png', 'x-feld': JSON.stringify({ S, mitte, hoehe }) } }));
  } catch { /* ohne Speicher: nächstes Mal neu zeichnen */ }
}

function gefaerbt(geo, farbe, x = 0, y = 0, z = 0) {
  geo.translate(x, y, z);
  const col = new THREE.Color(farbe), n = geo.attributes.position.count, a = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) a.set([col.r, col.g, col.b], i * 3);
  geo.setAttribute('color', new THREE.BufferAttribute(a, 3));
  if (!geo.index) geo.setIndex([...Array(n).keys()]);
  for (const k of Object.keys(geo.attributes)) if (!['position', 'normal', 'color'].includes(k)) geo.deleteAttribute(k);
  return geo;
}

// Ein Übungsfeld als Platte: Oberfläche mit Höhenprofil, Seiten bis zum Hallenboden (lokal: Laufrichtung = +x)
function feldPlatte(f, n = 96) {
  const pos = [];
  const quad = (a, b, c, d) => pos.push(...a, ...b, ...c, ...a, ...c, ...d);
  for (let k = 0; k < n; k++) {
    const u0 = k / n, u1 = (k + 1) / n, x0 = -PL / 2 + u0 * PL, x1 = -PL / 2 + u1 * PL, y0 = f(u0), y1 = f(u1 - 1e-6);
    quad([x0, y0, PB / 2], [x1, y1, PB / 2], [x1, y1, -PB / 2], [x0, y0, -PB / 2]);       // oben
    quad([x0, 0, PB / 2], [x1, 0, PB / 2], [x1, y1, PB / 2], [x0, y0, PB / 2]);            // Seite vorn
    quad([x1, 0, -PB / 2], [x0, 0, -PB / 2], [x0, y0, -PB / 2], [x1, y1, -PB / 2]);        // Seite hinten
    const yn = f(u1 + 1e-6);                                                                   // Stufenkante
    if (k < n - 1 && Math.abs(yn - y1) > 1e-4) quad([x1, y1, PB / 2], [x1, yn, PB / 2], [x1, yn, -PB / 2], [x1, y1, -PB / 2]);
  }
  const yA = f(0), yE = f(0.999);
  quad([-PL / 2, 0, -PB / 2], [-PL / 2, 0, PB / 2], [-PL / 2, yA, PB / 2], [-PL / 2, yA, -PB / 2]);       // Anfang
  quad([PL / 2, 0, PB / 2], [PL / 2, 0, -PB / 2], [PL / 2, yE, -PB / 2], [PL / 2, yE, PB / 2]);           // Ende
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.computeVertexNormals();
  return g;
}

function boden() {
  const teile = [], ende = [];
  const m = new THREE.Matrix4();
  let summe = 0;
  // in derselben Reihenfolge wie die Enten (vorn und mittig zuerst), damit sparen() mit den Enten auch ihre Felder weglässt
  const reihe = [...Array(ANZAHL).keys()].map(platz).map((p, i) => ({ ...p, i }))
    .sort((a, b) => b.z - a.z || Math.abs(a.x) - Math.abs(b.x)).map((p) => p.i);
  for (const i of reihe) {
    const { x, z, dreh } = platz(i), b = BODEN[art(i)];
    const g = feldPlatte(b.f).applyMatrix4(m.makeRotationY(dreh)).applyMatrix4(new THREE.Matrix4().makeTranslation(x, 0, z));
    const ton = new THREE.Color(b.farbe).offsetHSL(0, 0, (zahl(i, 3) - 0.5) * 0.04).getHex();
    teile.push(gefaerbt(g, ton));
    summe += g.index.count; ende.push(summe);              // bis wohin die Felder 0…i reichen (für sparen())
  }
  const felder = new THREE.Mesh(mergeGeometries(teile), new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.8, metalness: 0, envMapIntensity: 0.5 }));
  felder.userData.ende = ende;
  // heller Hallenboden mit feinem Raster bis zum Horizont
  const halle = new THREE.Mesh(new THREE.PlaneGeometry(90, 90).rotateX(-Math.PI / 2),
    new THREE.MeshStandardMaterial({ color: HALLE, roughness: 0.9, envMapIntensity: 0.5 }));
  halle.position.y = -0.001;
  const raster = new THREE.GridHelper(60, 120, LINIE, LINIE);
  raster.material.transparent = true; raster.material.opacity = 0.55; raster.material.fog = true;
  const gruppe = new THREE.Group();
  gruppe.add(halle, raster, felder);
  gruppe.userData.felder = felder;
  return gruppe;
}

// Bild-Enten: ein Rechteck je Ente, das zur Kamera schaut; je Ente wählt `zelle` (u, v, sichtbar) das Bild aus dem Bogen.
// Sichtbar < 1 löst die Ente gerastert auf (zurück an den Start) – ohne Sortieren und Transparenz.
function bildEnten(bogen, S, mitte, hoehe) {
  const tex = new THREE.CanvasTexture(bogen);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.minFilter = THREE.LinearMipmapLinearFilter;
  tex.generateMipmaps = true;
  const geo = new THREE.PlaneGeometry(S, S).translate(0, mitte, 0);
  const zelle = new THREE.InstancedBufferAttribute(new Float32Array(ANZAHL * 3), 3);
  zelle.setUsage(THREE.DynamicDrawUsage);
  geo.setAttribute('zelle', zelle);
  const mat = new THREE.MeshBasicMaterial({ map: tex, alphaTest: 0.4, toneMapped: false, fog: true, side: THREE.DoubleSide });
  mat.alphaToCoverage = true;
  mat.onBeforeCompile = (sh) => {
    sh.vertexShader = sh.vertexShader
      .replace('#include <common>', '#include <common>\nattribute vec3 zelle;\nvarying float vSicht;')
      .replace('#include <uv_vertex>', `#include <uv_vertex>\nvMapUv = vMapUv * vec2(${1 / BLICKE}, ${1 / ZEILEN}) + zelle.xy;\nvSicht = zelle.z;`);
    sh.fragmentShader = sh.fragmentShader
      .replace('#include <common>', '#include <common>\nvarying float vSicht;')
      .replace('#include <alphatest_fragment>', `if (vSicht < 0.999) {
        vec2 p = mod(floor(gl_FragCoord.xy), 4.0);                     // Bayer 4 × 4: ruhiges Raster statt Rauschen
        float b = mod(p.x * 2.0 + p.y * 3.0, 4.0) * 4.0 + mod(p.x + p.y * 2.0, 4.0);
        if ((b + 0.5) / 16.0 > vSicht) discard;
      }
      #include <alphatest_fragment>`);
  };
  const netz = new THREE.InstancedMesh(geo, mat, ANZAHL);
  netz.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  netz.frustumCulled = false;
  // Große Figuren (Open Duck, 42 cm) etwas kleiner, damit sie auf die Übungsfelder passen
  return { netz, zelle, S, f: Math.min(1, 0.28 / (hoehe || 0.28)) };
}

export function trainingsfeld(canvas) {
  const ruhig = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  const scene = new THREE.Scene();
  const { key } = studio(renderer, scene, GRUND);
  renderer.shadowMap.enabled = false;                      // Bild-Enten werfen keine Schattenkarte – Kontaktschatten
  key.castShadow = false;
  key.position.set(3, 6, 4);
  key.intensity = 1.5;
  scene.environmentIntensity = 0.55;
  scene.fog = new THREE.Fog(GRUND, 8, 22);
  const kamera = new THREE.PerspectiveCamera(30, 2, 0.1, 60);
  const halle = boden();
  scene.add(halle);

  // Kontaktschatten: weicher, dunkler Fleck unter jeder Ente (hält sie am Boden)
  const fleck = (() => {
    const c = document.createElement('canvas'); c.width = c.height = 64;
    const g = c.getContext('2d'), v = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    v.addColorStop(0, 'rgba(0,0,0,0.6)'); v.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = v; g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
  })();
  const schatten = new THREE.InstancedMesh(new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({ map: fleck, transparent: true, depthWrite: false }), ANZAHL);
  schatten.instanceMatrix.setUsage(THREE.DynamicDrawUsage); schatten.frustumCulled = false; scene.add(schatten);
  schatten.visible = false;                                  // erst mit den Enten – sonst liegen Flecken ohne Ente da

  // Zufall mit fester Saat – jede Ente hat ihr eigenes Tempo, ihren eigenen Kurs und ihren eigenen Mut
  let saat = 11;
  const zufall = () => ((saat = (saat * 16807) % 2147483647) / 2147483647);
  // Neuer Durchgang wie ein Reset im RL: am Anfang des eigenen Übungsfelds, leicht versetzt und schräg
  function neuStart(d) {
    d.lx = -PL / 2 + RAND; d.lz = (zufall() - 0.5) * 0.12;
    d.richtung = (zufall() - 0.5) * 0.4; d.kurs = 0; d.wander = zufall() * 6.28;
    d.fall = -1; d.zeitum = false; d.sicht = 0; d.phase = zufall() * 6.28; d.seite = zufall() < 0.5 ? 1 : -1;
  }
  // Lage auf dem Feld (lokal) → Welt; Höhe aus dem Profil des eigenen Felds
  function lage(d) {
    const c = Math.cos(d.dreh), sn = Math.sin(d.dreh);
    d.px = d.x + d.lx * c + d.lz * sn; d.pz = d.z - d.lx * sn + d.lz * c;
    d.h = BODEN[art(d.i)].f((d.lx + PL / 2) / PL);
  }
  // Jede Ente auf ihrem eigenen Feld; die Reihen sind gegenläufig, darum laufen sie hin und zurück
  const enten = Array.from({ length: ANZAHL }, (_, i) => {
    const d = { i, takt: 0.88 + zufall() * 0.24, ...platz(i) };
    neuStart(d);
    d.lx += zufall() * (PL - 2 * RAND) * 0.9;                // nicht alle gleichzeitig am Start
    d.sicht = 1;
    lage(d);
    return d;
  });
  // Plätze im Netz nach Nähe zur Kamera (sie steht auf der +z-Seite): wird gespart, fallen die hinteren zuerst weg
  [...enten].sort((a, b) => b.z - a.z || Math.abs(a.x) - Math.abs(b.x)).forEach((d, k) => { d.platz = k; });

  let ente = null;                // { netz, zelle, S } – die Bild-Enten
  let stufe = 0, messung = [];
  let sichtbarAnzahl = ANZAHL;
  // Sparen auf schwacher Grafik: Bilder dauern im Mittel länger als 45 ms → weniger Bildpunkte, dann nur die vordere
  // Hälfte, dann ein Viertel der Enten (die Zahlen zählen weiter alle)
  function sparen(neu = stufe + 1) {
    stufe = neu;
    sichtbarAnzahl = stufe >= 3 ? Math.ceil(ANZAHL / 4) : stufe >= 2 ? Math.ceil(ANZAHL / 2) : ANZAHL;
    for (const m of [ente && ente.netz, schatten]) if (m) m.count = sichtbarAnzahl;
    const felder = halle.userData.felder;                // kein leeres Übungsfeld: nur so viele Felder wie Enten
    felder.geometry.setDrawRange(0, felder.userData.ende[sichtbarAnzahl - 1]);
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 1.5) * [1, 0.8, 0.65, 0.5][stufe]);
    canvas.dataset.sparen = String(stufe);
  }

  let erfolg = 0.2;               // Anteil der Durchgänge ohne Sturz (0…1)
  let lauf = null;                // {erfolg, name} – sonst Zeitraffer
  let t0 = performance.now(), letzt = t0, raf = 0, sichtbar = false, runde = 1;
  const m4 = new THREE.Matrix4(), q = new THREE.Quaternion(), v = new THREE.Vector3(), s = new THREE.Vector3();
  const oben = new THREE.Vector3(0, 1, 0);
  let zahlen = () => {};


  function schritt(dt, zeit) {
    if (!lauf) {                                          // Zeitraffer: eine Lernkurve in 60 Sekunden
      const t = (zeit / 1000) % 60;
      runde = Math.floor(zeit / 60000) + 1;
      erfolg = 0.1 + 0.82 * (1 - Math.exp(-t / 16));
    } else erfolg = lauf.erfolg;
    // Sturzgefahr je Sekunde so, dass ein Durchgang mit Wahrscheinlichkeit „erfolg“ ohne Sturz bleibt
    const gefahr = -Math.log(Math.max(0.02, Math.min(0.995, erfolg))) / DURCHGANG;
    let stehen = 0;
    for (const d of enten) {
      if (d.fall < 0) {
        d.sicht = Math.min(1, d.sicht + dt * 5);
        const tempo = TEMPO * d.takt;
        d.phase += dt * Math.PI * 2 * FREQ * d.takt;
        d.wander += dt * 0.6;
        d.kurs = Math.sin(d.wander) * 0.18;                 // die Policy schlingert ein wenig
        const a = d.richtung + d.kurs;
        d.lx += Math.cos(a) * tempo * dt; d.lz -= Math.sin(a) * tempo * dt;
        d.lz = Math.max(-PB / 2 + 0.05, Math.min(PB / 2 - 0.05, d.lz));     // sie korrigiert, bevor sie vom Feld läuft
        if (Math.abs(d.lz) >= PB / 2 - 0.05) d.richtung *= 0.9;
        if (zufall() < dt * gefahr * BODEN[art(d.i)].schwer) d.fall = 0;
        if (d.lx > PL / 2 - RAND) { d.fall = 1.0; d.zeitum = true; }   // geschafft → Welt zurücksetzen, neuer Durchgang
        else stehen++;
      } else {
        d.fall += dt;
        if (d.fall > 1.0) d.sicht = Math.max(0, 1 - (d.fall - 1.0) / 0.2);   // Welt zurücksetzen: ausblenden …
        if (d.fall > 1.2) neuStart(d);                                        // … und am Start wieder da
      }
      lage(d);
      const px = d.px, pz = d.pz, h = d.h;
      // Blick der Kamera im Rahmen der Ente → Spalte; Gangphase oder Sturz → Zeile
      const yaw = d.dreh + d.richtung + d.kurs;             // Blick in Laufrichtung auf dem eigenen Feld
      const vx = kamera.position.x - px, vz = kamera.position.z - pz;
      const lx = vx * Math.cos(yaw) - vz * Math.sin(yaw), lz = vx * Math.sin(yaw) + vz * Math.cos(yaw);
      let b = Math.atan2(-lz, lx);
      let zeile = Math.floor((((d.phase % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2)) / (Math.PI * 2) * GANG) % GANG;
      let spiegel = 1;
      if (d.fall >= 0 && !d.zeitum) {
        zeile = d.fall < 0.22 ? GANG : GANG + 1;
        if (d.seite < 0) { b = -b; spiegel = -1; }          // zur anderen Seite: gespiegeltes Bild
      }
      const k = ((Math.round(b / (Math.PI * 2) * BLICKE) % BLICKE) + BLICKE) % BLICKE;
      if (ente) {
        ente.zelle.setXYZ(d.platz, k / BLICKE, 1 - (zeile + 1) / ZEILEN, d.sicht);
        q.setFromAxisAngle(oben, Math.atan2(vx, vz));
        v.set(px, h, pz);
        s.set(spiegel, 1, 1).multiplyScalar(ente.f);
        ente.netz.setMatrixAt(d.platz, m4.compose(v, q, s));
      }
      const lieg = d.fall >= 0.22 && !d.zeitum ? 1 : 0;
      v.set(px + lieg * d.seite * 0.05 * Math.sin(yaw), h + 0.002, pz + lieg * d.seite * 0.05 * Math.cos(yaw));
      q.identity();
      s.set((0.15 + lieg * 0.1) * d.sicht, 1, (0.15 + lieg * 0.04) * d.sicht).multiplyScalar(ente ? (ente.S * ente.f) / 0.33 : 1);
      schatten.setMatrixAt(d.platz, m4.compose(v, q, s));
    }
    if (ente) { ente.zelle.needsUpdate = true; ente.netz.instanceMatrix.needsUpdate = true; }
    schatten.instanceMatrix.needsUpdate = true;
    zahlen({ stehen, anzahl: ANZAHL, erfolg, durchgang: runde, runde, lauf });
  }

  function groesse() {
    const w = canvas.clientWidth || 800, h = canvas.clientHeight || 300;
    if (canvas.width !== Math.round(w * renderer.getPixelRatio())) renderer.setSize(w, h, false);
    kamera.aspect = w / h;
    kamera.updateProjectionMatrix();
  }

  // Kamera wie in einer Keynote: tief und weit, gleitet langsam seitlich über das Feld und zurück
  // Auftakt wie im Video von NVIDIA zur Microduck: erst nah an einer Ente, dann zieht die Kamera auf das ganze Feld auf
  const blick = new THREE.Vector3(), ziel = new THREE.Vector3();
  function kameraStellen(zeit) {
    // feste Kamera für Website und Doku (seit 0.38.56, „nimm lieber das Bild bei Lernen“): "x,y,z,zielX,zielY,zielZ"
    const fest = (canvas.dataset.blick || '').split(',').map(Number);
    if (fest.length === 6 && fest.every(Number.isFinite)) {
      kamera.position.set(fest[0], fest[1], fest[2]);
      kamera.lookAt(fest[3], fest[4], fest[5]);
      return;
    }
    const t = ruhig ? 0 : zeit / 1000;
    const a = 0.42 + Math.sin(t / 14) * 0.22;
    const schmal = kamera.aspect < 1.4;
    const r = schmal ? 5.6 : 7.4 + Math.sin(t / 21) * 0.5;     // schmal (Handy): näher heran
    kamera.position.set(Math.sin(a) * r, (schmal ? 1.5 : 1.75) + Math.sin(t / 17) * 0.2, Math.cos(a) * r);
    ziel.set(Math.sin(t / 19) * 0.9, 0.05, 0.4);
    const auf = ruhig ? 1 : Math.min(1, t / 6);
    if (auf < 1) {
      const e = auf * auf * (3 - 2 * auf);                    // weich anfahren und abbremsen
      const vorn = enten.find((d) => d.platz === 0);
      blick.set(vorn.px, vorn.h + 0.1, vorn.pz);
      kamera.position.lerpVectors(blick.clone().add(new THREE.Vector3(0.45, 0.18, 0.6)), kamera.position, e);
      ziel.lerpVectors(blick, ziel, e);
    }
    kamera.lookAt(ziel);
  }

  function bild(zeit) {
    const roh = zeit - letzt;
    const dt = Math.min(0.05, roh / 1000);
    letzt = zeit;
    if (stufe < 3 && roh > 0 && roh < 8000 && canvas.dataset.sparen !== 'nie') {   // 'nie': Bilder für Website und Doku
      messung.push(roh);
      const n = messung.length;
      if (n > 4 && roh > 400) { messung = []; sparen(); }                        // sehr langsam: sofort sparen
      else if (n >= 24) { const mittel = messung.slice(4).reduce((a, b) => a + b, 0) / (n - 4); messung = []; if (mittel > 45) sparen(); }
    }
    groesse();
    kameraStellen(zeit - t0);
    schritt(dt, zeit - t0);
    renderer.render(scene, kamera);
    if (sichtbar && !ruhig) raf = requestAnimationFrame(bild);
  }

  function weiter() {
    cancelAnimationFrame(raf);
    if (sichtbar) { letzt = performance.now(); raf = requestAnimationFrame(bild); }
  }

  function standbild() {
    groesse(); kameraStellen(0);
    for (let k = 0; k < 40; k++) schritt(0.05, 30000);
    requestAnimationFrame(() => { groesse(); kameraStellen(0); renderer.render(scene, kamera); });
  }

  // Nur rechnen, wenn das Feld zu sehen ist (Ansicht offen, Fenster sichtbar, im Bild)
  const beob = new IntersectionObserver(([x]) => { sichtbar = x.isIntersecting && !document.hidden; weiter(); });
  beob.observe(canvas);
  document.addEventListener('visibilitychange', () => { sichtbar = !document.hidden && canvas.offsetParent !== null; weiter(); });

  // Den Bogen zeichnen, ohne die Seite anzuhalten: ein Teilbild je Bild der Seite
  const warten = () => new Promise((ok) => (document.hidden ? setTimeout(ok, 0) : requestAnimationFrame(() => ok())));
  let bauNr = 0;
  let bau = () => {};
  async function figurSetzen(figur, schluessel = '') {
    const nr = ++bauNr;
    const t = performance.now();
    if (!ente) bau(true);                                   // noch keine Enten im Feld: sagen, dass sie kommen
    let fertig = schluessel ? await ausDemSpeicher(schluessel) : null;
    canvas.dataset.bogenAus = fertig ? 'speicher' : 'gezeichnet';
    if (!fertig) {
      fertig = await bildbogen(figur(), warten);
      if (schluessel && nr === bauNr) inDenSpeicher(schluessel, fertig);
    }
    const { bogen, S, mitte, hoehe } = fertig;
    if (nr !== bauNr) return false;                        // inzwischen eine andere Figur gewünscht
    if (!ente) t0 = performance.now();                      // der Auftakt beginnt, wenn die ersten Enten stehen
    if (ente) { scene.remove(ente.netz); ente.netz.geometry.dispose(); ente.netz.material.map.dispose(); ente.netz.material.dispose(); }
    ente = bildEnten(bogen, S, mitte, hoehe);
    ente.netz.count = sichtbarAnzahl;
    scene.add(ente.netz);
    schatten.visible = true;
    bau(false);
    canvas.dataset.bogenMs = String(Math.round(performance.now() - t));
    canvas.feldBogen = bogen;                               // für Prüfungen: der gezeichnete Bildbogen
    if (ruhig) standbild();
    return true;
  }

  canvas.feldInfo = () => ({ ...renderer.info.render, anzahl: ANZAHL, bilder: ente ? 1 : 0 });   // für Prüfungen
  // Website-Bilder (seit 0.38.56): alle Enten, feste Kamera aus data-blick, jetzt zeichnen – headless steht die Schleife
  canvas.feldZeichnen = () => {
    if (stufe) { sparen(0); canvas.dataset.sparen = 'nie'; }
    groesse(); kameraStellen(performance.now() - t0); renderer.render(scene, kamera);
  };
  let modellSchluessel = '';
  canvas.dataset.figur = 'einfach';                        // für den Abnahmetest: welche Figur steht im Feld
  return {
    // Lauf mit gemessener Erfolgsquote (0…1) oder null für den Zeitraffer
    setLauf(neu) { lauf = neu; if (ruhig) standbild(); },
    beiZahlen(fn) { zahlen = fn; },
    beiBau(fn) { bau = fn; },
    get erfolg() { return erfolg; },
    get figur() { return modellSchluessel; },
    // Originalmodell, wenn es in der 3D-Ansicht gewählt ist (koerper: microduck | open_duck_mini), sonst die einfache Ente
    async setModell({ koerper = 'microduck', original = false, farbe = 'cream' } = {}) {
      const k = koerper === 'open_duck_mini' ? 'open_duck_mini' : 'microduck';
      const einfach = `einfach|${k}|${farbe}`;
      const wunsch = original ? `${k}|${farbe}` : einfach;
      if (wunsch === modellSchluessel) return modellSchluessel;
      // erst (oder ohne Original) die einfache Ente des Körpers – schnell gezeichnet
      if (modellSchluessel !== einfach && (!original || !ente)) {
        const d = () => { const e = new Duck(k === 'open_duck_mini' ? 'open_duck' : 'microduck'); e.setFarbe?.(farbe); return e; };
        if (await figurSetzen(d, `${einfach}|${BOGEN_STAND}|${PX}`)) { modellSchluessel = einfach; canvas.dataset.figur = 'einfach'; }
      }
      if (!original) return modellSchluessel;
      try {
        const modell = await loadModel(k === 'open_duck_mini' ? '/static/model/open_duck_mini.dpm' : MODEL_URL);
        const echt = () => { const e = new RealDuck(modell); e.setFarbe(farbe || 'cream'); return e; };
        const groesse = `${modell.positions.length}-${modell.indices.length}-${modell.head.parts.length}`;
        if (await figurSetzen(echt, `${wunsch}|${groesse}|${BOGEN_STAND}|${PX}`)) { modellSchluessel = wunsch; canvas.dataset.figur = `original ${k}`; }
      } catch (err) {
        console.info('Trainingsfeld: Originalmodell nicht da, einfache Enten bleiben:', err.message);
      }
      return modellSchluessel;
    },
  };
}
