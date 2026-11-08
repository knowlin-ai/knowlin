// Odi ausprobieren (T4, seit 0.38.29) – Odi läuft ganz im Browser: kein Server, kein Konto, kein KI-Schlüssel, keine
// Anfragen nach draußen. Plan: „Ausprobieren ohne Installation auf knowlin.de – stark für den Launch.“
//
// Was hier steckt: das offene Modell der Open Duck Mini v2 (Apache-2.0) und dieselbe 3D-Ansicht wie in Knowlin
// (Modell-Lader, Licht, Dielenboden). Die Beine bewegt die Gangformel des einfachen Simulators
// (duckpilot/backends/sim.py → display_joints), hier nach JavaScript übertragen. Was fehlt, sagt die Seite selbst:
// keine Physik, kein Claude – Odi versteht nur ein paar Wörter.
import * as THREE from './vendor/three.module.min.js';
import { OrbitControls } from './vendor/OrbitControls.js';
import { parseModel, RealDuck } from './duckmodel.js';
import { studio } from './licht3d.js';
import { boden, himmel, teppich } from './raum3d.js';
import { clamp, gelenke, verstehen } from './gang.js';

const $ = (id) => document.getElementById(id);
const sprache = () => (document.documentElement.lang === 'en' ? 'en' : 'de');

// ── Texte (die Seite selbst ist zweisprachig; was das Skript sagt, steht hier) ──────────────────────────────────
const TEXT = {
  de: {
    laden: 'Odi wird geladen …', keinWebgl: 'Dieser Browser kann kein 3D (WebGL). Mit einem aktuellen Chrome, Edge, Firefox oder Safari geht es.',
    fehler: 'Odi ließ sich nicht laden. Bitte die Seite neu laden.', bereit: 'Hallo! Ich bin Odi. Drück die Pfeile oder sag mir, was ich tun soll.',
    rand: 'Hier ist die Spielfläche zu Ende.', sitzt: 'Ich sitze. Sag „steh auf“, dann geht es weiter.',
    unbekannt: 'Das verstehe ich hier noch nicht. Versuch: geh, dreh dich, setz dich, tanz, nick, schau dich um, zum Ball.',
    vor: 'Ich gehe los.', zurueck: 'Ich gehe rückwärts.', links: 'Ich drehe mich nach links.', rechts: 'Ich drehe mich nach rechts.',
    halt: 'Ich bleibe stehen.', sitzen: 'Ich setze mich.', aufstehen: 'Ich stehe auf.', nicken: 'Ja!', schuetteln: 'Nein.',
    umschauen: 'Ich schaue mich um.', tanzen: 'Musik an – ich tanze!', ball: 'Ich gehe zum Ball.', ballDa: 'Hab ihn!', hallo: 'Hallo! Schön, dass du da bist.',
    sitzenKnopf: 'Hinsetzen', aufstehenKnopf: 'Aufstehen', bild: 'Odi in 3D – mit den Pfeiltasten steuern', beispiel: 'z. B. geh zum Ball',
  },
  en: {
    laden: 'Loading Odi …', keinWebgl: 'This browser cannot show 3D (WebGL). A current Chrome, Edge, Firefox or Safari will do.',
    fehler: 'Odi could not be loaded. Please reload the page.', bereit: "Hi! I'm Odi. Press the arrows or tell me what to do.",
    rand: 'This is the edge of the play area.', sitzt: "I'm sitting. Say “stand up” to go on.",
    unbekannt: "I don't know that one here. Try: walk, turn, sit, dance, nod, look around, ball.",
    vor: 'Off I go.', zurueck: 'Walking backwards.', links: 'Turning left.', rechts: 'Turning right.', halt: 'Stopping.',
    sitzen: 'Sitting down.', aufstehen: 'Standing up.', nicken: 'Yes!', schuetteln: 'No.', umschauen: 'Looking around.',
    tanzen: "Music on – I'm dancing!", ball: 'Going to the ball.', ballDa: 'Got it!', hallo: 'Hi! Nice to meet you.',
    sitzenKnopf: 'Sit down', aufstehenKnopf: 'Stand up', bild: 'Odi in 3D – steer with the arrow keys', beispiel: 'e.g. go to the ball',
  },
};
const t = (k) => TEXT[sprache()][k];

// ── Die kleine Welt: runde Spielfläche, ein Ball ────────────────────────────────────────────────────────────
const FELD_R = 1.6;          // m
const ODI_R = 0.09;          // m – Körperradius (Kollision mit dem Ball, Abstand zum Rand)
const BALL_R = 0.05;
const MAX_VOR = 0.16, MAX_ZURUECK = -0.08, MAX_DREH = 0.9;

class Odi {
  constructor() {
    this.x = -0.35; this.y = 0; this.yaw = 0;
    this.vx = 0; this.vyaw = 0; this.wunsch = { vx: 0, vyaw: 0 };
    this.phase = 0; this.fold = 0; this.sitzt = false;
    this.kopf = { neck: 0, pitch: 0, yaw: 0, roll: 0 };
    this.programm = null;        // laufender Trick: { name, t, dauer, schritt(o, t) }
    this.ziel = null;            // „zum Ball“
    this.randGesagt = 0;
  }
  fahren(vx, vyaw) { this.programm = null; this.ziel = null; this.wunsch = { vx, vyaw }; }
}

function trick(name) {
  const k = { neck: 0, pitch: 0, yaw: 0, roll: 0 };
  switch (name) {
    case 'nicken': return { name, dauer: 1.6, schritt: (o, s) => { o.kopf = { ...k, pitch: 0.28 * Math.sin(s * Math.PI * 2 * 1.8) * Math.sin(Math.PI * s / 1.6) }; } };
    case 'schuetteln': return { name, dauer: 1.6, schritt: (o, s) => { o.kopf = { ...k, yaw: 0.45 * Math.sin(s * Math.PI * 2 * 1.8) * Math.sin(Math.PI * s / 1.6) }; } };
    case 'umschauen': return { name, dauer: 3.2, schritt: (o, s) => { o.kopf = { ...k, yaw: 0.8 * Math.sin(s * Math.PI * 2 / 3.2), pitch: -0.08 }; } };
    case 'tanzen': return { name, dauer: 8, schritt: (o, s) => {
      const takt = s * 2.2;                               // ~132 bpm
      o.kopf = { ...k, roll: 0.22 * Math.sin(takt * Math.PI), pitch: 0.12 * Math.sin(takt * Math.PI * 2), yaw: 0.25 * Math.sin(takt * Math.PI / 2) };
      o.wunsch = { vx: 0, vyaw: s < 2 || (s > 4 && s < 6) ? 0.9 * Math.sign(Math.sin(takt * Math.PI / 4) || 1) : 0 };
      if (s >= 6) o.wunsch = { vx: 0.06 * Math.sin(takt * Math.PI), vyaw: 0 };
    } };
    default: return null;
  }
}

// ── Seite einrichten ──────────────────────────────────────────────────────────────────────────────────────────
const leinwand = $('odi-bild');
const vorhang = $('vorhang');
const antwort = $('antwort');
let odi = null, welt = null;

function sagen(k) { antwort.textContent = t(k); }

function webglDa() {
  try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch { return false; }
}

async function starten() {
  const knopf = $('odi-start');
  if (!webglDa()) { $('vorhang-text').textContent = t('keinWebgl'); knopf.hidden = true; return; }
  knopf.disabled = true;
  $('vorhang-text').textContent = t('laden');
  try {
    const res = await fetch('demo/model/odi-modell.json');               // DPM2 als Base64 (siehe tools/website.py)
    if (!res.ok) throw new Error(`Modell fehlt (${res.status})`);
    const roh = Uint8Array.from(atob((await res.json()).daten), (c) => c.charCodeAt(0));
    const modell = parseModel(roh.buffer);
    welt = bauen(modell);
  } catch (e) {
    console.info('Odi:', e);
    $('vorhang-text').textContent = `${t('fehler')} (${String(e && e.message || e).slice(0, 120)})`;
    knopf.disabled = false;
    return;
  }
  vorhang.hidden = true;
  leinwand.hidden = false;
  welt.groesse();
  leinwand.focus({ preventScroll: true });
  sagen('bereit');
}

function bauen(modell) {
  const renderer = new THREE.WebGLRenderer({ canvas: leinwand, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  const scene = new THREE.Scene();
  const HINTERGRUND = 0x24262b;
  const licht = studio(renderer, scene, HINTERGRUND);
  scene.add(himmel(HINTERGRUND));
  scene.fog = new THREE.Fog(HINTERGRUND, 3.5, 8.5);
  scene.add(boden(renderer, 6, 6));
  const matte = teppich(0, 0, FELD_R);
  if (matte) scene.add(matte);
  // Rand der Spielfläche: ein leiser Ring
  const ring = new THREE.Mesh(new THREE.RingGeometry(FELD_R - 0.012, FELD_R, 96),
    new THREE.MeshBasicMaterial({ color: 0xf0962c, transparent: true, opacity: 0.55 }));
  ring.rotation.x = -Math.PI / 2; ring.position.y = 0.004;
  scene.add(ring);
  // Ball
  const ball = new THREE.Mesh(new THREE.SphereGeometry(BALL_R, 32, 16),
    new THREE.MeshPhysicalMaterial({ color: 0xf0962c, roughness: 0.45, clearcoat: 0.4 }));
  ball.castShadow = true;
  const b = { x: 0.55, y: 0.25, vx: 0, vy: 0, mesh: ball };
  scene.add(ball);

  const figur = new RealDuck(modell);
  scene.add(figur.root);
  odi = new Odi();

  const kamera = new THREE.PerspectiveCamera(40, 16 / 9, 0.01, 40);
  kamera.position.set(-1.25, 0.62, 0.95);
  const steuer = new OrbitControls(kamera, leinwand);
  steuer.enableDamping = true;
  steuer.target.set(-0.35, 0.12, 0);
  steuer.maxPolarAngle = Math.PI * 0.48;
  steuer.minDistance = 0.35;
  steuer.maxDistance = 4;
  steuer.update();

  const ruhig = matchMedia('(prefers-reduced-motion: reduce)');
  const uhr = new THREE.Clock();
  let sichtbar = true;
  new IntersectionObserver(([e]) => { sichtbar = e.isIntersecting; }).observe(leinwand);

  function groesse() {
    const r = leinwand.getBoundingClientRect();
    if (!r.width || !r.height) return;
    renderer.setSize(r.width, r.height, false);
    kamera.aspect = r.width / r.height;
    kamera.updateProjectionMatrix();
  }
  new ResizeObserver(groesse).observe(leinwand);

  const nachVorn = new THREE.Vector3();
  function schritt(dt) {
    const o = odi;
    // Trick oder „zum Ball“ setzt den Wunsch
    if (o.programm) {
      o.programm.t += dt;
      if (o.programm.t >= o.programm.dauer) {
        if (o.programm.name === 'tanzen') o.wunsch = { vx: 0, vyaw: 0 };
        o.programm = null; o.kopf = { neck: 0, pitch: 0, yaw: 0, roll: 0 };
      } else o.programm.schritt(o, o.programm.t);
    }
    if (o.ziel) {
      const dx = b.x - o.x, dy = b.y - o.y, d = Math.hypot(dx, dy);
      const fehler = Math.atan2(Math.sin(Math.atan2(dy, dx) - o.yaw), Math.cos(Math.atan2(dy, dx) - o.yaw));
      if (d < ODI_R + BALL_R + 0.03) { o.ziel = null; o.wunsch = { vx: 0, vyaw: 0 }; sagen('ballDa'); trickStarten('nicken', false); }
      else o.wunsch = { vx: Math.abs(fehler) > 0.5 ? 0 : MAX_VOR * Math.min(1, d / 0.3), vyaw: clamp(2.2 * fehler, -MAX_DREH, MAX_DREH) };
    }
    // Sitzen: Beine falten, solange sitzt kein Laufen
    o.fold += ((o.sitzt ? 1 : 0) - o.fold) * Math.min(1, dt * 3);
    const wunsch = o.fold > 0.05 ? { vx: 0, vyaw: 0 } : o.wunsch;
    // sanft anfahren und bremsen (wie die Glättung im Simulator)
    const a = Math.min(1, dt * 4);
    o.vx += (wunsch.vx - o.vx) * a;
    o.vyaw += (wunsch.vyaw - o.vyaw) * a;
    // Bewegung und Rand der Spielfläche
    let nx = o.x + Math.cos(o.yaw) * o.vx * dt, ny = o.y + Math.sin(o.yaw) * o.vx * dt;
    if (Math.hypot(nx, ny) > FELD_R - ODI_R) {
      nx = o.x; ny = o.y; o.vx = 0;
      if (performance.now() - o.randGesagt > 3000) { o.randGesagt = performance.now(); sagen('rand'); }
    }
    o.x = nx; o.y = ny; o.yaw += o.vyaw * dt;
    // Ball anstoßen
    const dx = b.x - o.x, dy = b.y - o.y, d = Math.hypot(dx, dy), reich = ODI_R + BALL_R;
    if (d < reich && d > 1e-6) {
      b.x = o.x + (dx / d) * reich; b.y = o.y + (dy / d) * reich;
      const v = Math.max(0.1, Math.abs(o.vx) * 1.8);
      b.vx += (dx / d) * v; b.vy += (dy / d) * v;
    }
    b.x += b.vx * dt; b.y += b.vy * dt;
    const reib = Math.exp(-1.4 * dt); b.vx *= reib; b.vy *= reib;
    const bd = Math.hypot(b.x, b.y);
    if (bd > FELD_R - BALL_R) {                                   // am Rand zurückprallen
      const nxr = b.x / bd, nyr = b.y / bd, vn = b.vx * nxr + b.vy * nyr;
      if (vn > 0) { b.vx -= 1.6 * vn * nxr; b.vy -= 1.6 * vn * nyr; }
      b.x = nxr * (FELD_R - BALL_R); b.y = nyr * (FELD_R - BALL_R);
    }
    // Gangphase: Schritte beim Laufen und beim Drehen auf der Stelle
    const laeuft = Math.abs(o.vx) > 0.01 || Math.abs(o.vyaw) > 0.08;
    if (laeuft) o.phase = (o.phase + 2 * Math.PI * (2 + 2 * Math.min(1, Math.abs(o.vx) / 0.25)) * dt) % (2 * Math.PI);
    else o.phase += (((o.phase < Math.PI) ? 0 : 2 * Math.PI) - o.phase) * Math.min(1, dt * 6);
  }

  function bild() {
    requestAnimationFrame(bild);
    const dt = Math.min(0.05, uhr.getDelta());
    if (!sichtbar || document.hidden) return;
    schritt(dt);
    const o = odi;
    const speed = Math.abs(o.vx) + 0.05 * Math.abs(o.vyaw);
    const k = Math.min(1, speed / 0.15) * (1 - o.fold);
    figur.update({
      x: o.x, y: o.y, yaw: o.yaw,
      display_joints: gelenke({ fold: o.fold, vx: o.vx, vyaw: o.vyaw, phase: o.phase, kopf: o.kopf }),
      pose: { z: 0, roll: 0.05 * k * Math.sin(o.phase), pitch: 0.025 * k * Math.sin(2 * o.phase + 0.5) },
    }, dt);
    b.mesh.position.set(b.x, BALL_R, -b.y);
    b.mesh.rotation.z -= (b.vx * dt) / BALL_R;
    b.mesh.rotation.x -= (b.vy * dt) / BALL_R;
    // Kamera folgt Odi sanft (ohne Ruck bei „Bewegung reduzieren“: dann springt das Ziel mit)
    nachVorn.set(o.x, 0.12, -o.y);
    const f = ruhig.matches ? 1 : Math.min(1, dt * 2.5);
    const vorher = steuer.target.clone();
    steuer.target.lerp(nachVorn, f);
    kamera.position.add(steuer.target.clone().sub(vorher));
    licht.key.position.copy(steuer.target).add(licht.keyOffset);
    licht.key.target.position.copy(steuer.target);
    steuer.update();
    renderer.render(scene, kamera);
  }
  requestAnimationFrame(bild);
  return { groesse, ball: b };
}

// ── Bedienung ─────────────────────────────────────────────────────────────────────────────────────────────────
const FAHRT = { vor: [MAX_VOR, 0], zurueck: [MAX_ZURUECK, 0], links: [0, MAX_DREH], rechts: [0, -MAX_DREH], halt: [0, 0] };

function fahrtKnoepfe(aktiv) {
  for (const k of document.querySelectorAll('[data-fahrt]')) k.setAttribute('aria-pressed', String(k.dataset.fahrt === aktiv && aktiv !== 'halt'));
}

function fahren(was, sprechen = true) {
  if (!odi) return;
  if (odi.sitzt && was !== 'halt') { sagen('sitzt'); return; }
  odi.fahren(...FAHRT[was]);
  fahrtKnoepfe(was);
  if (sprechen) sagen(was);
}

function sitzenKnopf() {
  const k = document.querySelector('[data-trick="sitzen"]');
  k.setAttribute('aria-pressed', String(odi.sitzt));
  k.replaceChildren(document.createTextNode(odi.sitzt ? t('aufstehenKnopf') : t('sitzenKnopf')));
}

function trickStarten(was, sprechen = true) {
  if (!odi) return;
  if (was === 'sitzen' || was === 'aufstehen') {
    odi.sitzt = was === 'sitzen';
    odi.programm = null; odi.kopf = { neck: 0, pitch: 0, yaw: 0, roll: 0 };
    odi.fahren(0, 0); fahrtKnoepfe('halt'); sitzenKnopf();
    if (sprechen) sagen(odi.sitzt ? 'sitzen' : 'aufstehen');
    return;
  }
  if (odi.sitzt && (was === 'tanzen' || was === 'ball')) { sagen('sitzt'); return; }
  if (was === 'ball') { odi.programm = null; odi.ziel = true; fahrtKnoepfe('halt'); if (sprechen) sagen('ball'); return; }
  const p = trick(was);
  if (!p) return;
  if (was === 'tanzen') { odi.ziel = null; odi.wunsch = { vx: 0, vyaw: 0 }; fahrtKnoepfe('halt'); }
  odi.programm = { ...p, t: 0 };
  if (sprechen) sagen(was);
}

$('odi-start').addEventListener('click', starten);

for (const k of document.querySelectorAll('[data-fahrt]')) {
  k.addEventListener('click', () => {
    if (!odi) { starten(); return; }
    const an = k.getAttribute('aria-pressed') === 'true';
    fahren(an ? 'halt' : k.dataset.fahrt);              // nochmal tippen hält an
  });
}
for (const k of document.querySelectorAll('[data-trick]')) {
  k.addEventListener('click', () => {
    if (!odi) { starten(); return; }
    if (k.dataset.trick === 'sitzen') trickStarten(odi.sitzt ? 'aufstehen' : 'sitzen');
    else trickStarten(k.dataset.trick);
  });
}
$('sagen').addEventListener('submit', (ev) => {
  ev.preventDefault();
  const feld = $('sagen-text');
  const was = verstehen(feld.value);
  feld.value = '';
  if (!odi) { starten(); return; }
  if (!was) { sagen('unbekannt'); return; }
  if (was === 'hallo') { trickStarten('nicken', false); sagen('hallo'); return; }
  if (FAHRT[was]) fahren(was); else trickStarten(was);
});

// Tastatur, solange das Bild ausgewählt ist: gedrückt halten = fahren, loslassen = stehen bleiben
const TASTEN = { ArrowUp: 'vor', KeyW: 'vor', ArrowDown: 'zurueck', KeyS: 'zurueck', ArrowLeft: 'links', KeyA: 'links',
  ArrowRight: 'rechts', KeyD: 'rechts', Space: 'halt' };
leinwand.addEventListener('keydown', (ev) => {
  const was = TASTEN[ev.code];
  if (!was) return;
  ev.preventDefault();
  if (!ev.repeat) fahren(was, false);
});
leinwand.addEventListener('keyup', (ev) => {
  if (TASTEN[ev.code] && TASTEN[ev.code] !== 'halt') fahren('halt', false);
});

// Sprache gewechselt: was das Skript geschrieben hat, nachziehen
new MutationObserver(() => {
  leinwand.setAttribute('aria-label', t('bild'));
  $('sagen-text').placeholder = t('beispiel');
  if (odi) sitzenKnopf();
  antwort.textContent = '';
}).observe(document.documentElement, { attributes: true, attributeFilter: ['lang'] });
leinwand.setAttribute('aria-label', t('bild'));
$('sagen-text').placeholder = t('beispiel');
window.odiBereit = true;            // für den Hinweis in der Seite, falls dieses Skript nicht lädt
