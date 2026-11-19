// Stack-chan in der 3D-Ansicht (seit 0.38.58). Seit 0.38.61 mit Gehäuse und Füßen aus den offenen Gehäusedaten der
// Stack-chan-Community (Apache-2.0, `static/model/stackchan.dpm`, duckpilot/modell/stackchan.py) und in deren Maßen:
// Füße fest, darüber dreht und nickt der ganze Kopf – Schale und M5Stack-Kasten mit dem Bildschirm vorn (den zeichnet
// Knowlin selbst, er gehört nicht zu den Gehäusedaten). Bis das Modell geladen ist (oder ohne es) steht eine einfache
// gezeichnete Fassung in denselben Maßen.
// Gleiche Schnittstelle wie die übrigen Figuren: root, body, headRoll, beakTip, povNode, update(st, dt).
// Das Gesicht kommt als `st.gesicht` {ausdruck, mund, wach, zustand}; Blinzeln und Blick zeichnet die Figur selbst.
// Koordinaten wie in duck3d.js: Simulator x = vorn, y = links, z = oben → three.js X = x, Y = z, Z = -y.
import * as THREE from './vendor/three.module.min.js';
import { FINISH, loadModel } from './duckmodel.js';
import { allesVerschmelzen, rundKasten, stoff, teil } from './formen3d.js';
import { ZEICHNER } from './stackchan_gesichter.js';

export const STACKCHAN_URL = '/static/model/stackchan.dpm';
const F = { schale: 0xf2f1ee, m5: 0x2b2d31, glas: 0x0c0d0f, knopf: 0x8a8d93 };
const DREH_Y = 0.0405;        // Kopfgelenk über dem Boden (wie DREH_HOEHE beim Backen)
const KOPF = 0.054;           // Breite und Höhe von Schale und M5Stack
const KOPF_Y = -0.0035;       // Mitte des Kopfes unter dem Gelenk
const M5_X = 0.023, M5_T = 0.018;            // M5Stack-Kasten vor der Schale: Mitte, Tiefe
const BILD_B = 0.0408, BILD_H = 0.0306;      // sichtbarer Bildschirm (2 Zoll, 4:3)
const BILD_X = M5_X + M5_T / 2 + 0.0004, BILD_Y = KOPF_Y + 0.004;
const PX = 160;               // Breite der Gesichts-Textur (Höhe 3/4)
// LED-Farben: grün beim Zuhören, blau beim Sprechen; seit 0.39 frei wählbar und im Lichttanz (backends/stackchan.FARBEN)
const LED = { gruen: 0x34d27a, blau: 0x3d8bff, rot: 0xff4a4a, gelb: 0xffd23f, lila: 0xb36bff, tuerkis: 0x2ee6d6,
  orange: 0xff9a3c, weiss: 0xf4f6ff };

function zzMalen(ctx, w, h) {                                // schläft (seit 0.38.62): „Z z“ oben rechts
  ctx.fillStyle = '#fff';
  ctx.font = 'bold 18px sans-serif';
  ctx.fillText('Z', w * 0.8, h * 0.2);
  ctx.font = 'bold 12px sans-serif';
  ctx.fillText('z', w * 0.89, h * 0.11);
}

// Gesicht auf die Zeichenfläche: schwarzer Grund, weiße Augen und Mund wie das Standardgesicht des Projekts.
// a = Ausdruck, m = Mund offen 0…1, auf = Augen offen 0…1, bx/by = Blick (−1…1), s = Avatar (seit 0.39)
export function gesichtZeichnen(ctx, { a = 'ruhig', m = 0, auf = 1, bx = 0, by = 0, zz = false, s = 'standard' }) {
  const w = PX, h = PX * 0.75;
  if (ZEICHNER[s]) {
    ZEICHNER[s](ctx, { a, m, auf, bx, by }, w, h);
    if (zz) zzMalen(ctx, w, h);
    return;
  }
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = ctx.strokeStyle = '#fff';
  ctx.lineCap = 'round';
  const augeY = h * 0.42 + by * 8, r = a === 'ueberrascht' ? 18 : 14;
  for (const s of [-1, 1]) {
    const x = w / 2 + s * w * 0.24 + bx * 8;
    ctx.beginPath();
    if (a === 'schwindelig' && auf > 0.2) {                // schwindelig (seit 0.38.62): Spiralen
      ctx.lineWidth = 3.5;
      for (let i = 0; i <= 40; i++) {
        const w2 = i / 40 * Math.PI * 5, rr = r * i / 40;
        const px = x + rr * Math.cos(w2 * s), py = augeY + rr * Math.sin(w2 * s);
        if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
      }
      ctx.stroke();
    } else if (a === 'froh' && auf > 0.2) {                // lachende Augen: Bögen nach oben
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
  } else if (a === 'schwindelig') {                          // Wellenmund (seit 0.38.62)
    for (let i = 0; i <= 24; i++) {
      const px = mx - breit * 0.6 + i * breit * 1.2 / 24, py = my + 4 * Math.sin(i / 24 * Math.PI * 4);
      if (i) ctx.lineTo(px, py); else ctx.moveTo(px, py);
    }
    ctx.stroke();
  } else {
    ctx.moveTo(mx - breit / 2, my); ctx.lineTo(mx + breit / 2, my);
    ctx.stroke();
  }
  if (zz) zzMalen(ctx, w, h);
}

export class StackChan {
  constructor() {
    this.root = new THREE.Group();
    const schale = stoff(F.schale, 'shell');
    this.body = new THREE.Group();
    this.root.add(this.body);
    // Ersatz, bis das Originalgehäuse geladen ist: zwei Füße, Schale hinter dem M5Stack
    this.ersatzFuss = new THREE.Group();
    this.body.add(this.ersatzFuss);
    for (const s of [-1, 1]) teil(this.ersatzFuss, rundKasten(0.037, 0.008, 0.023, 0.004, 3), schale, 0.0045, 0.004, s * 0.0125);
    // Kopf: drehen (Hochachse), nicken (Querachse) um dasselbe Gelenk
    this.headYaw = new THREE.Group();
    this.headYaw.position.y = DREH_Y;
    this.body.add(this.headYaw);
    this.headPitch = new THREE.Group();
    this.headYaw.add(this.headPitch);
    this.headRoll = new THREE.Group();
    this.headPitch.add(this.headRoll);
    this.ersatzSchale = new THREE.Group();
    this.headRoll.add(this.ersatzSchale);
    teil(this.ersatzSchale, rundKasten(0.0425, KOPF, KOPF, 0.008, 3), schale, -0.00725, KOPF_Y, 0);
    // M5Stack-Kasten mit Glas und drei Knöpfen unter dem Bildschirm
    const m5 = new THREE.Group();
    this.headRoll.add(m5);
    teil(m5, rundKasten(M5_T, KOPF, KOPF, 0.004, 3), stoff(F.m5, 'dark'), M5_X, KOPF_Y, 0);
    teil(m5, rundKasten(0.001, BILD_H + 0.006, BILD_B + 0.006, 0.0015, 2), stoff(F.glas, 'glass'), BILD_X - 0.0008, BILD_Y, 0);
    for (const z of [-0.014, 0, 0.014]) {
      teil(m5, rundKasten(0.0012, 0.003, 0.008, 0.001, 2), stoff(F.knopf, 'plastic'), M5_X + M5_T / 2, KOPF_Y - 0.021, z);
    }
    // LEDs (seit 0.38.62, wie der StackChan von M5Stack): zwei Reihen à sechs, oben links über dem Bildschirm –
    // grün beim Zuhören, blau beim Sprechen, sonst aus
    this.ledStoff = new THREE.MeshStandardMaterial({ color: 0x1d1f23, emissive: 0x000000, roughness: 0.4 });
    const ledForm = new THREE.SphereGeometry(0.0007, 8, 6);
    for (const y of [0.0185, 0.021]) {
      for (let i = 0; i < 6; i++) {
        const led = new THREE.Mesh(ledForm, this.ledStoff);
        led.position.set(M5_X + M5_T / 2 + 0.0002, y, 0.0135 + i * 0.002);
        led.userData.einzeln = true;
        this.headRoll.add(led);
      }
    }
    // Bildschirm: eigene Zeichenfläche, wird nur neu gezeichnet, wenn sich das Gesicht ändert
    this.leinwand = document.createElement('canvas');
    this.leinwand.width = PX;
    this.leinwand.height = PX * 0.75;
    this.ctx = this.leinwand.getContext('2d');
    this.textur = new THREE.CanvasTexture(this.leinwand);
    this.textur.colorSpace = THREE.SRGBColorSpace;
    const bild = new THREE.Mesh(new THREE.PlaneGeometry(BILD_B, BILD_H), new THREE.MeshBasicMaterial({ map: this.textur }));
    bild.position.set(BILD_X, BILD_Y, 0);
    bild.rotation.y = Math.PI / 2;                     // zeigt nach vorn (+X)
    bild.userData.einzeln = true;                      // eigene Textur – nicht zusammenfassen
    this.headRoll.add(bild);
    // Blickpunkt vor dem Gesicht und Kamera (M5Stack CoreS3: Kamera über dem Bildschirm)
    this.beakTip = new THREE.Object3D();
    this.beakTip.position.set(BILD_X + 0.012, BILD_Y, 0);
    this.headRoll.add(this.beakTip);
    this.povNode = new THREE.Object3D();
    this.povNode.position.set(BILD_X, KOPF_Y + 0.023, 0);
    this.headRoll.add(this.povNode);
    this._lage = { yaw: 0, pitch: 0 };
    this._mund = 0;
    this._t = 0;
    this._blinzeln = 3;
    this._letztes = '';
    allesVerschmelzen(this.root);
    this.geladen = this._original().catch(() => false);
  }

  // Originalgehäuse laden (MJCF-Rahmen: z oben → three.js y oben); der Ersatz verschwindet, wenn es da ist
  async _original() {
    const model = await loadModel(STACKCHAN_URL);
    const mat = new THREE.MeshPhysicalMaterial({ color: F.schale, ...FINISH.shell });
    for (const m of model.head.meshes) {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(model.positions.slice(m.v[0] * 3, (m.v[0] + m.v[1]) * 3), 3));
      g.setAttribute('normal', new THREE.BufferAttribute(model.normals.slice(m.v[0] * 3, (m.v[0] + m.v[1]) * 3), 3, true));
      g.setIndex(new THREE.BufferAttribute(model.indices.slice(m.i[0], m.i[0] + m.i[1]), 1));
      g.computeBoundingSphere();
      const mesh = new THREE.Mesh(g, mat);
      mesh.castShadow = mesh.receiveShadow = true;
      mesh.rotation.x = -Math.PI / 2;
      (m.name === 'fuss' ? this.body : this.headRoll).add(mesh);
    }
    this.ersatzFuss.visible = this.ersatzSchale.visible = false;
    return true;
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
    if (g.zustand === 'schlaeft') f.zz = true;
    if (g.avatar && g.avatar !== 'standard') f.s = g.avatar;
    const led = LED[g.led] ?? 0;                               // LEDs nach Zustand
    if (led !== this._led) {
      this._led = led;
      this.ledStoff.color.setHex(led || 0x1d1f23);
      this.ledStoff.emissive.setHex(led);
      this.ledStoff.emissiveIntensity = led ? 2.2 : 0;
    }
    const schluessel = JSON.stringify(f);
    if (schluessel !== this._letztes) {
      this._letztes = schluessel;
      gesichtZeichnen(this.ctx, f);
      this.textur.needsUpdate = true;
    }
  }
}
