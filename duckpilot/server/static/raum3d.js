// Der Raum um die Verkörperung (seit 0.38.18): Dielenboden, Wände wie bei einem Puppenhaus (die zur Kamera
// zeigende Wand tritt bis auf die Fußleiste zurück), Teppich unter dem Couchtisch und ein ruhiger Verlauf als
// Hintergrund. Alles aus wenigen Flächen und einer gezeichneten Textur – keine Bilddateien, wenige Zeichenaufrufe.
import * as THREE from './vendor/three.module.min.js';

const DIELE_M = 0.12;                // Breite einer Diele
const KACHEL_M = DIELE_M * 8;        // so viel Boden zeigt eine Textur

let dielenTextur = null;
// Dielen in warmem Eichenton, gezeichnet: Fugen, versetzte Stöße, leichte Maserung. Einmal je Seite.
function dielen(renderer) {
  if (dielenTextur) return dielenTextur;
  const n = 1024, c = document.createElement('canvas');
  c.width = c.height = n;
  const g = c.getContext('2d');
  let saat = 5;
  const zufall = () => ((saat = (saat * 16807) % 2147483647) / 2147483647);
  const reihe = n / 8;
  for (let r = 0; r < 8; r++) {
    let x = -zufall() * n * 0.5;
    while (x < n) {
      const laenge = n * (0.45 + zufall() * 0.5);
      const ton = 0.93 + zufall() * 0.1;
      g.fillStyle = `rgb(${Math.round(116 * ton)},${Math.round(90 * ton)},${Math.round(66 * ton)})`;
      g.fillRect(x, r * reihe, laenge, reihe);
      // Maserung: feine, leicht gewellte Linien
      for (let m = 0; m < 14; m++) {
        const y0 = r * reihe + zufall() * reihe;
        g.strokeStyle = `rgba(${zufall() < 0.5 ? '60,40,24' : '170,130,90'},${0.03 + zufall() * 0.05})`;
        g.lineWidth = 1 + zufall() * 1.5;
        g.beginPath();
        g.moveTo(x, y0);
        for (let t = 0; t <= 1; t += 0.1) g.lineTo(x + laenge * t, y0 + Math.sin(t * 6 + m) * 2.5);
        g.stroke();
      }
      g.fillStyle = 'rgba(30,20,12,0.4)';
      g.fillRect(x, r * reihe, 2, reihe);                    // Stoß
      x += laenge;
    }
    g.fillStyle = 'rgba(30,20,12,0.45)';
    g.fillRect(0, r * reihe, n, 2);                          // Fuge
  }
  dielenTextur = new THREE.CanvasTexture(c);
  dielenTextur.colorSpace = THREE.SRGBColorSpace;
  dielenTextur.wrapS = dielenTextur.wrapT = THREE.RepeatWrapping;
  dielenTextur.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
  return dielenTextur;
}

// Boden: Dielen (w × d Meter), darüber ein sehr leises Raster zur Orientierung (10 cm)
export function boden(renderer, w, d) {
  const gruppe = new THREE.Group();
  const tex = dielen(renderer).clone();
  tex.needsUpdate = true;
  tex.repeat.set(w / KACHEL_M, d / KACHEL_M);
  const flaeche = new THREE.Mesh(new THREE.PlaneGeometry(w, d), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.72 }));
  flaeche.rotation.x = -Math.PI / 2;
  flaeche.receiveShadow = true;
  gruppe.add(flaeche);
  const raster = new THREE.GridHelper(Math.max(w, d), Math.round(Math.max(w, d) * 10), 0xffffff, 0xffffff);
  raster.position.y = 0.0006;
  raster.material.transparent = true;
  raster.material.opacity = 0.05;
  raster.material.depthWrite = false;
  gruppe.add(raster);
  return gruppe;
}

// Wände mit Fußleiste. Rückgabe: Gruppe und eine Funktion, die je Bild die Wände zwischen Kamera und Raum absenkt.
export function waende(breite, tiefe) {
  const gruppe = new THREE.Group();
  const hoch = 0.5, dick = 0.04, leiste = 0.035;
  const wandStoff = new THREE.MeshStandardMaterial({ color: 0x8c857c, roughness: 0.95 });
  const leistenStoff = new THREE.MeshStandardMaterial({ color: 0xd8d2c8, roughness: 0.6 });
  const hw = breite / 2, hd = tiefe / 2;
  const liste = [];
  // [x, z, Länge entlang, quer?, Normale nach außen]
  for (const [x, z, laenge, quer, nx, nz] of [[0, hd + dick / 2, breite + 2 * dick, false, 0, 1], [0, -hd - dick / 2, breite + 2 * dick, false, 0, -1],
    [hw + dick / 2, 0, tiefe, true, 1, 0], [-hw - dick / 2, 0, tiefe, true, -1, 0]]) {
    const sx = quer ? dick : laenge, sz = quer ? laenge : dick;
    const wand = new THREE.Mesh(new THREE.BoxGeometry(sx, hoch, sz), wandStoff);
    wand.position.set(x, hoch / 2, z);
    wand.castShadow = wand.receiveShadow = true;
    // ausgeblendete Wand nimmt keine Klicks an – sonst ließe sich durch sie nicht in den Raum tippen
    wand.raycast = function (strahl, treffer) { if (this.visible) THREE.Mesh.prototype.raycast.call(this, strahl, treffer); };
    // Seitliche Leisten enden vor der Ecke: Dort liegt die Leiste der Quer-Wand schon. Gleich hohe, überlappende
    // Oberkanten flimmerten (Z-Fighting, gemeldet nach 0.38.32: „die Ecken flimmern“).
    const fuss = new THREE.Mesh(new THREE.BoxGeometry(sx + (quer ? 0.012 : 0), leiste, quer ? sz - 0.026 : sz + 0.012), leistenStoff);
    fuss.position.set(x - nx * 0.006, leiste / 2, z - nz * 0.006);
    fuss.receiveShadow = true;
    gruppe.add(wand, fuss);
    liste.push({ wand, n: new THREE.Vector2(nx, nz), p: new THREE.Vector2(x, z) });
  }
  const v = new THREE.Vector2();
  const ausrichten = (kamera) => {
    for (const w of liste) {
      v.set(kamera.position.x - w.p.x, kamera.position.z - w.p.y);
      w.wand.visible = v.dot(w.n) < 0;                         // Kamera außerhalb dieser Wand → nur Fußleiste
    }
  };
  return { gruppe, ausrichten };
}

// Runder Teppich (unter dem Couchtisch): weich, dezent gemustert
export function teppich(x, z, r) {
  const n = 512, c = document.createElement('canvas');
  c.width = c.height = n;
  const g = c.getContext('2d');
  g.fillStyle = '#4e5866';
  g.beginPath(); g.arc(n / 2, n / 2, n / 2, 0, Math.PI * 2); g.fill();
  // Webstruktur: feines Rauschen, dazu eine schmale Bordüre
  for (let i = 0; i < 9000; i++) {
    const a = Math.random() * Math.PI * 2, r = Math.sqrt(Math.random()) * n * 0.5;
    g.fillStyle = `rgba(${Math.random() < 0.5 ? '255,255,255' : '0,0,0'},0.05)`;
    g.fillRect(n / 2 + Math.cos(a) * r, n / 2 + Math.sin(a) * r, 2, 2);
  }
  g.strokeStyle = 'rgba(214,196,170,0.5)';
  g.lineWidth = n * 0.012;
  g.beginPath(); g.arc(n / 2, n / 2, n * 0.45, 0, Math.PI * 2); g.stroke();
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const m = new THREE.Mesh(new THREE.CircleGeometry(r, 64),
    new THREE.MeshStandardMaterial({ map: tex, roughness: 0.95 }));
  m.rotation.x = -Math.PI / 2;
  m.position.set(x, 0.002, z);
  m.receiveShadow = true;
  m.raycast = () => {};                  // gehört zum Boden: Klicks gehen durch
  return m;
}

// Hintergrund: ruhiger Verlauf als ferne Kuppel statt Schwarz über den Wänden. Eine Kuppel statt scene.background,
// weil die Umgebungsverdeckung (GTAO) Pixel ohne Tiefe schwarz färbt – so bleibt der Verlauf sichtbar.
// Khronos-Neutral (unser Tonwert-Mapping) drückt sehr dunkle Töne fast auf Schwarz (unter 0,08 linear: y = 6,25·x²).
// Für den Hintergrund rechnen wir das zurück, damit er so erscheint wie gewünscht – mit und ohne Nachbearbeitung.
function vorNeutral(hex) {
  const c = new THREE.Color(hex);
  for (const k of ['r', 'g', 'b']) c[k] = c[k] < 0.04 ? Math.sqrt(c[k] / 6.25) : c[k] + 0.04;
  return c;
}

export function himmel(unten, oben = 0x34353a) {
  const geo = new THREE.SphereGeometry(20, 32, 16);
  const farbe = [], a = vorNeutral(unten), b = vorNeutral(oben), c = new THREE.Color();
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const t = THREE.MathUtils.clamp(pos.getY(i) / 20, 0, 1) ** 0.6;
    c.copy(a).lerp(b, t);
    farbe.push(c.r, c.g, c.b);
  }
  geo.setAttribute('color', new THREE.Float32BufferAttribute(farbe, 3));
  // nach innen gewendet (Reihenfolge und Normalen), damit auch die Verdeckung sie als zugewandte Fläche sieht
  const idx = geo.index.array;
  for (let i = 0; i < idx.length; i += 3) { const t = idx[i + 1]; idx[i + 1] = idx[i + 2]; idx[i + 2] = t; }
  const nrm = geo.attributes.normal.array;
  for (let i = 0; i < nrm.length; i++) nrm[i] = -nrm[i];
  const kuppel = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ vertexColors: true, fog: false }));
  kuppel.renderOrder = -1;
  return kuppel;
}
