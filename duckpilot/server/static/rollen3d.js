// Zubehör der Microduck in der 3D-Ansicht (seit 0.47): Rollen an den Füßen, die Strecke des Arena-Rennens und die
// Geisterente (die beste Fahrt als heller Punkt). Eigene Datei, damit duck3d.js klein bleibt: Die Rollen folgen den
// Füßen jedes Bild (Fußpunkte des Originalmodells oder die Knöchel der einfachen Ente) und drehen sich mit der Fahrt.
import * as THREE from './vendor/three.module.min.js';

const RAD_R = 0.009;            // m – Radius der Rollen
const UNTER_FUSS = 0.006;       // m – so weit unter dem Fußpunkt sitzt die Achse

function rolle() {
  const g = new THREE.Group();
  const schiene = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.006, 0.022),
    new THREE.MeshStandardMaterial({ color: 0x3a3f47, roughness: 0.6 }));
  schiene.position.y = RAD_R + 0.002;
  g.add(schiene);
  const gummi = new THREE.MeshStandardMaterial({ color: 0xf2b134, roughness: 0.45 });
  g.raeder = [-0.016, 0.016].map((x) => {
    const r = new THREE.Mesh(new THREE.CylinderGeometry(RAD_R, RAD_R, 0.02, 16).rotateX(Math.PI / 2), gummi);
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

function torBogen(t) {
  const g = new THREE.Group();
  const farbe = t.nr === 0 ? 0xe5484d : 0x3e8ed0;
  const m = new THREE.MeshStandardMaterial({ color: farbe, roughness: 0.5 });
  for (const s of [-1, 1]) {
    const p = new THREE.Mesh(new THREE.CylinderGeometry(0.008, 0.008, 0.16, 10), m);
    p.position.set(0, 0.08, s * t.breite / 2);
    g.add(p);
  }
  const fahne = new THREE.Mesh(new THREE.BoxGeometry(0.01, 0.03, t.breite), m);
  fahne.position.y = 0.16;
  g.add(fahne);
  const linie = new THREE.Mesh(new THREE.PlaneGeometry(0.02, t.breite).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({ color: farbe, transparent: true, opacity: 0.6 }));
  linie.position.y = 0.002;
  g.add(linie);
  g.position.set(t.x, 0, -t.y);
  g.rotation.y = t.richtung;
  g.traverse((o) => { o.raycast = () => {}; });
  return g;
}

export function initRollen3D(scene) {
  if (!scene || !scene.scene) return { strecke() {}, geist() {}, naechstes() {} };
  const paar = [rolle(), rolle()];
  let an = false, geduckt = false, tempo = 0, yaw = 0, drehung = 0;
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
    geduckt = !!z.geduckt;
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
    if (an) {
      drehung += (tempo / RAD_R) * dt;
      const fs = fuesse(scene.duck);
      paar.forEach((r, i) => {
        const f = fs[i];
        r.visible = !!f;
        if (!f) return;
        f.getWorldPosition(p);
        r.position.set(p.x, Math.max(0, p.y - UNTER_FUSS - RAD_R - (geduckt ? 0.002 : 0)), p.z);
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
