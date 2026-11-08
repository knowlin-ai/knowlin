// Reachy Mini aus Pollens 3D-Modell (seit 0.38.2) – nachgeladen wie bei der Microduck (`/api/modell/reachy.dpm`,
// auf diesem PC aus Pollens Dateien gebacken). Gleiche Schnittstelle wie das gezeichnete Modell in reachy3d.js.
//
// Der Kopf sitzt auf einer Stewart-Plattform: sechs Motoren mit Armen, sechs Stangen, geschlossene Kette. Wie bei
// Pollen kommt die Kopflage vorgegeben (Welt: Körperdrehung + Lage relativ zum Körper); die Motorwinkel rechnet die
// Ansicht selbst aus (Stangenlänge fest → je Motor eine Gleichung, Lösung nahe am letzten Winkel) und richtet die
// Stangen zwischen Arm und Kopf aus. Gegen Pollens eigene Kinematik geprüft (gleiche Winkel auf 0,001 rad).
import * as THREE from './vendor/three.module.min.js';
import { FINISH, loadModel } from './duckmodel.js';
import { allesVerschmelzen } from './formen3d.js';

export const REACHY_URL = '/api/modell/reachy.dpm';
export const loadReachy = () => loadModel(REACHY_URL);

const v3 = (a) => new THREE.Vector3(a[0], a[1], a[2]);
const q4 = (q) => new THREE.Quaternion(q[1], q[2], q[3], q[0]);   // MJCF w x y z
const lokal = (b) => new THREE.Matrix4().compose(v3(b.pos), q4(b.quat), new THREE.Vector3(1, 1, 1));
const _m = new THREE.Matrix4(), _rz = new THREE.Matrix4(), _p = new THREE.Vector3(), _q = new THREE.Vector3();
const _o = new THREE.Vector3(), _f = new THREE.Vector3(), _quat = new THREE.Quaternion(), _e = new THREE.Euler();

export class RealReachy {
  constructor(model) {
    const { head } = model;
    this.head = head;
    this.istReachy = true;
    this.root = new THREE.Group();                 // Lage des Sockels in der Welt
    this.mj = new THREE.Group();                   // MJCF: z oben → three.js: y oben
    this.mj.rotation.x = -Math.PI / 2;
    this.root.add(this.mj);

    const geos = head.meshes.map((m) => {
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.BufferAttribute(model.positions.slice(m.v[0] * 3, (m.v[0] + m.v[1]) * 3), 3));
      g.setAttribute('normal', new THREE.BufferAttribute(model.normals.slice(m.v[0] * 3, (m.v[0] + m.v[1]) * 3), 3, true));
      g.setIndex(new THREE.BufferAttribute(model.indices.slice(m.i[0], m.i[0] + m.i[1]), 1));
      g.computeBoundingSphere();
      return g;
    });
    const mats = new Map();
    const matFor = (rgb, finish) => {
      const key = `${rgb.join(',')}|${finish}`;
      if (!mats.has(key)) {
        const c = new THREE.Color().setRGB(rgb[0], rgb[1], rgb[2], THREE.SRGBColorSpace);
        mats.set(key, new THREE.MeshPhysicalMaterial({ color: c, ...(FINISH[finish] || FINISH.plastic) }));
      }
      return mats.get(key);
    };

    // Jeder Körper als eigene Gruppe direkt unter mj; ihre Lage rechnet update() je Bild aus
    this.L = head.bodies.map(lokal);
    this.W = head.bodies.map(() => new THREE.Matrix4());
    this.nodes = head.bodies.map((b) => {
      const g = new THREE.Group();
      g.name = b.name;
      g.matrixAutoUpdate = false;
      this.mj.add(g);
      return g;
    });
    for (const p of head.parts) {
      const mesh = new THREE.Mesh(geos[p.mesh], matFor(p.rgb, p.finish));
      mesh.position.copy(v3(p.pos));
      mesh.quaternion.copy(q4(p.quat));
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      this.nodes[p.body].add(mesh);
    }
    allesVerschmelzen(this.mj);             // gleiche Materialien je Teil zusammen: weniger Zeichenaufrufe
    const K = head.kinematik;
    this.K = K;
    this.stange = new Map(K.stangen.map((s) => [s.stange, s]));
    this.horn = new Map(K.stangen.map((s) => [s.horn, s]));
    this.theta = K.stangen.map(() => 0);
    this.site = lokal(K.kopf_site);
    this.siteInv = this.site.clone().invert();
    this.joint = new Map(head.bodies.map((b, i) => [i, b.joint]));

    // Schnittstelle wie das gezeichnete Modell: body, headRoll, povNode/beakTip
    this.body = this.nodes[K.koerper];
    this.headRoll = this.nodes[K.kopf];
    const siteNode = new THREE.Object3D();
    siteNode.position.copy(v3(K.kopf_site.pos));
    siteNode.quaternion.copy(q4(K.kopf_site.quat));
    this.headRoll.add(siteNode);
    // Kamera vor den Augen: Pollens camera_optical liegt im Kopf; im Bezugsrahmen „head“ ist x vorn, z oben
    const cam = v3(K.kamera).applyMatrix4(this.siteInv);
    this.povNode = new THREE.Object3D();
    this.povNode.position.set(Math.max(cam.x, 0.03) + 0.01, cam.y, cam.z);
    this.povNode.rotation.x = Math.PI / 2;            // lokal y = oben (für die Kopfkamera in duck3d.js)
    siteNode.add(this.povNode);
    this.beakTip = this.povNode;

    this._lage = { x: 0, y: 0, z: 0, roll: 0, pitch: 0, yaw: 0, koerper: 0 };
    this._gueltig = { ...this._lage };           // zuletzt erreichbare Kopflage (seit 0.38.10)
    this._fehlt = false;
    this._ant = [-0.1745, 0.1745];
    this._pose = new THREE.Matrix4();
    this._kopf = new THREE.Matrix4();
    this.rechne(this._lage, this._ant);
  }

  // Kopflage (relativ zum Körper) + Körperdrehung → Lage aller Teile. false: eine Stange reicht nicht hin
  rechne(L, ant) {
    const K = this.K;
    this._fehlt = false;
    _rz.makeRotationZ(L.koerper);
    _e.set(L.roll, L.pitch, L.yaw, 'ZYX');            // Pollen: R = Rz(yaw)·Ry(pitch)·Rx(roll)
    this._pose.makeRotationFromEuler(_e).setPosition(L.x, L.y, L.z + K.kopf_z).premultiply(_rz);
    this._kopf.multiplyMatrices(this._pose, this.siteInv);
    const bodies = this.head.bodies;
    for (let i = 0; i < bodies.length; i++) {
      const b = bodies[i];
      const W = this.W[i];
      if (i === K.kopf) {
        W.copy(this._kopf);
      } else if (this.stange.has(i)) {
        this._stange(i, this.stange.get(i));
      } else {
        if (b.parent >= 0) W.multiplyMatrices(this.W[b.parent], this.L[i]); else W.copy(this.L[i]);
        const j = b.joint;
        let winkel = 0;
        if (j === 'yaw_body') winkel = L.koerper;
        else if (j === 'right_antenna') winkel = ant[0];
        else if (j === 'left_antenna') winkel = ant[1];
        else if (this.horn.has(i)) winkel = this._ik(i, this.horn.get(i), W);
        if (winkel) W.multiply(_m.makeRotationAxis(v3(b.axis || [0, 0, 1]).normalize(), winkel));
      }
      this.nodes[i].matrix.copy(W);
      this.nodes[i].matrixWorldNeedsUpdate = true;
    }
    return !this._fehlt;
  }

  // Motorwinkel: Stangenende am Arm muss genau „laenge“ vom Ansatz am Kopf entfernt sein
  _ik(i, s, Whorn0) {
    const k = this.K.stangen.indexOf(s);
    _p.set(...s.anker).applyMatrix4(this._kopf);
    const rodL = this.L[s.stange];
    const f = (th) => {
      _m.copy(Whorn0).multiply(_rz.makeRotationZ(th)).multiply(rodL);
      return _q.setFromMatrixPosition(_m).distanceTo(_p) - s.laenge;
    };
    const [lo, hi] = this.head.bodies[i].range || [-Math.PI, Math.PI];
    const n = 48, step = (hi - lo) / n;
    let best = null;
    let a = lo, fa = f(a);
    for (let t = 1; t <= n; t++) {
      const b = lo + t * step, fb = f(b);
      if (fa === 0 || fa * fb < 0) {
        let x0 = a, x1 = b, f0 = fa;
        for (let it = 0; it < 24; it++) {
          const m = (x0 + x1) / 2, fm = f(m);
          if (f0 * fm <= 0) x1 = m; else { x0 = m; f0 = fm; }
        }
        const r = (x0 + x1) / 2;
        if (best === null || Math.abs(r - this.theta[k]) < Math.abs(best - this.theta[k])) best = r;
      }
      a = b; fa = fb;
    }
    if (best !== null) this.theta[k] = best;      // keine Lösung (außer Reichweite): letzten Winkel halten …
    else this._fehlt = true;                      // … und update() zeichnet den Kopf in der letzten gültigen Lage
    return this.theta[k];
  }

  // Stange zwischen Armende und Ansatz am Kopf ausrichten (Kugelgelenke an beiden Enden)
  _stange(i, s) {
    const W = this.W[i];
    W.multiplyMatrices(this.W[s.horn], this.L[i]);
    _o.setFromMatrixPosition(W);
    _f.set(...s.fern).applyMatrix4(W).sub(_o).normalize();
    _p.set(...s.anker).applyMatrix4(this._kopf).sub(_o).normalize();
    _quat.setFromUnitVectors(_f, _p);
    _m.makeRotationFromQuaternion(_quat);
    const t = new THREE.Matrix4().makeTranslation(_o.x, _o.y, _o.z);
    W.premultiply(new THREE.Matrix4().makeTranslation(-_o.x, -_o.y, -_o.z)).premultiply(_m).premultiply(t);
  }

  update(st, dt) {
    const L = st.kopf_lage || {};
    const k = Math.min(1, dt * 12);
    for (const n of Object.keys(this._lage)) this._lage[n] += ((L[n] || 0) - this._lage[n]) * k;
    const ant = st.antennen && st.antennen.length === 2 ? st.antennen : [-0.1745, 0.1745];
    for (let i = 0; i < 2; i++) this._ant[i] += (ant[i] - this._ant[i]) * k;
    this.root.position.set(st.x, st.stand_z || 0, -st.y);          // Tischroboter: auf der Standfläche (seit 0.38.10)
    this.root.rotation.y = (st.yaw || 0) - (L.koerper || 0);       // der Sockel dreht sich nicht mit
    // Unerreichbare Lage (sollte der Server schon verhindern): nicht den Kopf in den Körper zeichnen, sondern die
    // zuletzt gültige Lage behalten – nur die Körperdrehung folgt
    if (this.rechne(this._lage, this._ant)) Object.assign(this._gueltig, this._lage);
    else {
      Object.assign(this._lage, this._gueltig, { koerper: this._lage.koerper });
      this.rechne(this._lage, this._ant);
    }
  }
}
