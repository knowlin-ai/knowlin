// Reachy Mini als einfache Verkörperung für die 3D-Ansicht (seit 0.38.1). Gleiche Schnittstelle wie die Ente in duck3d.js:
// root, body, headRoll, beakTip, update(st, dt). Gezeichnet nach Pollens Fotos, nicht aus dem CAD-Modell:
// fester Fuß, drehbarer Körper, Kopf auf der Stewart-Plattform (hoch/runter, nicken, neigen, drehen), zwei Antennen.
// Koordinaten wie in duck3d.js: Simulator x = vorn, y = links, z = oben → three.js X = x, Y = z, Z = -y.
import * as THREE from './vendor/three.module.min.js';
import { allesVerschmelzen, rundKasten, stoff, teil } from './formen3d.js';

const F = {
  // Farben wie Pollens Gerät: weiße Schalen, Brillenaugen, metallene Stangen (seit 0.38.18 ohne dunkles Visier)
  hell: 0xf4f3f0, fuss: 0xd2d2d0, dunkel: 0x1e1f21, glas: 0x2c3035, stange: 0x9aa0a6,
};
const KOPF_Y = 0.192;      // Mitte der Plattform über dem Boden (wach)


export class Reachy {
  constructor() {
    this.root = new THREE.Group();
    this.istReachy = true;
    const schale = stoff(F.hell, 'shell'), dunkel = stoff(F.dunkel, 'servo'), metall = stoff(F.stange, 'metal');
    // Fuß: flacher heller Teller, steht fest
    this.fuss = new THREE.Group();
    this.root.add(this.fuss);
    teil(this.fuss, new THREE.CylinderGeometry(0.07, 0.072, 0.008, 48), stoff(F.fuss, 'plastic'), 0, 0.004, 0);

    // Körper: eiförmige Schale, oben offen (dunkler Boden der Öffnung); dreht sich um die Hochachse (body_yaw)
    this.body = new THREE.Group();
    this.root.add(this.body);
    const umriss = [[0.0, 0.008], [0.056, 0.008], [0.066, 0.02], [0.073, 0.05], [0.072, 0.085], [0.065, 0.112],
      [0.058, 0.13], [0.054, 0.134], [0.05, 0.13]].map(([r, y]) => new THREE.Vector2(r, 0.008 + (y - 0.008) * 1.2));
    teil(this.body, new THREE.LatheGeometry(umriss, 56), schale);
    teil(this.body, new THREE.CylinderGeometry(0.05, 0.05, 0.004, 40), stoff(F.dunkel, 'dark'), 0, 0.15, 0);
    // Stewart-Plattform: sechs Stangen zwischen Körper und Kopf, werden jedes Bild neu ausgerichtet
    this.unten = [];
    this.oben = [];
    for (let i = 0; i < 6; i++) {
      const a = (i * Math.PI) / 3 + (i % 2 ? 0.25 : -0.25);
      this.unten.push(new THREE.Vector3(0.04 * Math.cos(a), 0.152, 0.04 * Math.sin(a)));
      const c = (i * Math.PI) / 3 + (i % 2 ? -0.35 : 0.35);
      this.oben.push(new THREE.Vector3(0.03 * Math.cos(c), -0.012, 0.03 * Math.sin(c)));
    }
    const stangeGeo = new THREE.CylinderGeometry(0.0022, 0.0022, 1, 8);
    stangeGeo.translate(0, 0.5, 0);
    this.stangen = this.unten.map(() => {
      const st = new THREE.Mesh(stangeGeo, metall);
      st.castShadow = true;
      st.userData.einzeln = true;                     // bewegt sich jedes Bild einzeln – nicht zusammenfassen
      this.body.add(st);
      return st;
    });

    // Kopf: Gier, Nicken, Neigen nacheinander, Höhe über kopfHoch
    this.kopfHoch = new THREE.Group();
    this.kopfHoch.position.y = KOPF_Y;
    this.body.add(this.kopfHoch);
    this.headYaw = new THREE.Group();
    this.kopfHoch.add(this.headYaw);
    this.headPitch = new THREE.Group();
    this.headYaw.add(this.headPitch);
    this.headRoll = new THREE.Group();
    this.headPitch.add(this.headRoll);
    // Kopf: weich gerundeter Quader, vorn zwei runde Kameraaugen wie eine Brille (Gläser, Fassung, Steg)
    teil(this.headRoll, rundKasten(0.076, 0.068, 0.118, 0.03, 5), schale, 0, 0.035, 0);
    const glas = stoff(F.glas, 'glass'), fassung = stoff(F.dunkel, 'servo');
    this.augen = [1, -1].map((seite) => {
      const z = 0.024 * seite;
      const auge = teil(this.headRoll, new THREE.SphereGeometry(0.0145, 28, 14), glas, 0.0372, 0.034, z);
      auge.scale.set(0.22, 1, 1);
      teil(this.headRoll, new THREE.TorusGeometry(0.0148, 0.0019, 10, 36), fassung, 0.0382, 0.034, z, 0, Math.PI / 2, 0);
      return auge;
    });
    teil(this.headRoll, new THREE.CylinderGeometry(0.0013, 0.0013, 0.02, 8), fassung, 0.0392, 0.0355, 0, Math.PI / 2, 0, 0);
    // Antennen: drehen in der Querebene, 0 = senkrecht; Pollen: [rechts, links], rechts negativ = nach außen
    this.antennen = [1, -1].map((seite) => {          // three.js +Z = rechts
      const fuss = new THREE.Group();
      fuss.position.set(-0.012, 0.068, 0.03 * seite);
      this.headRoll.add(fuss);
      teil(fuss, new THREE.CylinderGeometry(0.0026, 0.0026, 0.018, 10), dunkel, 0, 0.012, 0);   // Feder
      teil(fuss, new THREE.CylinderGeometry(0.0012, 0.0015, 0.09, 6), dunkel, 0, 0.065, 0);
      teil(fuss, new THREE.SphereGeometry(0.0034, 12, 8), dunkel, 0, 0.11, 0);
      return fuss;
    });
    // Blickpunkt vor dem Gesicht (für Dinge und die Kopfkamera wie beim Schnabel der Ente)
    this.beakTip = new THREE.Object3D();
    this.beakTip.position.set(0.075, 0.03, 0);
    this.headRoll.add(this.beakTip);
    // Kamera zwischen den Augen, Blick nach vorn (+x) – für den Entenblick
    this.povNode = new THREE.Object3D();
    this.povNode.position.set(0.06, 0.034, 0);
    this.headRoll.add(this.povNode);
    this._lage = { z: 0, roll: 0, pitch: 0, yaw: 0 };
    this._ant = [-0.1745, 0.1745];
    this._p = new THREE.Vector3();
    this._q = new THREE.Vector3();
    allesVerschmelzen(this.root);
  }

  update(st, dt) {
    this.root.position.set(st.x, st.stand_z || 0, -st.y);          // auf dem Couchtisch (seit 0.38.10)
    this.body.rotation.y = st.yaw || 0;
    const k = Math.min(1, dt * 12);
    const ziel = st.kopf_lage || {};
    for (const n of ['z', 'roll', 'pitch', 'yaw']) this._lage[n] += ((ziel[n] || 0) - this._lage[n]) * k;
    const ant = st.antennen && st.antennen.length === 2 ? st.antennen : [-0.1745, 0.1745];
    for (let i = 0; i < 2; i++) this._ant[i] += (ant[i] - this._ant[i]) * k;

    const L = this._lage;
    const schlaf = st.sitting || !st.powered ? -0.03 : 0;
    this.kopfHoch.position.y = KOPF_Y + L.z + schlaf;
    this.headYaw.rotation.y = L.yaw;
    this.headPitch.rotation.z = -L.pitch;
    this.headRoll.rotation.x = L.roll;
    // rechts (Index 0, +Z) kippt mit negativem Wert nach außen, links (−Z) mit positivem – beides ist −rotation.x
    this.antennen[0].rotation.x = -this._ant[0];
    this.antennen[1].rotation.x = -this._ant[1];

    // Stangen von den Körperpunkten zu den Kopfpunkten ausrichten (im Körper-Rahmen)
    this.headRoll.updateWorldMatrix(true, false);
    this.body.updateWorldMatrix(true, false);
    const inv = this.body.matrixWorld.clone().invert();
    const oben = new THREE.Vector3(0, 1, 0);
    this.stangen.forEach((s, i) => {
      this._q.copy(this.oben[i]).applyMatrix4(this.headRoll.matrixWorld).applyMatrix4(inv);
      this._p.copy(this.unten[i]);
      const d = this._q.clone().sub(this._p);
      s.position.copy(this._p);
      s.scale.set(1, Math.max(0.001, d.length()), 1);
      s.quaternion.setFromUnitVectors(oben, d.normalize());
    });
  }
}
