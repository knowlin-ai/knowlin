// Dinge im Zimmer, die mehr als eine Grundform brauchen (seit 0.38.25).
//
// Socke – Hinweise „sieht nicht mal wie eine Socke aus“ (vorher ein halber Ring) und zum ersten runden Entwurf
// „es soll nach Socke aussehen“: flach liegender Stoff im typischen Umriss – Schaft, Ferse im rechten Winkel, breiterer
// Fuß mit runder Spitze –, abgesetzte Ferse und Spitze in der Ringelfarbe, zwei Ringel unter dem Bündchen. So erkennt man
// sie auf den ersten Blick wie das Socken-Zeichen. Bündchen-Mitte bei (0, 0, 0), Schaft nach unten (−y), Fuß nach vorn (+x).
import * as THREE from './vendor/three.module.min.js';

const RINGEL = 0x6f8fbf;
const DICKE = 0.0045;        // m – Stoff, flachgelegt
const RAND = 0.0018;         // m – weiche Kante

// Umriss (Meter bei r = 0,035): oben das Bündchen, links die Ferse, rechts Spann und Spitze
function umriss(s) {
  const p = (x, y) => [x * s, y * s];
  const f = new THREE.Shape();
  f.moveTo(...p(-0.015, 0));
  f.lineTo(...p(0.015, 0));
  f.lineTo(...p(0.015, -0.036));
  f.quadraticCurveTo(...p(0.016, -0.046), ...p(0.028, -0.047));          // Spann
  f.lineTo(...p(0.05, -0.048));
  f.quadraticCurveTo(...p(0.066, -0.049), ...p(0.066, -0.06));           // Spitze
  f.quadraticCurveTo(...p(0.066, -0.072), ...p(0.05, -0.072));
  f.lineTo(...p(0.002, -0.072));
  f.quadraticCurveTo(...p(-0.016, -0.072), ...p(-0.016, -0.054));        // Ferse
  f.lineTo(...p(-0.015, 0));
  return f;
}

function ferse(s) {
  const p = (x, y) => [x * s, y * s];
  const f = new THREE.Shape();
  f.moveTo(...p(-0.0162, -0.047));
  f.quadraticCurveTo(...p(-0.003, -0.05), ...p(0.006, -0.0722));
  f.lineTo(...p(0.002, -0.0722));
  f.quadraticCurveTo(...p(-0.0162, -0.0722), ...p(-0.0162, -0.054));
  f.lineTo(...p(-0.0162, -0.047));
  return f;
}

function spitze(s) {
  const p = (x, y) => [x * s, y * s];
  const f = new THREE.Shape();
  f.moveTo(...p(0.05, -0.0478));
  f.quadraticCurveTo(...p(0.0662, -0.0488), ...p(0.0662, -0.06));
  f.quadraticCurveTo(...p(0.0662, -0.0722), ...p(0.05, -0.0722));
  f.quadraticCurveTo(...p(0.054, -0.06), ...p(0.05, -0.0478));
  return f;
}

function platte(shape, tiefe, rand, stoff) {
  const g = new THREE.ExtrudeGeometry(shape, {
    depth: tiefe, bevelEnabled: rand > 0, bevelThickness: rand, bevelSize: rand * 0.8, bevelSegments: 2, curveSegments: 10,
  });
  g.translate(0, 0, -tiefe / 2);
  return new THREE.Mesh(g, stoff);
}

export function sockenForm(item, stoff) {
  const s = item.r / 0.035;
  const t = DICKE * s;
  const ringel = new THREE.MeshStandardMaterial({ color: RINGEL, roughness: 0.75 });
  const form = new THREE.Group();
  form.add(platte(umriss(s), t, RAND * s, stoff));
  const aussen = t + 2 * RAND * s + 0.0006;                  // Flicken liegen auf beiden Seiten auf
  form.add(platte(ferse(s), aussen, 0, ringel), platte(spitze(s), aussen, 0, ringel));
  for (const y of [-0.011, -0.018]) {                        // zwei Ringel unter dem Bündchen
    const band = new THREE.Mesh(new THREE.BoxGeometry(0.0312 * s, 0.003 * s, aussen), ringel);
    band.position.set(0, y * s, 0);
    form.add(band);
  }
  const mesh = new THREE.Group();
  mesh.add(form);
  mesh.userData.form = form;
  mesh.userData.dicke = t / 2 + RAND * s;
  sockeLegen(mesh, item);
  return mesh;
}

// Am Boden: flach hingelegt, Mitte auf dem Platz des Dings, jede Socke etwas anders gedreht
export function sockeLegen(mesh, item) {
  const form = mesh.userData.form, s = item.r / 0.035;
  form.rotation.set(-Math.PI / 2, 0, 0);
  form.position.set(-0.025 * s, mesh.userData.dicke, -0.036 * s);
  let h = 0;
  for (const c of String(item.name || '')) h = (h * 31 + c.charCodeAt(0)) % 360;
  mesh.rotation.set(0, (h / 180) * Math.PI, 0);
}

// Im Schnabel: am Bündchen gehalten, hängt senkrecht, Fuß zeigt nach vorn
export function sockeHaengen(mesh) {
  mesh.userData.form.rotation.set(0, 0, 0);
  mesh.userData.form.position.set(0, 0, 0);
}
