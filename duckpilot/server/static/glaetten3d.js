// Ruhiges Bild trotz holprigem Zustand (seit 0.38.52, Maintainer: „Der Controller-Modus ruckelt stark bei Bewegung bzw.
// zappelt“). Zwei Ursachen, zwei Filter:
// 1. Lage der Figur: Der Zustand kommt mit 20 Hz, übers WLAN aber unregelmäßig – die Figur springt. `Lage` gleitet
//    in kurzer Zeit zum neuesten Wert (Zeitkonstante, unabhängig von der Bildrate); große Sprünge (Zurücksetzen,
//    Platz wechseln) übernimmt sie sofort.
// 2. Entenblick: Die Kopfkamera wackelt mit jedem Schritt. `Stabilisator` glättet Ort und Blickrichtung und hält den
//    Horizont gerade – wie eine Kamera mit Bildstabilisierung. Nur fürs Bild; was die Ente „sieht“, ändert sich nicht.
import * as THREE from './vendor/three.module.min.js';

const anteil = (dt, tau) => 1 - Math.exp(-Math.max(0, dt) / tau);
const winkelDiff = (a, b) => Math.atan2(Math.sin(a - b), Math.cos(a - b));

export class Lage {
  constructor(tau = 0.07, sprung = 0.35) {
    this.tau = tau;
    this.sprung = sprung;          // m: weiter weg = sofort dort (kein Gleiten durchs Zimmer)
    this.x = null; this.y = 0; this.yaw = 0;
  }

  // Gibt eine Kopie des Zustands mit geglätteter Lage zurück (das Original bleibt unverändert)
  glaetten(st, dt) {
    if (st.x == null || st.y == null) return st;
    const yaw = st.yaw || 0;
    if (this.x === null || Math.hypot(st.x - this.x, st.y - this.y) > this.sprung) {
      this.x = st.x; this.y = st.y; this.yaw = yaw;
    } else {
      const k = anteil(dt, this.tau);
      this.x += (st.x - this.x) * k;
      this.y += (st.y - this.y) * k;
      this.yaw += winkelDiff(yaw, this.yaw) * k;
    }
    return { ...st, x: this.x, y: this.y, yaw: this.yaw };
  }
}

export class Stabilisator {
  constructor(tauOrt = 0.1, tauBlick = 0.16) {
    this.tauOrt = tauOrt;
    this.tauBlick = tauBlick;
    this.ort = null;
    this.blick = new THREE.Vector3();
  }

  // Setzt `cam` an den geglätteten Ort, Blick geglättet, Horizont gerade (oben = Welt-oben)
  fuehren(cam, pos, dir, dt) {
    if (!this.ort || this.ort.distanceTo(pos) > 0.3) {
      this.ort = pos.clone();
      this.blick.copy(dir).normalize();
    } else {
      this.ort.lerp(pos, anteil(dt, this.tauOrt));
      this.blick.lerp(dir, anteil(dt, this.tauBlick)).normalize();
    }
    cam.position.copy(this.ort);
    cam.up.set(0, 1, 0);
    cam.lookAt(this.ort.clone().add(this.blick));
  }
}
