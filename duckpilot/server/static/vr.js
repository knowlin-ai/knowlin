// VR und Mixed Reality mit der Meta Quest (seit 0.44, WebXR) – gebaut, aber NICHT mit einer echten Brille geprüft.
// Der Roboter aus dem Simulator steht auf deinem echten Boden (Passthrough, „immersive-ar“):
// - Auf den Boden zeigen und abdrücken: Dort steht er (Hit-Test). Danach heißt Abdrücken auf dem Boden „lauf dahin“
//   (nur mit Beinen oder Rädern, über das Werkzeug go_to mit allen Regeln), Abdrücken auf ihm „anstupsen“
//   (streicheln, wenn er Berührung kennt, sonst freut er sich).
// - Not-Aus: die Greiftaste (squeeze) an jedem Controller oder der rote Knopf im Overlay – derselbe Not-Aus wie überall.
// - Nur über eine sichere Adresse (https, z. B. Tailscale) – sonst bietet der Browser WebXR gar nicht an.
// Ins Netz geht nichts; Kamera- und Raumdaten der Brille bleiben in der Brille, hierher kommt nur der Abdrück-Punkt.
import * as THREE from './vendor/three.module.min.js';
import { figurFuer } from './portraet3d.js';

export function initVR({ $, send, toast, getConfig }) {
  const knopf = $('vr-start');
  if (!knopf || !navigator.xr || !window.isSecureContext) return;
  navigator.xr.isSessionSupported('immersive-ar').then((ja) => { knopf.hidden = !ja; }).catch(() => {});

  let renderer = null, session = null, figur = null, letzter = null, ursprung = null;
  let hitQuelle = null, gesetzt = false, letzteZeit = 0;
  const szene = new THREE.Scene();
  szene.add(new THREE.HemisphereLight(0xffffff, 0x444444, 2.2));
  const kamera = new THREE.PerspectiveCamera();
  const marke = new THREE.Mesh(new THREE.RingGeometry(0.06, 0.08, 32).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({ color: 0x4f9cf9 }));
  marke.matrixAutoUpdate = false;
  marke.visible = false;
  szene.add(marke);
  const anker = new THREE.Group();          // der Platz auf deinem Boden, an dem der Simulator beginnt
  szene.add(anker);
  const strahl = new THREE.Raycaster();
  const boden = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);

  const text = (t) => { $('vr-text').textContent = t; };
  const eig = () => new Set((getConfig() || {}).eigenschaften || []);
  const notaus = () => send({ type: 'stop' });

  window.addEventListener('knowlin:state', (ev) => { letzter = ev.detail; });

  // Simulator (x vorn, y links, z oben) → Anker (three.js: X = x, Y = z, Z = −y), relativ zur Lage beim Hinstellen
  function aufAnker(st) {
    const dx = st.x - ursprung.x, dy = st.y - ursprung.y;
    return new THREE.Vector3(dx, st.stand_z || 0, -dy);
  }
  function inSimulator(punktAnker) {
    return { x: ursprung.x + punktAnker.x, y: ursprung.y - punktAnker.z };
  }

  function abdruecken(ev) {
    if (!gesetzt) {
      if (!marke.visible || !letzter) return;
      anker.matrix.copy(marke.matrix);
      anker.matrix.decompose(anker.position, anker.quaternion, anker.scale);
      ursprung = { x: letzter.x, y: letzter.y };
      gesetzt = true;
      marke.visible = false;
      text('Abdrücken auf dem Boden: lauf dahin · auf ihm: anstupsen · Greiftaste: Not-Aus');
      return;
    }
    const c = ev.target;
    const m = new THREE.Matrix4().extractRotation(c.matrixWorld);
    strahl.ray.origin.setFromMatrixPosition(c.matrixWorld);
    strahl.ray.direction.set(0, 0, -1).applyMatrix4(m);
    if (figur && strahl.intersectObject(figur.root, true).length) {
      if (eig().has('beruehrung')) send({ type: 'tool', name: 'beruehren', args: { art: 'streicheln' } });
      else send({ type: 'tool', name: 'absicht', args: { aktion: 'freuen' } });
      return;
    }
    if (!(eig().has('beine') || eig().has('raeder'))) return;
    const ankerInv = new THREE.Matrix4().copy(anker.matrixWorld).invert();
    const lokal = strahl.ray.clone().applyMatrix4(ankerInv);
    const p = new THREE.Vector3();
    if (lokal.intersectPlane(boden, p)) {
      const z = inSimulator(p);
      send({ type: 'tool', name: 'go_to', args: { x: Math.round(z.x * 100) / 100, y: Math.round(z.y * 100) / 100 } });
    }
  }

  async function starten() {
    try {
      figur = await figurFuer((getConfig() || {}).modul);
    } catch (e) { toast(`Figur lädt nicht: ${e.message || e}`, true); return; }
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.xr.enabled = true;
    renderer.xr.setReferenceSpaceType('local-floor');
    try {
      session = await navigator.xr.requestSession('immersive-ar', {
        requiredFeatures: ['hit-test'], optionalFeatures: ['local-floor', 'dom-overlay'], domOverlay: { root: $('vr-overlay') },
      });
    } catch (e) { toast(`VR startet nicht: ${e.message || e}`, true); renderer.dispose(); renderer = null; return; }
    await renderer.xr.setSession(session);
    $('vr-overlay').hidden = false;
    text('Auf den Boden zeigen und abdrücken: Dort steht er.');
    gesetzt = false;
    if (figur) anker.add(figur.root);
    for (const i of [0, 1]) {
      const c = renderer.xr.getController(i);
      c.addEventListener('select', abdruecken);
      c.addEventListener('squeeze', notaus);           // Greiftaste = Not-Aus
      szene.add(c);
    }
    const ansicht = await session.requestReferenceSpace('viewer');
    hitQuelle = await session.requestHitTestSource({ space: ansicht });
    session.addEventListener('end', aufraeumen);
    renderer.setAnimationLoop(bild);
  }

  function bild(zeit, frame) {
    const dt = letzteZeit ? Math.min(0.1, (zeit - letzteZeit) / 1000) : 0;
    letzteZeit = zeit;
    if (!gesetzt && frame && hitQuelle) {
      const treffer = frame.getHitTestResults(hitQuelle);
      const raum = renderer.xr.getReferenceSpace();
      const lage = treffer.length ? treffer[0].getPose(raum) : null;
      marke.visible = !!lage;
      if (lage) marke.matrix.fromArray(lage.transform.matrix);
    }
    if (figur && letzter) {
      figur.update(letzter, dt);
      if (gesetzt && ursprung) {
        figur.root.position.copy(aufAnker(letzter));
        figur.root.rotation.y = letzter.yaw || 0;
      }
      figur.root.visible = gesetzt;
    }
    renderer.render(szene, kamera);
  }

  function aufraeumen() {
    if (renderer) { renderer.setAnimationLoop(null); renderer.dispose(); }
    if (figur) anker.remove(figur.root);
    renderer = session = hitQuelle = null;
    gesetzt = false;
    letzteZeit = 0;
    $('vr-overlay').hidden = true;
  }

  knopf.addEventListener('click', starten);
  $('vr-notaus').addEventListener('click', notaus);
  $('vr-ende').addEventListener('click', () => { if (session) session.end(); });
}
