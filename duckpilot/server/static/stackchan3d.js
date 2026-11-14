// Stack-chan in der 3D-Ansicht (seit 0.38.58). Gezeichnet nach Fotos des offenen Projekts, ohne dessen Dateien:
// heller Würfel als Kopf mit schwarzem Bildschirm vorn (das Gesicht), darunter das Servo-Gehäuse auf einem kleinen Fuß.
// Gleiche Schnittstelle wie die übrigen Figuren: root, body, headRoll, beakTip, povNode, update(st, dt).
// Das Gesicht kommt als `st.gesicht` {ausdruck, mund, wach, zustand}; Blinzeln und Blick zeichnet die Figur selbst.
// Koordinaten wie in duck3d.js: Simulator x = vorn, y = links, z = oben → three.js X = x, Y = z, Z = -y.
import * as THREE from './vendor/three.module.min.js';
import { allesVerschmelzen, rundKasten, stoff, teil } from './formen3d.js';

const F = { schale: 0xf2f1ee, fuss: 0xd9d8d4, servo: 0x2a2b2e, rahmen: 0x1b1c1f };
const KOPF = 0.06;            // Kopfwürfel, Kantenlänge
const DREH_Y = 0.052;         // Drehachse des Kopfes über dem Fuß
const BILD = 0.046;           // sichtbare Bildschirmfläche
const PX = 160;               // Auflösung der Gesichts-Textur

// Gesicht auf die Zeichenfläche: schwarzer Grund, weiße Augen und Mund wie das Standardgesicht des Projekts.
// a = Ausdruck, m = Mund offen 0…1, auf = Augen offen 0…1, bx/by = Blick (−1…1)
export function gesichtZeichnen(ctx, { a = 'ruhig', m = 0, auf = 1, bx = 0, by = 0 }) {
  const w = PX, h = PX;
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = ctx.strokeStyle = '#fff';
  ctx.lineCap = 'round';
  const augeY = h * 0.42 + by * 8, r = a === 'ueberrascht' ? 18 : 14;
  for (const s of [-1, 1]) {
    const x = w / 2 + s * w * 0.24 + bx * 8;
    ctx.beginPath();
    if (a === 'froh' && auf > 0.2) {                       // lachende Augen: Bögen nach oben
      ctx.lineWidth = 6;
      ctx.arc(x, augeY + 4, r, Math.PI * 1.15, Math.PI * 1.85);
      ctx.stroke();
    } else if (auf < 0.25 || a === 'muede') {               // zu oder müde: Strich
      ctx.lineWidth = 5;
      ctx.moveTo(x - r, augeY + 2); ctx.lineTo(x + r, augeY + 2);
      ctx.stroke();
    } else {
      const rr = a === 'neugierig' && s === 1 ? r * 1.25 : r;
      ctx.ellipse(x, augeY, rr, rr * auf, 0, 0, Math.PI * 2);
      ctx.fill();
      if (a === 'wuetend' || a === 'traurig') {             // Lid schräg darüber (schwarz)
        ctx.fillStyle = '#000';
        const innen = a === 'wuetend' ? -1 : 1;
        ctx.beginPath();
        ctx.moveTo(x - r - 3, augeY - r - 3 + (s * innen < 0 ? 15 : 0));
        ctx.lineTo(x + r + 3, augeY - r - 3 + (s * innen > 0 ? 15 : 0));
        ctx.lineTo(x + r + 3, augeY - r - 10); ctx.lineTo(x - r - 3, augeY - r - 10);
        ctx.fill();
        ctx.fillStyle = '#fff';
      }
    }
    if (a === 'verlegen') {                                  // rote Bäckchen
      ctx.fillStyle = '#e8707a';
      ctx.beginPath(); ctx.ellipse(x + s * 8, augeY + 24, 9, 4.5, 0, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = '#fff';
    }
  }
  const mx = w / 2, my = h * 0.72, breit = a === 'froh' ? 34 : 24;
  const offen = Math.max(0, Math.min(1, m));
  ctx.lineWidth = 5;
  ctx.beginPath();
  if (offen > 0.08 || a === 'ueberrascht') {                 // offener Mund beim Sprechen oder Staunen
    const hh = Math.max(offen, a === 'ueberrascht' ? 0.5 : 0) * 18 + 3;
    ctx.ellipse(mx, my, breit * (a === 'ueberrascht' ? 0.45 : 0.6), hh, 0, 0, Math.PI * 2);
    ctx.fill();
  } else if (a === 'froh') {
    ctx.arc(mx, my - 10, breit * 0.7, Math.PI * 0.2, Math.PI * 0.8);
    ctx.stroke();
  } else if (a === 'traurig') {
    ctx.arc(mx, my + 12, breit * 0.6, Math.PI * 1.25, Math.PI * 1.75);
    ctx.stroke();
  } else {
    ctx.moveTo(mx - breit / 2, my); ctx.lineTo(mx + breit / 2, my);
    ctx.stroke();
  }
}

export class StackChan {
  constructor() {
    this.root = new THREE.Group();
    const schale = stoff(F.schale, 'shell'), servo = stoff(F.servo, 'servo');
    // Fuß und Servo-Gehäuse: dreht sich nicht (der Kopf dreht über dem oberen Servo)
    this.body = new THREE.Group();
    this.root.add(this.body);
    teil(this.body, rundKasten(0.056, 0.008, 0.056, 0.006, 3), stoff(F.fuss, 'plastic'), 0, 0.004, 0);
    teil(this.body, rundKasten(0.046, 0.036, 0.046, 0.008, 3), schale, 0, 0.026, 0);
    teil(this.body, new THREE.CylinderGeometry(0.009, 0.009, 0.006, 20), servo, 0, 0.047, 0);
    // Kopf: drehen (Hochachse), nicken (Querachse); der Würfel sitzt über der Achse
    this.headYaw = new THREE.Group();
    this.headYaw.position.y = DREH_Y;
    this.body.add(this.headYaw);
    this.headPitch = new THREE.Group();
    this.headYaw.add(this.headPitch);
    this.headRoll = new THREE.Group();
    this.headPitch.add(this.headRoll);
    teil(this.headRoll, rundKasten(KOPF * 0.8, KOPF, KOPF, 0.009, 4), schale, 0, KOPF / 2, 0);
    teil(this.headRoll, rundKasten(0.004, BILD + 0.006, BILD + 0.006, 0.002, 2), stoff(F.rahmen, 'dark'),
      KOPF * 0.4 - 0.0015, KOPF / 2, 0);
    // Bildschirm: eigene Zeichenfläche, wird nur neu gezeichnet, wenn sich das Gesicht ändert
    this.leinwand = document.createElement('canvas');
    this.leinwand.width = this.leinwand.height = PX;
    this.ctx = this.leinwand.getContext('2d');
    this.textur = new THREE.CanvasTexture(this.leinwand);
    this.textur.colorSpace = THREE.SRGBColorSpace;
    const bild = new THREE.Mesh(new THREE.PlaneGeometry(BILD, BILD), new THREE.MeshBasicMaterial({ map: this.textur }));
    bild.position.set(KOPF * 0.4 + 0.0006, KOPF / 2, 0);
    bild.rotation.y = Math.PI / 2;                     // zeigt nach vorn (+X)
    bild.userData.einzeln = true;                      // eigene Textur – nicht zusammenfassen
    this.headRoll.add(bild);
    // Blickpunkt vor dem Gesicht und Kamera (Stack-chan: Kamera unter dem Bildschirm)
    this.beakTip = new THREE.Object3D();
    this.beakTip.position.set(KOPF * 0.6, KOPF / 2, 0);
    this.headRoll.add(this.beakTip);
    this.povNode = new THREE.Object3D();
    this.povNode.position.set(KOPF * 0.42, KOPF * 0.12, 0);
    this.headRoll.add(this.povNode);
    this._lage = { yaw: 0, pitch: 0 };
    this._mund = 0;
    this._t = 0;
    this._blinzeln = 3;
    this._letztes = '';
    allesVerschmelzen(this.root);
  }

  update(st, dt) {
    this.root.position.set(st.x || 0, st.stand_z || 0, -(st.y || 0));
    this.root.rotation.y = st.yaw || 0;
    const k = Math.min(1, dt * 10);
    const ziel = st.kopf_lage || {};
    for (const n of ['yaw', 'pitch']) this._lage[n] += ((ziel[n] || 0) - this._lage[n]) * k;
    this.headYaw.rotation.y = this._lage.yaw;
    this.headPitch.rotation.z = -this._lage.pitch;

    const g = st.gesicht || {};
    this._t += dt;
    this._mund += ((g.mund || 0) - this._mund) * Math.min(1, dt * 18);
    let auf = g.wach === false ? 0 : 1;
    if (auf && this._t > this._blinzeln) {                    // Blinzeln alle 3–6 s, 0,14 s lang
      auf = 0;
      if (this._t > this._blinzeln + 0.14) { this._t = 0; this._blinzeln = 3 + Math.random() * 3; }
    }
    const denkt = g.zustand === 'denkt';
    const f = { a: g.ausdruck || 'ruhig', m: Math.round(this._mund * 8) / 8, auf,
      bx: denkt ? 0.7 : 0, by: denkt ? -0.7 : (g.ausdruck === 'verlegen' ? 0.6 : 0) };
    if (g.zustand === 'zuhoeren' && f.a === 'ruhig') f.a = 'neugierig';
    const schluessel = JSON.stringify(f);
    if (schluessel !== this._letztes) {
      this._letztes = schluessel;
      gesichtZeichnen(this.ctx, f);
      this.textur.needsUpdate = true;
    }
  }
}
