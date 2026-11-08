// Die einfache Ente (Ersatz, solange Pollens Modell fehlt, und in der öffentlichen Fassung) – eigener Entwurf, keine
// Daten aus Pollens CAD. Gleiche Schnittstelle wie RealDuck: root, body, headRoll, beakTip, update(st, dt).
// Koordinaten wie in duck3d.js: Simulator x = vorn, y = links, z = oben → three.js X = x, Y = z, Z = -y.
import * as THREE from './vendor/three.module.min.js';
import { applyBodyQuat } from './duckmodel.js';
import { allesVerschmelzen, FARBEN, rundKasten, stoff, teil } from './formen3d.js';

const L_THIGH = 0.055, L_SHIN = 0.06, FOOT_H = 0.012;
const STAND_LEG = [0, -0.0873, -0.4579, -0.0049, 0.4530], HOME_NECK = 0.3491, HOME_HEAD = 0.3491;

export class Duck {
  // Eigener Entwurf als kleiner Roboter (seit 0.38.18, vorher eine Comic-Ente): weiße Schale, Servos in Dunkelgrau,
  // Kopf mit Visier, zwei Kameraaugen und orangem Unterkiefer, orange Füße mit Gummisohle. Nach Fotos gezeichnet,
  // ohne CAD-Daten. art 'open_duck': Open Duck Mini – gedruckt, breiter Trapezkopf, langer Hals, gelbe Füße, Antennen.
  constructor(art = 'microduck') {
    const od = art === 'open_duck';
    const F = od
      ? { schale: 0xf0eee8, schaleArt: 'plastic', visier: 0xf0eee8, fuss: 0xf2b632, akzent: 0xf0962c }
      : { schale: 0xf4f2ec, schaleArt: 'shell', visier: 0xd6d1c8, fuss: 0xf07a2c, akzent: 0xf07a2c };
    const schale = stoff(F.schale, F.schaleArt).clone(), servo = stoff(0x2c2d30, 'servo'), kappe = stoff(0xa9abae, 'plastic');
    const sohle = stoff(0x343434, 'rubber'), akzent = stoff(F.akzent, 'soft'), glas = stoff(0x101012, 'glass');
    this.root = new THREE.Group();
    this.body = new THREE.Group();
    this.root.add(this.body);
    const gelenk = (g, r, breit, x = 0, y = 0) => teil(g, new THREE.CylinderGeometry(r, r, breit, 20), kappe, x, y, 0, Math.PI / 2);

    // Rumpf: Schale und darunter der Gürtel der Hüftservos
    if (od) {
      teil(this.body, rundKasten(0.064, 0.084, 0.066, 0.009), schale, 0, 0.012, 0);
      for (const s of [1, -1]) teil(this.body, rundKasten(0.022, 0.016, 0.01, 0.003), akzent, 0, -0.026, 0.036 * s);
    } else {
      teil(this.body, rundKasten(0.07, 0.062, 0.072, 0.018), schale, 0, 0.004, 0);
    }
    teil(this.body, rundKasten(0.05, 0.016, 0.076, 0.005), servo, 0, -0.028, 0);

    // Hals: ein Servo mit Gelenkkappen
    this.neck = new THREE.Group();
    this.neck.position.set(0.018, od ? 0.05 : 0.034, 0);
    this.body.add(this.neck);
    const hals = od ? 0.085 : 0.06;
    teil(this.neck, rundKasten(0.028, hals, 0.032, 0.006), servo, 0, hals / 2, 0);
    gelenk(this.neck, 0.0085, 0.032);
    this.headYaw = new THREE.Group();
    this.headYaw.position.y = hals + 0.002;
    this.neck.add(this.headYaw);
    this.headPitch = new THREE.Group();
    this.headYaw.add(this.headPitch);
    this.headRoll = new THREE.Group();
    this.headPitch.add(this.headRoll);
    gelenk(this.headRoll, 0.0085, 0.032);

    this.jaw = new THREE.Group();
    if (od) {
      // Trapezkopf: oben schmaler, vorn zwei runde Augen, oben die Antennen
      const kopf = rundKasten(0.072, 0.044, 0.13, 0.008, 3, (fx, fy) => [1, 1 - 0.2 * Math.max(0, fy)]);
      teil(this.headRoll, kopf, schale, 0.012, 0.03, 0);
      for (const s of [1, -1]) {
        teil(this.headRoll, new THREE.SphereGeometry(0.0085, 20, 12), glas, 0.0485, 0.032, 0.03 * s, 0, 0, 0).scale.set(0.3, 1, 1);
      }
      this.antennen = [1, -1].map((s) => {
        const a = new THREE.Group();
        a.position.set(-0.012, 0.05, 0.04 * s);
        a.rotation.x = -0.32 * s;
        teil(a, new THREE.CylinderGeometry(0.0011, 0.0013, 0.075, 6), servo, 0, 0.0375, 0);
        teil(a, new THREE.SphereGeometry(0.0028, 10, 8), servo, 0, 0.075, 0);
        this.headRoll.add(a);
        return a;
      });
      this.jaw.position.set(0.012, 0.008, 0);
      this.beakTip = new THREE.Object3D();
      this.beakTip.position.set(0.06, 0.02, 0);
      this.povNode = new THREE.Object3D();            // Kamera vor den Augen – nicht im Kopf (Fund 7.11.)
      this.povNode.position.set(0.056, 0.032, 0);
    } else {
      // Kopf: lang nach vorn, oben zur Stirn hin flacher; vorn ein Visier mit zwei Kameraaugen
      const kopf = rundKasten(0.115, 0.05, 0.088, 0.016, 4,
        (fx, fy) => [1 - 0.3 * Math.max(0, fx) * Math.max(0, fy), 1 - 0.1 * Math.max(0, fx)]);
      teil(this.headRoll, kopf, schale, 0.022, 0.026, 0);
      teil(this.headRoll, rundKasten(0.03, 0.03, 0.07, 0.011), stoff(F.visier, 'plastic'), 0.069, 0.021, 0);
      const ring = stoff(0xf6b23c, 'servo');
      for (const s of [1, -1]) {
        teil(this.headRoll, new THREE.TorusGeometry(0.0085, 0.0022, 10, 28), ring, 0.0845, 0.023, 0.016 * s, 0, Math.PI / 2, 0);
        teil(this.headRoll, new THREE.SphereGeometry(0.0075, 20, 12), glas, 0.0838, 0.023, 0.016 * s).scale.set(0.35, 1, 1);
      }
      // Unterkiefer: oranger Schnabel, öffnet um die Hinterkante
      this.jaw.position.set(-0.025, 0.002, 0);
      teil(this.jaw, rundKasten(0.122, 0.013, 0.082, 0.006, 3, (fx) => [1, 1 - 0.16 * Math.max(0, fx)]), akzent, 0.061, -0.004, 0);
      this.beakTip = new THREE.Object3D();
      this.beakTip.position.set(0.097, 0.0, 0);
      this.povNode = new THREE.Object3D();            // Kamera vor dem Visier – nicht im Kopf (Fund 7.11.)
      this.povNode.position.set(0.092, 0.023, 0);
    }
    this.headRoll.add(this.jaw, this.beakTip, this.povNode);

    // Beine: Hüftservo, weiße Oberschenkelschale, dunkles Schienbein, Gelenkkappen, Fuß mit Gummisohle
    this.legs = [1, -1].map((side) => {
      const hip = new THREE.Group();
      hip.position.set(0.0, -0.035, (od ? 0.034 : 0.03) * side);
      this.body.add(hip);
      teil(hip, rundKasten(0.03, 0.022, 0.026, 0.005), servo, 0, -0.004, 0);
      teil(hip, rundKasten(0.028, L_THIGH + 0.004, 0.022, 0.009), schale, 0, -L_THIGH / 2, 0);
      const knee = new THREE.Group();
      knee.position.y = -L_THIGH;
      hip.add(knee);
      gelenk(knee, 0.0088, 0.027);
      teil(knee, rundKasten(0.021, L_SHIN, 0.019, 0.006), servo, 0, -L_SHIN / 2, 0);
      const ankle = new THREE.Group();
      ankle.position.y = -L_SHIN;
      knee.add(ankle);
      gelenk(ankle, 0.0075, 0.023);
      teil(ankle, rundKasten(0.056, FOOT_H * 0.72, 0.034, 0.005), stoff(F.fuss, 'soft'), 0.012, -FOOT_H * 0.36, 0);
      teil(ankle, rundKasten(0.056, FOOT_H * 0.32, 0.034, 0.0028, 2), sohle, 0.012, -FOOT_H * 0.84, 0);
      return { hip, knee, ankle };
    });
    allesVerschmelzen(this.root);
    this.fallAngle = 0;
    this.schale = od ? null : { m: schale, original: schale.color.clone() };
  }

  // Farbe der Schale wie bei der echten Microduck (Cream, Graphite, Lavender, Sky)
  setFarbe(name) {
    if (!this.schale) return;
    const f = FARBEN[name];
    if (f == null) this.schale.m.color.copy(this.schale.original); else this.schale.m.color.setHex(f);
  }

  // st = DuckState vom Server
  update(st, dt) {
    const j = st.display_joints && st.display_joints.length === 15 ? st.display_joints : null;
    const [ny, nx] = [st.y, st.x];
    this.root.position.set(nx, 0, -ny);
    this.root.rotation.y = st.yaw;

    let stanceHeight = 0.05;
    if (j) {
      // display_joints sind MJCF-Winkel des echten Roboters – grob auf diese Ersatz-Ente umrechnen
      const legs = [j.slice(0, 5), j.slice(10, 15).map((v) => -v)];
      legs.forEach((lj, i) => {
        const dh = lj[2] - STAND_LEG[2], dk = lj[3] - STAND_LEG[3], da = lj[4] - STAND_LEG[4];
        const hy = lj[0], hr = lj[1] - STAND_LEG[1];
        const hp = -0.45 + 1.6 * dh - 0.55 * dk, kn = 0.9 + 1.43 * dk, an = -0.45 + 1.3 * da - 0.3 * dk;
        const leg = this.legs[i];
        leg.hip.rotation.set(hr * (i === 0 ? 1 : -1), hy, -hp, 'YXZ');
        leg.knee.rotation.z = -kn;
        leg.ankle.rotation.z = -an;
        const h = L_THIGH * Math.cos(hp) + L_SHIN * Math.cos(hp + kn) + FOOT_H;
        stanceHeight = Math.max(stanceHeight, h);
      });
    }
    const pose = st.pose || { z: 0, roll: 0, pitch: 0 };
    // Rumpf: Hüfthöhe aus der Standbeinkinematik + Hüftabstand
    let y = stanceHeight + 0.035 + pose.z;
    let pitch = pose.pitch, roll = pose.roll;
    if (st.skill === 'roulade') {
      const p = st.skill_progress || 0;
      pitch = p * Math.PI * 2;
      y += Math.sin(p * Math.PI) * 0.04;
    }
    if (st.skill === 'ground_pick') {
      pitch += Math.sin(Math.PI * Math.min(1, (st.skill_progress || 0) * 1.15)) * 0.35;
    }
    if (st.body && st.body.length === 3) {
      // Physik-Simulator: Lage des Rumpfs aus MuJoCo (Höhe grob auf diese Ersatz-Ente umgerechnet)
      this.fallAngle = 0;
      this.body.position.y = Math.max(0.03, st.body[0] - 0.12 + y);
      if (!applyBodyQuat(this.body, st)) this.body.rotation.set(st.body[1], 0, -st.body[2], 'ZYX');
    } else {
      const targetFall = st.fallen ? (st.fall_side || 1) * 1.35 : 0;
      this.fallAngle += (targetFall - this.fallAngle) * Math.min(1, dt * (st.fallen ? 9 : 3));
      if (Math.abs(this.fallAngle) > 0.05) y = Math.max(0.055 * Math.abs(Math.sin(this.fallAngle)), y * Math.cos(this.fallAngle));
      this.body.position.y = y;
      this.body.rotation.set(roll + this.fallAngle, 0, -pitch, 'XYZ');
    }

    if (j) {
      this.neck.rotation.z = (j[5] - HOME_NECK) * 0.8;
      this.headYaw.rotation.y = j[7];
      this.headPitch.rotation.z = -(j[6] - HOME_HEAD);
      this.headRoll.rotation.x = j[8];
      this.jaw.rotation.z = -Math.max(0, Math.min(1, j[9])) * 0.55;
    }
  }
}
