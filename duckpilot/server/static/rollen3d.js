// Zubehör der Microduck in der 3D-Ansicht (seit 0.47): Rollen an den Füßen, die Strecke des Arena-Rennens und die
// Geisterente (die beste Fahrt als heller Punkt). Eigene Datei, damit duck3d.js klein bleibt: Die Rollen folgen den
// Füßen jedes Bild (Fußpunkte des Originalmodells oder die Knöchel der einfachen Ente) und drehen sich mit der Fahrt.
import * as THREE from './vendor/three.module.min.js';

const RAD_R = 0.011;            // m – Radius der Rollen
const HOEHE = 2 * RAD_R + 0.006;  // m – so weit heben die Rollen sie an (Rad plus Schiene)

// Eine Rolle wie Pollens Rollschuh: dunkle Schiene unter dem Fuß, zwei schwarze Räder mit hellen Naben – breiter als der
// Fuß, damit man sie sieht (0.49.1, Maintainer: „Rollen dran – sehe sie aber nicht im Simulator“)
function rolle() {
  const g = new THREE.Group();
  const schiene = new THREE.Mesh(new THREE.BoxGeometry(0.066, 0.006, 0.032),
    new THREE.MeshStandardMaterial({ color: 0x2a6fdb, roughness: 0.5 }));
  schiene.position.y = 2 * RAD_R + 0.003;
  g.add(schiene);
  const gummi = new THREE.MeshStandardMaterial({ color: 0x1c1c1e, roughness: 0.7 });
  const nabe = new THREE.MeshStandardMaterial({ color: 0xf2b134, roughness: 0.4 });
  g.raeder = [-0.022, 0.022].map((x) => {
    const r = new THREE.Group();
    r.add(new THREE.Mesh(new THREE.CylinderGeometry(RAD_R, RAD_R, 0.03, 20).rotateX(Math.PI / 2), gummi));
    r.add(new THREE.Mesh(new THREE.CylinderGeometry(RAD_R * 0.45, RAD_R * 0.45, 0.032, 12).rotateX(Math.PI / 2), nabe));
    r.position.set(x, RAD_R, 0);
    g.add(r);
    return r;
  });
  g.traverse((o) => { o.castShadow = true; o.raycast = () => {}; });
  return g;
}

function fuesse(duck) {
  if (duck?.sites?.left_foot) return [duck.sites.left_foot, duck.sites.right_foot].filter(Boolean);
  return (duck?.legs || []).map((l) => l.ankle);
}

// Ein Tor zum Durchfahren (0.49.1, Maintainer: „sehen wie Zäune aus“): ein Bogen statt Pfosten mit Querlatte, dazu
// Pfeile am Boden in Fahrtrichtung (lokales +x) und eine Linie zwischen den Pfosten. Start/Ziel rot, sonst blau.
function torBogen(t) {
  const g = new THREE.Group();
  const farbe = t.nr === 0 ? 0xe5484d : 0x3e8ed0;
  const m = new THREE.MeshStandardMaterial({ color: farbe, roughness: 0.5 });
  const r = t.breite / 2;
  const bogen = new THREE.Mesh(new THREE.TorusGeometry(r, 0.007, 10, 32, Math.PI).rotateY(Math.PI / 2), m);
  g.add(bogen);
  const boden = new THREE.MeshBasicMaterial({ color: farbe, transparent: true, opacity: 0.7 });
  const linie = new THREE.Mesh(new THREE.PlaneGeometry(0.012, t.breite).rotateX(-Math.PI / 2), boden);
  linie.position.y = 0.002;
  g.add(linie);
  for (const dx of [-0.09, 0.06]) {            // zwei Pfeile „>“: hier hindurch
    for (const s of [-1, 1]) {
      const strich = new THREE.Mesh(new THREE.PlaneGeometry(0.06, 0.012).rotateX(-Math.PI / 2), boden);
      strich.rotation.y = s * 0.7;
      strich.position.set(dx - 0.012, 0.002, s * 0.018);
      g.add(strich);
    }
  }
  g.position.set(t.x, 0, -t.y);
  g.rotation.y = t.richtung;
  g.traverse((o) => { o.raycast = () => {}; });
  return g;
}

export function initRollen3D(scene) {
  if (!scene || !scene.scene) return { strecke() {}, geist() {}, naechstes() {} };
  const paar = [rolle(), rolle()];
  let an = false, tempo = 0, yaw = 0, drehung = 0;
  let tore = null, torObjekte = [], geistWeg = null, geistStart = 0;
  const geistPunkt = new THREE.Mesh(new THREE.SphereGeometry(0.03, 16, 12),
    new THREE.MeshBasicMaterial({ color: 0xbfe3ff, transparent: true, opacity: 0.55 }));
  geistPunkt.visible = false;
  scene.scene.add(geistPunkt);
  const p = new THREE.Vector3();

  window.addEventListener('knowlin:state', (ev) => {
    const st = ev.detail || {};
    const z = st.zubehoer || {};
    const jetzt = !!z.rollen;
    if (jetzt !== an) { an = jetzt; for (const r of paar) { if (an) scene.scene.add(r); else scene.scene.remove(r); } }
    tempo = (st.twist && st.twist.vx) || 0;
    yaw = st.yaw || 0;
  });

  // Erst nach dem Bewegen der Gelenke und vor dem Zeichnen setzen (Scene.onBeforeRender), sonst hinken die Rollen
  // den Füßen ein Bild hinterher – bei langsamen Rechnern sichtbar.
  let zuletzt = performance.now();
  const vorher = scene.scene.onBeforeRender;
  scene.scene.onBeforeRender = (...args) => {
    vorher?.apply(scene.scene, args);
    const t = performance.now(), dt = Math.min(0.1, (t - zuletzt) / 1000);
    zuletzt = t;
    if (scene.duck?.root) scene.duck.root.position.y = an ? HOEHE : 0;   // auf den Rollen steht sie höher
    if (an) {
      drehung += (tempo / RAD_R) * dt;
      const fs = fuesse(scene.duck);
      paar.forEach((r, i) => {
        const f = fs[i];
        r.visible = !!f;
        if (!f) return;
        f.getWorldPosition(p);
        r.position.set(p.x, 0, p.z);
        r.rotation.y = yaw;
        for (const rad of r.raeder) rad.rotation.z = -drehung;
        r.updateMatrixWorld(true);
      });
    }
    if (geistWeg && geistWeg.length > 1) {
      const s = (t - geistStart) / 1000;
      let i = geistWeg.findIndex((w) => w[0] > s);
      if (i < 0) { geistPunkt.visible = false; return; }
      i = Math.max(1, i);
      const [t0, x0, y0] = geistWeg[i - 1], [t1, x1, y1] = geistWeg[i];
      const k = t1 > t0 ? (s - t0) / (t1 - t0) : 0;
      geistPunkt.position.set(x0 + (x1 - x0) * k, 0.05, -(y0 + (y1 - y0) * k));
      geistPunkt.visible = true;
      geistPunkt.updateMatrixWorld(true);
    }
  };

  return {
    // Tore zeigen oder wegräumen (null)
    strecke(neu) {
      for (const o of torObjekte) scene.scene.remove(o);
      tore = neu;
      torObjekte = (neu || []).map(torBogen);
      for (const o of torObjekte) scene.scene.add(o);
    },
    // Die Geisterente startet mit der Uhr (Weg: [[t, x, y], …]); null blendet sie aus
    geist(weg) {
      geistWeg = weg && weg.length > 1 ? weg : null;
      geistStart = performance.now();
      geistPunkt.visible = false;
    },
    // Das nächste Tor hervorheben
    naechstes(nr) {
      torObjekte.forEach((o, i) => { o.scale.setScalar(i === nr ? 1.25 : 1); });
      return tore ? tore[nr] : null;
    },
  };
}
