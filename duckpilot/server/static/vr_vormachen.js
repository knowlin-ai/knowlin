// Vormachen in der Quest (seit 0.48, Mentor): mit dem eigenen Kopf ihren Kopf führen, mit der Hand einen Arm.
// Nicht mit einer echten Brille geprüft – gebaut nach WebXR (Hand-Tracking, Viewer-Pose).
// - Schalttafel neben dem Roboter (anzeigen und abdrücken bzw. Finger zusammen): „Kopf vormachen“ an/aus, „Aufnehmen“.
// - Kopf: Lage der Brille relativ zum Einschalten → {type: 'marionette', gieren, nicken, neigen, quelle: 'vr'}.
// - Hand (nur Körper mit Arm, nur mit Hand-Tracking): 21 Gelenke der rechten Hand, aus deiner Sicht projiziert wie ein
//   Kamerabild, das dich ansieht → dieselbe Nachricht wie beim Vormachen per Webcam ({type: 'mentor_hand'}).
// Ins Netz gehen nur diese Zahlen; Bilder und Raumdaten der Brille bleiben in der Brille. Not-Aus: wie in vr.js.
import * as THREE from './vendor/three.module.min.js';

const TAKT_MS = 66;
// WebXR-Gelenke in der Reihenfolge der 21 MediaPipe-Punkte
const GELENKE = ['wrist',
  'thumb-metacarpal', 'thumb-phalanx-proximal', 'thumb-phalanx-distal', 'thumb-tip',
  'index-finger-phalanx-proximal', 'index-finger-phalanx-intermediate', 'index-finger-phalanx-distal', 'index-finger-tip',
  'middle-finger-phalanx-proximal', 'middle-finger-phalanx-intermediate', 'middle-finger-phalanx-distal', 'middle-finger-tip',
  'ring-finger-phalanx-proximal', 'ring-finger-phalanx-intermediate', 'ring-finger-phalanx-distal', 'ring-finger-tip',
  'pinky-finger-phalanx-proximal', 'pinky-finger-phalanx-intermediate', 'pinky-finger-phalanx-distal', 'pinky-finger-tip'];

// Punkt im Raum (Sicht der Brille: x rechts, y oben, −z nach vorn) → „Kamerabild, das dich ansieht“ (0…1)
export function projizieren(p) {
  const tiefe = Math.max(0.05, -p.z);
  return [+(0.5 - (0.9 * p.x) / tiefe).toFixed(4), +(0.5 - (0.9 * p.y) / tiefe).toFixed(4), 0];
}

// Lage der Brille relativ zur Nullstellung → gieren (+ links), nicken (+ hoch), neigen (+ rechts), rad
export function kopfLage(q, null0) {
  const rel = null0.clone().invert().multiply(q);
  const e = new THREE.Euler().setFromQuaternion(rel, 'YXZ');
  return { gieren: +e.y.toFixed(3), nicken: +e.x.toFixed(3), neigen: +(-e.z).toFixed(3) };
}

function tafel(text) {
  const c = document.createElement('canvas');
  c.width = 512; c.height = 128;
  const tex = new THREE.CanvasTexture(c);
  const m = new THREE.Mesh(new THREE.PlaneGeometry(0.24, 0.06), new THREE.MeshBasicMaterial({ map: tex, transparent: true }));
  m.zeichnen = (t, an) => {
    const g = c.getContext('2d');
    g.clearRect(0, 0, 512, 128);
    g.fillStyle = an ? '#2f7d4f' : '#2b2f36';
    g.beginPath(); g.roundRect(4, 4, 504, 120, 40); g.fill();
    g.fillStyle = '#ffffff';
    g.font = '600 46px system-ui, sans-serif';
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(t, 256, 66);
    tex.needsUpdate = true;
  };
  m.zeichnen(text, false);
  return m;
}

export function initVRVormachen({ send, eig, anker }) {
  const gruppe = new THREE.Group();
  const kopfKnopf = tafel('Kopf vormachen');
  const aufKnopf = tafel('Aufnehmen');
  aufKnopf.position.y = -0.075;
  gruppe.add(kopfKnopf, aufKnopf);
  gruppe.position.set(0.32, 0.22, 0);
  gruppe.visible = false;
  anker.add(gruppe);
  let kopfAn = false, null0 = null, aufnahme = false, zuletzt = 0, handZuletzt = 0, handDa = false;
  const q = new THREE.Quaternion(), blick = new THREE.Matrix4(), p = new THREE.Vector3(), kam = new THREE.Vector3();

  function kopfSchalten(an) {
    kopfAn = an;
    null0 = null;
    kopfKnopf.zeichnen(an ? 'Kopf: folgt dir' : 'Kopf vormachen', an);
    if (!an) send({ type: 'marionette_ende' });
  }
  async function aufnahmeSchalten() {
    const an = !aufnahme;
    const name = `VR ${new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    const r = await fetch('/api/marionette/aufnahme', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(an ? { aktion: 'start' } : { aktion: 'stopp', name }) }).then((x) => x.json()).catch(() => null);
    if (!r || r.ok === false) { aufKnopf.zeichnen('geht nicht', false); return; }
    aufnahme = an;
    aufKnopf.zeichnen(an ? 'Stopp + merken' : 'Gemerkt', an);
  }

  return {
    // Abdrücken: trifft der Strahl die Tafel? Dann schalten und true (sonst macht vr.js weiter)
    abdruecken(strahl) {
      if (!gruppe.visible) return false;
      const hit = strahl.intersectObjects([kopfKnopf, aufKnopf], false)[0];
      if (!hit) return false;
      if (hit.object === kopfKnopf) kopfSchalten(!kopfAn); else aufnahmeSchalten();
      return true;
    },
    // Führt gerade eine Hand den Arm? Dann ist „Finger zusammen“ ein Greifen, kein Abdrücken
    handFuehrt: () => handDa,
    zeigen(an) { gruppe.visible = an; },
    bild(frame, raum, kamera) {
      if (!frame || !raum) return;
      if (gruppe.visible) { kamera.getWorldPosition(kam); gruppe.lookAt(kam); }
      const sicht = frame.getViewerPose(raum);
      if (!sicht) return;
      const t = performance.now();
      if (kopfAn && eig().has('kopf') && t - zuletzt >= TAKT_MS) {
        const o = sicht.transform.orientation;
        q.set(o.x, o.y, o.z, o.w);
        if (!null0) null0 = q.clone();
        zuletzt = t;
        send({ type: 'marionette', quelle: 'vr', ...kopfLage(q, null0) });
      }
      // Hand → Arm (nur mit Arm und Hand-Tracking)
      if (!eig().has('arm') || t - handZuletzt < TAKT_MS) return;
      const quelle = [...frame.session.inputSources].find((s) => s.hand && s.handedness === 'right')
        || [...frame.session.inputSources].find((s) => s.hand);
      if (!quelle) { if (handDa) { handDa = false; send({ type: 'mentor_ende' }); } return; }
      blick.fromArray(sicht.transform.inverse.matrix);
      const punkte = [];
      for (const name of GELENKE) {
        const g = quelle.hand.get(name);
        const lage = g && frame.getJointPose(g, raum);
        if (!lage) { punkte.length = 0; break; }
        const pp = lage.transform.position;
        p.set(pp.x, pp.y, pp.z).applyMatrix4(blick);
        punkte.push(projizieren(p));
      }
      if (punkte.length !== 21) return;
      handZuletzt = t;
      handDa = true;
      send({ type: 'mentor_hand', seite: quelle.handedness || '', punkte });
    },
    ende() {
      if (kopfAn) kopfSchalten(false);
      if (handDa) { handDa = false; send({ type: 'mentor_ende' }); }
      gruppe.visible = false;
    },
  };
}
