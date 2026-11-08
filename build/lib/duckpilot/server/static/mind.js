// Knowlins Kopf als räumliches neuronales Netz (seit 0.38.8 auf der Startseite; neu gebaut in 0.38.21 nach // Hinweis mit Vorbild-Bild: „das aktuelle Netz ist an vielen Stellen so komisch verbogen und nach innen wirkt es hohl,
// als ob es nur ein Obstnetz ist“).
// Jetzt wie ein Plexus: Neuronen füllen den ganzen Raum einer Gehirnform (innen dichter, nicht nur die Oberfläche),
// jedes mit seinen nächsten Nachbarn durch gerade, feine Linien verbunden. Keine Hülle, keine Bögen. Seit 0.38.23 etwas
// kleiner und auf einem flachen Halo als Bezugsfläche (Wunsch: „es soll nur auf einer Art Halo oder
// Bezugsfläche sein“ – wie die Scheibe früher, aber keine Blase um das Netz).
// Hinten blasser und kleiner, vorn heller; die Form dreht sich langsam. Impulse laufen als Lichtpunkte mit Schweif über
// die Synapsen, lassen das Ziel aufglühen und stoßen manchmal den nächsten an (Kettenreaktion). Gleiche Bildsprache wie
// das Netz der Website und das Erfahrungsnetz (`hirn.js`).
//
// Die Form zeigt nur, was der Kopf gerade tut, nie ein Gefühl, das er nicht hat:
//   ruhe    – atmet langsam, wenige Impulse
//   hoert   – ein Puls läuft von außen nach innen, Impulse wandern zur Mitte
//   denkt   – viele Impulse und Ketten, das Netz leuchtet stärker und atmet tiefer
//   spricht – rhythmische Wellen nach außen
//
// Sparsam: gezeichnet wird nur, solange die Form zu sehen ist (IntersectionObserver, sichtbarer Tab), höchstens 30 Bilder
// je Sekunde, devicePixelRatio höchstens 2; Linien nach Tiefe gebündelt (wenige Pfade je Bild). Mit „Bewegung reduzieren“
// steht ein ruhiges Standbild, das je Zustand nur heller oder dunkler wird. Farben kommen aus den Tokens
// (getComputedStyle), nicht aus festen Werten.

const SCHRITT = 1000 / 30;
const MAX_IMPULSE = 60;
const NEURONEN = 240;
const NACHBARN = 5;               // je Neuron so viele nächste Nachbarn
const REICHWEITE = 0.4;           // längere Verbindungen nur, wenn ein Neuron sonst allein wäre
const SCHICHTEN = 6;              // Tiefen-Bündel für die Linien

// Zielwerte je Zustand; die gezeigten Werte gleiten weich dorthin
export const ZUSTAENDE = {
  ruhe: { energie: 0.25, dreh: 0.07, wabern: 0.02, atem: 0.022, atemTakt: 0.75, rate: 2, kette: 0.3, tempo: 0.55, welle: '' },
  hoert: { energie: 0.5, dreh: 0.1, wabern: 0.03, atem: 0.018, atemTakt: 1.0, rate: 5, kette: 0.35, tempo: 0.85, welle: 'innen' },
  denkt: { energie: 1, dreh: 0.2, wabern: 0.05, atem: 0.04, atemTakt: 2.2, rate: 18, kette: 0.6, tempo: 1.25, welle: '' },
  spricht: { energie: 0.72, dreh: 0.13, wabern: 0.035, atem: 0.02, atemTakt: 1.5, rate: 7, kette: 0.4, tempo: 1.0, welle: 'aussen' },
};

// kleiner, fester Zufall – das Netz sieht bei jedem Laden gleich aus (auch das Standbild)
export function zufall(seed) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// Gehirnform: Ellipsoid (breiter als hoch, vorn und hinten gestreckt), oben eine leichte Längsfurche zwischen den
// Hälften, hinten unten etwas Kleinhirn. Gibt den Radius-Faktor für eine Richtung zurück (1 = Grundform).
function form(dx, dy, dz) {
  let k = 1 + 0.07 * Math.cos(3 * Math.atan2(dz, dx)) * (1 - Math.abs(dy));      // Lappen
  if (dy > 0.2) k -= 0.12 * Math.exp(-((dz / 0.12) ** 2)) * dy;                  // Furche oben zwischen den Hälften
  if (dy < -0.35 && dx < -0.2) k += 0.06;                                        // Kleinhirn hinten unten
  return k;
}

// Das Netz: Neuronen füllen die Form (innen etwas dichter als gleichmäßig), jedes mit seinen nächsten Nachbarn durch
// gerade Synapsen verbunden; alles hängt zusammen. Koordinaten etwa im Einheitsradius.
export function bauNetz(n = NEURONEN, seed = 11) {
  const r = zufall(seed);
  const neuronen = [];
  let versuche = 0;
  while (neuronen.length < n && versuche++ < n * 40) {
    const x = r() * 2 - 1, y = r() * 2 - 1, z = r() * 2 - 1;
    const l = Math.hypot(x, y, z);
    if (l > 1 || l < 1e-6) continue;
    // innen dichter: Radius gestaucht (gleichmäßig wäre l, hier l^1.25) – das Netz wirkt gefüllt, nicht hohl
    const rad = l ** 1.25;
    const dx = x / l, dy = y / l, dz = z / l;
    const k = form(dx, dy, dz) * rad;
    const px = dx * k * 1.18, py = dy * k * 0.86, pz = dz * k * 0.98;
    // Abstand halten: Neuronen nicht zu dicht aufeinander (sonst Klumpen statt Netz)
    if (neuronen.some((q) => Math.hypot(q.x - px, q.y - py, q.z - pz) < 0.062)) continue;
    const nabe = r() < 0.05;                                    // ein paar größere, hellere Knoten
    neuronen.push({ x: px, y: py, z: pz, r: rad, groesse: nabe ? 1.7 + r() * 0.5 : 0.7 + r() * 0.5, nabe,
      phase: r() * Math.PI * 2, glut: 0 });
  }
  const abstand = (a, b) => Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);
  const synapsen = [];
  const da = new Set();
  const verbinde = (i, j) => {
    const k = i < j ? `${i}|${j}` : `${j}|${i}`;
    if (i === j || da.has(k)) return;
    da.add(k);
    const a = neuronen[i], b = neuronen[j];
    // gerade Linie; `c` ist die Mitte (für Impulse und Tiefe) – keine Bögen mehr
    synapsen.push({ a: i, b: j, laenge: abstand(a, b), glut: 0, c: { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, z: (a.z + b.z) / 2 } });
  };
  const m = neuronen.length;
  neuronen.forEach((a, i) => {
    const nah = [];
    for (let j = 0; j < m; j++) if (j !== i) nah.push({ j, d: abstand(a, neuronen[j]) });
    nah.sort((p, q) => p.d - q.d);
    const k = a.nabe ? NACHBARN + 3 : NACHBARN;
    nah.slice(0, k).forEach(({ j, d }, idx) => { if (d < REICHWEITE || idx === 0) verbinde(i, j); });
  });
  // alles zusammenhängend: getrennte Teile über ihr nächstes Paar verbinden
  for (;;) {
    const teil = new Array(m).fill(-1);
    const nb = neuronen.map(() => []);
    synapsen.forEach((s) => { nb[s.a].push(s.b); nb[s.b].push(s.a); });
    let anzahl = 0;
    for (let s = 0; s < m; s++) {
      if (teil[s] >= 0) continue;
      const stapel = [s];
      teil[s] = anzahl;
      while (stapel.length) {
        const v = stapel.pop();
        for (const w of nb[v]) if (teil[w] < 0) { teil[w] = anzahl; stapel.push(w); }
      }
      anzahl++;
    }
    if (anzahl <= 1) break;
    let best = null;
    for (let i = 0; i < m; i++) {
      if (teil[i] !== 0) continue;
      for (let j = 0; j < m; j++) {
        if (teil[j] === 0) continue;
        const d = abstand(neuronen[i], neuronen[j]);
        if (!best || d < best.d) best = { i, j, d };
      }
    }
    verbinde(best.i, best.j);
  }
  const nachbarn = neuronen.map(() => []);
  synapsen.forEach((s, k) => { nachbarn[s.a].push(k); nachbarn[s.b].push(k); });
  return { neuronen, synapsen, nachbarn };
}

// Drehen (yaw um die Hochachse, pitch um die Querachse) und perspektivisch abbilden; s < 1 heißt weiter hinten
export function projiziere(p, yaw, pitch, F = 2.7) {
  const cy = Math.cos(yaw), sy = Math.sin(yaw), cp = Math.cos(pitch), sp = Math.sin(pitch);
  const x1 = p.x * cy + p.z * sy, z1 = -p.x * sy + p.z * cy;
  const y2 = p.y * cp - z1 * sp, z2 = p.y * sp + z1 * cp;
  const s = F / (F + z2);
  return { x: x1 * s, y: y2 * s, z: z2, s };
}

// Ein weiches Feld über die Richtung – lässt das Netz sanft wabern (ohne die Linien zu verbiegen)
function feld(dx, dy, dz, t) {
  return Math.sin(dx * 2.3 + t * 0.9) * Math.cos(dy * 1.9 - t * 0.7) + 0.6 * Math.sin(dz * 2.7 + dx * 1.3 + t * 1.3);
}

export function initMind(canvas) {
  if (!canvas || !canvas.getContext) return { setZustand() {} };
  const g = canvas.getContext('2d');
  const reduziert = window.matchMedia ? window.matchMedia('(prefers-reduced-motion: reduce)') : { matches: false };
  const { neuronen, synapsen, nachbarn } = bauNetz();
  const zufallStill = zufall(5);
  // fürs Standbild: feste glimmende Neuronen und stehende Impulse – je Zustand mehr oder weniger
  const still = {
    glut: neuronen.map(() => zufallStill()),
    impulse: Array.from({ length: 12 }, () => ({ s: Math.floor(zufallStill() * synapsen.length), u: 0.45 + zufallStill() * 0.4, vor: zufallStill() < 0.5 })),
  };
  let zustand = 'ruhe';
  const p = { ...ZUSTAENDE.ruhe, innen: 0, aussen: 0 };          // gezeigte, weich gleitende Werte
  let sichtbar = false;
  let raf = 0;
  let zuletzt = 0;
  let uhr = 0;                                                   // eigene Zeit: steht still, wenn nichts zu sehen ist
  let drehung = 0.6;
  let phaseInnen = 0;
  let phaseAussen = 0;
  let farben = null;
  let farbenAlt = -10;
  const impulse = [];

  // Farben aus den Tokens, in r/g/b zerlegt (der Canvas normalisiert jede CSS-Farbe), damit Verläufe Deckkraft tragen
  const pruef = document.createElement('canvas').getContext('2d');
  function rgb(text, alt) {
    pruef.fillStyle = alt;
    pruef.fillStyle = text || alt;
    const v = String(pruef.fillStyle);
    if (v[0] === '#') return [1, 3, 5].map((i) => parseInt(v.slice(i, i + 2), 16));
    const m = v.match(/[\d.]+/g) || [128, 128, 128];
    return m.slice(0, 3).map(Number);
  }
  const rgba = (c, a) => `rgba(${c[0]}, ${c[1]}, ${c[2]}, ${Math.max(0, Math.min(1, a)).toFixed(3)})`;
  function lies() {
    const s = getComputedStyle(canvas);
    const v = (n) => s.getPropertyValue(n).trim();
    const neu = {
      akzent: rgb(v('--accent'), 'orange'), hell: rgb(v('--accent-text'), 'orange'), tief: rgb(v('--accent-strong'), 'orange'),
      licht: rgb(v('--ink'), 'white'), linie: rgb(v('--ink-3'), 'gray'),
    };
    const schluessel = JSON.stringify(neu);
    if (farben && farben.schluessel === schluessel) return;
    farben = { ...neu, schluessel };
    sprites();
  }

  // Vorgezeichneter Schein (weicher Lichtfleck) – schneller und weicher als je Bild neu
  let schein = null;
  function sprites() {
    const n = 64;
    schein = document.createElement('canvas'); schein.width = schein.height = n;
    const c = schein.getContext('2d');
    const v = c.createRadialGradient(n / 2, n / 2, 0, n / 2, n / 2, n / 2);
    v.addColorStop(0, rgba(farben.licht, 0.95));
    v.addColorStop(0.14, rgba(farben.hell, 0.7));
    v.addColorStop(0.4, rgba(farben.akzent, 0.22));
    v.addColorStop(1, rgba(farben.akzent, 0));
    c.fillStyle = v; c.fillRect(0, 0, n, n);
  }

  function groesse() {
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = Math.round(canvas.clientWidth * dpr);
    const h = Math.round(canvas.clientHeight * dpr);
    if (w && h && (canvas.width !== w || canvas.height !== h)) { canvas.width = w; canvas.height = h; }
    return { w: canvas.width, h: canvas.height, dpr };
  }

  // Wellenfront (Abstand von der Mitte) für Zuhören (außen → innen) und Sprechen (innen → außen)
  const frontInnen = () => 1.25 - (phaseInnen % 1) * 1.45;
  const frontAussen = () => (phaseAussen % 1) * 1.45 - 0.15;
  const buckel = (r, front) => Math.exp(-(((r - front) / 0.14) ** 2));

  // Lage eines Neurons zu Zeit t: atmen und leise wabern – die Linien bleiben gerade, weil nur Punkte sich bewegen
  function lage(q, t) {
    const r = Math.hypot(q.x, q.y, q.z) || 1;
    const dx = q.x / r, dy = q.y / r, dz = q.z / r;
    let k = 1 + p.atem * Math.sin(t * p.atemTakt) + p.wabern * feld(dx, dy, dz, t * (0.6 + p.energie));
    k += 0.05 * p.aussen * buckel(q.r, frontAussen()) - 0.04 * p.innen * buckel(q.r, frontInnen());
    const drift = 0.012 * Math.sin(t * 0.6 + q.phase);
    return { x: q.x * k + drift * dz, y: q.y * k + drift * 0.7, z: q.z * k - drift * dx };
  }

  function schiessen(s, vonA) { if (impulse.length < MAX_IMPULSE) impulse.push({ s, vor: vonA, u: 0 }); }

  // Neue Impulse: beim Zuhören von außen nach innen, beim Sprechen von innen nach außen, sonst kreuz und quer
  function anstossen() {
    const welle = ZUSTAENDE[zustand].welle;
    let best = null;
    for (let versuch = 0; versuch < 4; versuch++) {
      const k = Math.floor(Math.random() * synapsen.length);
      const s = synapsen[k];
      const ra = neuronen[s.a].r, rb = neuronen[s.b].r;
      const wert = welle === 'innen' ? Math.max(ra, rb) : welle === 'aussen' ? -Math.min(ra, rb) : Math.random();
      if (!best || wert > best.wert) best = { k, wert, vorA: welle === 'innen' ? ra > rb : welle === 'aussen' ? ra < rb : Math.random() < 0.5 };
    }
    schiessen(best.k, best.vorA);
  }

  function ankommen(imp) {
    const s = synapsen[imp.s];
    const ziel = imp.vor ? s.b : s.a;
    neuronen[ziel].glut = 1;
    // Kettenreaktion: das Ziel feuert weiter – seltener, je voller das Netz schon ist
    const welle = ZUSTAENDE[zustand].welle;
    const chance = p.kette * (1 - impulse.length / MAX_IMPULSE);
    const wege = nachbarn[ziel].filter((k) => k !== imp.s);
    const passend = welle ? wege.filter((k) => {
      const t = synapsen[k];
      const anderes = neuronen[t.a === ziel ? t.b : t.a].r;
      return welle === 'innen' ? anderes < neuronen[ziel].r : anderes > neuronen[ziel].r;
    }) : wege;
    const auswahl = passend.length ? passend : wege;
    for (let n = 0; n < (zustand === 'denkt' ? 2 : 1); n++) {
      if (!auswahl.length || Math.random() > chance) break;
      const k = auswahl[Math.floor(Math.random() * auswahl.length)];
      schiessen(k, synapsen[k].a === ziel);
    }
  }

  function schritt(dt) {
    const ziel = ZUSTAENDE[zustand];
    const f = 1 - Math.exp(-dt * 2.2);
    for (const k of ['energie', 'dreh', 'wabern', 'atem', 'atemTakt', 'rate', 'kette', 'tempo']) p[k] += (ziel[k] - p[k]) * f;
    p.innen += ((ziel.welle === 'innen' ? 1 : 0) - p.innen) * f;
    p.aussen += ((ziel.welle === 'aussen' ? 1 : 0) - p.aussen) * f;
    uhr += dt;
    drehung += dt * p.dreh;
    phaseInnen += dt * 0.55;
    phaseAussen += dt * 0.8;
    for (const n of neuronen) n.glut = Math.max(0, n.glut - dt * 1.3);
    for (const s of synapsen) s.glut = Math.max(0, s.glut - dt * 1.6);
    if (Math.random() < p.rate * dt) anstossen();
    for (let i = impulse.length - 1; i >= 0; i--) {
      const imp = impulse[i];
      const s = synapsen[imp.s];
      imp.u += dt * p.tempo * 1.1 / (0.2 + s.laenge);
      s.glut = Math.max(s.glut, 0.9 * Math.sin(Math.PI * Math.min(1, imp.u)));
      if (imp.u >= 1) { impulse.splice(i, 1); ankommen(imp); }
    }
  }

  // Der Halo: eine flache, ruhige Scheibe hinter dem Netz – Bezugsfläche, keine Kugel (Wahl am 7.11. aus drei
  // Vorschlägen: Scheibe wie früher, Ring, Bodenfläche). Bewegt sich nicht mit, wird nur mit der Aktivität etwas heller;
  // das Netz darf über ihren Rand hinausragen.
  function halo(cx, cy, R, strich, E, fb) {
    const Rh = R * 1.08;
    const f = g.createRadialGradient(cx, cy - Rh * 0.2, Rh * 0.05, cx, cy, Rh);
    f.addColorStop(0, rgba(fb.licht, 0.035 + 0.02 * E));
    f.addColorStop(0.7, rgba(fb.akzent, 0.035 + 0.025 * E));
    f.addColorStop(1, rgba(fb.akzent, 0.07 + 0.05 * E));
    g.beginPath(); g.arc(cx, cy, Rh, 0, Math.PI * 2);
    g.fillStyle = f; g.fill();
    g.lineWidth = strich;
    g.strokeStyle = rgba(fb.akzent, 0.16 + 0.12 * E);
    g.stroke();
  }

  function male(t, standbild = false) {
    const { w, h, dpr } = groesse();
    if (!w || !h) return;
    if (!farben || t - farbenAlt > 2 || standbild) { lies(); farbenAlt = t; }
    const fb = farben;
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.globalCompositeOperation = 'source-over';
    g.globalAlpha = 1;
    g.clearRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2;
    const R = Math.min(w, h) * 0.33;
    const E = p.energie;
    const strich = dpr * Math.max(0.6, Math.min(1, R / (110 * dpr)));

    // leiser Schein hinter dem Kopf – Tiefe, keine Hülle
    const v = g.createRadialGradient(cx, cy, R * 0.05, cx, cy, R * 1.5);
    v.addColorStop(0, rgba(fb.akzent, 0.07 + 0.1 * E));
    v.addColorStop(0.5, rgba(fb.akzent, 0.025 + 0.04 * E));
    v.addColorStop(1, rgba(fb.akzent, 0));
    g.fillStyle = v; g.fillRect(0, 0, w, h);
    halo(cx, cy, R, strich, E, fb);

    // Netz abbilden
    const pitch = 0.22 + 0.08 * Math.sin(t * 0.17);
    const sch = neuronen.map((n) => {
      const q = projiziere(lage(n, t), drehung, pitch);
      return { x: cx + q.x * R, y: cy + q.y * R, z: q.z, s: q.s };
    });
    const nah = (z) => Math.max(0, Math.min(1, (1.2 - z) / 2.4));   // 1 vorn, 0 hinten
    const welleAn = (r) => p.aussen * buckel(r, frontAussen()) + p.innen * buckel(r, frontInnen());

    // Synapsen: gerade, fein, nach Tiefe gebündelt (ein Pfad je Schicht) – additiv wie Licht
    g.globalCompositeOperation = 'lighter';
    g.lineCap = 'round';
    const schichten = Array.from({ length: SCHICHTEN }, () => []);
    const warm = [];
    synapsen.forEach((s, k) => {
      const tiefe = nah((sch[s.a].z + sch[s.b].z) / 2);
      schichten[Math.min(SCHICHTEN - 1, Math.floor(tiefe * SCHICHTEN))].push(s);
      const wl = Math.max(welleAn(neuronen[s.a].r), welleAn(neuronen[s.b].r)) * 0.6;
      if (s.glut > 0.03 || wl > 0.05) warm.push([k, Math.max(s.glut, wl), tiefe]);
    });
    schichten.forEach((liste, i) => {
      if (!liste.length) return;
      const tiefe = (i + 0.5) / SCHICHTEN;
      g.beginPath();
      for (const s of liste) { const a = sch[s.a], b = sch[s.b]; g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); }
      g.lineWidth = strich * (0.4 + 0.5 * tiefe);
      g.strokeStyle = rgba(fb.akzent, (0.04 + 0.3 * tiefe ** 1.3) * (0.7 + 0.45 * E));
      g.stroke();
    });
    for (const [k, gl, tiefe] of warm) {                           // wo ein Impuls läuft: heller
      const s = synapsen[k], a = sch[s.a], b = sch[s.b];
      g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y);
      g.lineWidth = strich * (0.8 + 0.8 * tiefe);
      g.strokeStyle = rgba(fb.hell, gl * (0.25 + 0.5 * tiefe));
      g.stroke();
    }

    // Impulse: Lichtpunkt mit Schweif entlang der geraden Synapse
    const zeigImpulse = standbild ? still.impulse.slice(0, Math.round(3 + 9 * E)) : impulse;
    for (const imp of zeigImpulse) {
      const s = synapsen[imp.s];
      const [a, b] = imp.vor ? [sch[s.a], sch[s.b]] : [sch[s.b], sch[s.a]];
      const u = Math.min(1, imp.u);
      const tiefe = nah((a.z + b.z) / 2);
      const hell = (0.45 + 0.55 * tiefe) * Math.min(1, u * 6, (1 - u) * 8 + 0.4);
      const u0 = Math.max(0, u - 0.35);
      const x0 = a.x + (b.x - a.x) * u0, y0 = a.y + (b.y - a.y) * u0;
      const x1 = a.x + (b.x - a.x) * u, y1 = a.y + (b.y - a.y) * u;
      const verlauf = g.createLinearGradient(x0, y0, x1, y1);
      verlauf.addColorStop(0, rgba(fb.akzent, 0));
      verlauf.addColorStop(1, rgba(fb.hell, 0.8 * hell));
      g.strokeStyle = verlauf;
      g.lineWidth = strich * (1.4 + 1.2 * tiefe);
      g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
      const gr = R * 0.07 * (0.7 + 0.5 * tiefe);
      g.globalAlpha = hell;
      g.drawImage(schein, x1 - gr, y1 - gr, gr * 2, gr * 2);
      g.globalAlpha = 1;
    }

    // Neuronen: kleine helle Punkte, hinten kleiner und blasser; glühende und Naben mit Schein
    for (let i = 0; i < neuronen.length; i++) {
      const n = neuronen[i], q = sch[i];
      const tiefe = nah(q.z);
      const gl = Math.min(1.2, n.glut + 0.55 * welleAn(n.r) + (standbild ? still.glut[i] ** 4 * E : 0));
      const rad = strich * (0.6 + 1.1 * tiefe) * n.groesse * q.s * (1 + 0.5 * Math.min(1, gl));
      if (n.nabe || gl > 0.05) {
        const gr = rad * (n.nabe ? 4.5 : 3) * (1 + 1.1 * Math.min(1, gl));
        g.globalAlpha = Math.min(1, (n.nabe ? 0.35 : 0) + gl) * (0.3 + 0.7 * tiefe) * (0.7 + 0.4 * E);
        g.drawImage(schein, q.x - gr, q.y - gr, gr * 2, gr * 2);
      }
      g.globalAlpha = (0.25 + 0.75 * tiefe ** 1.2) * (0.75 + 0.25 * E);
      g.fillStyle = rgba(gl > 0.3 ? fb.licht : fb.hell, 1);
      g.beginPath(); g.arc(q.x, q.y, rad, 0, Math.PI * 2); g.fill();
    }
    g.globalCompositeOperation = 'source-over';
    g.globalAlpha = 1;
  }

  function bild(now) {
    raf = 0;
    if (!laufen()) return;
    raf = requestAnimationFrame(bild);
    if (now - zuletzt < SCHRITT) return;
    const dt = Math.min(0.1, (now - (zuletzt || now)) / 1000);
    zuletzt = now;
    schritt(dt);
    male(uhr);
  }

  // Standbild: Werte sofort auf den Zustand, feste Zeit – ein ruhiges, schönes Bild, nur die Helligkeit wechselt
  function standbild() {
    Object.assign(p, ZUSTAENDE[zustand], { innen: 0, aussen: 0, wabern: 0.02, atem: 0 });
    drehung = 0.6;
    male(4, true);
  }

  const laufen = () => sichtbar && !document.hidden && !reduziert.matches;
  function weiter() {
    if (laufen()) { if (!raf) { zuletzt = 0; raf = requestAnimationFrame(bild); } return; }
    if (raf) { cancelAnimationFrame(raf); raf = 0; }
    if (sichtbar && reduziert.matches) standbild();
  }

  if ('IntersectionObserver' in window) {
    new IntersectionObserver((e) => { sichtbar = e.some((x) => x.isIntersecting); weiter(); }).observe(canvas);
  } else { sichtbar = true; }
  document.addEventListener('visibilitychange', weiter);
  if (reduziert.addEventListener) reduziert.addEventListener('change', weiter);
  window.addEventListener('resize', () => { if (sichtbar && !raf) (reduziert.matches ? standbild() : male(uhr)); });
  // ein paar Impulse von Anfang an, damit das Netz nicht leer startet
  for (let i = 0; i < 4; i++) { anstossen(); impulse[impulse.length - 1].u = Math.random() * 0.8; }
  weiter();

  const api = {
    setZustand(z) {
      if (!(z in ZUSTAENDE) || z === zustand) return;
      zustand = z;
      canvas.dataset.zustand = z;
      if (z === 'denkt') for (let i = 0; i < 8; i++) anstossen();    // Nachdenken setzt sofort ein
      weiter();
      if (!raf && sichtbar) (reduziert.matches ? standbild() : male(uhr));
    },
    get zustand() { return zustand; },
  };
  canvas.mind = api;                                             // für Abnahme und Konsole: $('mind').mind.setZustand('denkt')
  return api;
}
