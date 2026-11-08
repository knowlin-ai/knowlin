// Kollisionsmodus (nur Simulator mit echter Physik). Bedienung wie in CAD-Programmen und Robotik-Simulatoren
// (Onshape, SketchUp, MuJoCo `simulate`, Gazebo „Mouse Drag“):
//  • Zeigen bewegt nichts. Was sich anfassen lässt, leuchtet auf, der Zeiger wird zur Hand, und ein Hinweis am
//    Zeiger sagt, was Ziehen tut.
//  • Ente anfassen und ziehen: Sie hängt am angefassten Punkt an einer Feder zur Maus (gestrichelte Linie, Kraft
//    am Zeiger). Das Ziel liegt auf einer Ebene quer zur Kamera durch den Anfasspunkt – wie in MuJoCo und Gazebo.
//    Kurz zupfen schubst, lange und weit ziehen wirft sie um.
//  • Ding anfassen und ziehen: Es gleitet in seiner Höhe über den Boden (wie „Verschieben“ in SketchUp). Mit
//    gedrückter Umschalttaste oder am blauen Pfeil darüber geht es nur senkrecht (blaue Achse) – so hebt man es.
//    Lot, Bodenring und Maße (Höhe, Weg) zeigen, wo es ist. Mit Schwung loslassen wirft es: Richtung und Tempo
//    kommen aus der Mausbewegung über den Boden, der Winkel aus dem Regler „Wurfwinkel“. Der gestrichelte Bogen
//    zeigt vorher, wo es landet. Ohne Schwung loslassen legt es ab (es fällt).
//  • Kamera wie gewohnt in CAD: rechte Maustaste dreht, Mausrad zoomt; am Handy drehen zwei Finger.
//  • Zielwurf (Werfen: „zielen“): Ding anfassen und nach hinten ziehen wie bei einer Schleuder – Zuglänge = Tempo
//    (50 cm = 6 m/s), Richtung = Gegenrichtung, Winkel vom Regler. Der Bogen zeigt vorher, ob und wo er die Ente
//    trifft (Körperteil, Aufpralltempo, Impuls). Esc bricht ab. Für gezielte, wiederholbare Stöße fürs Training.
//  • In der Luft abstellen (Schalter): ohne Schwung losgelassen bleibt ein Ding stehen, wo es ist – z. B. ein Ball auf
//    Kopfhöhe, gegen den sie läuft. Sonst fällt es; Lot und Ring zeigen vorher, wo es landet (Boden oder Möbel).
//  • Wegräumen: das zuletzt angefasste Ding ist gewählt (blauer Pfeil); Entf oder „Wegräumen“ nimmt es weg.
//    Ein Ding woanders hinstellen: in der Leiste antippen und auf den Boden klicken.
//  • Ohne Zeigegerät (WCAG 2.1.1): Tasten im Bedienfeld – schubsen von einer Seite, Ding vor die Ente legen,
//    werfen, rollen, wegräumen.
//  • Nach einem Sturz (überall, auch am Roboter): das Stopp-Fenster. Mikrofon kurz offen, „Stopp“ oder
//    „Liegen lassen“ halten sie liegen (wirkt wie der Not-Aus), sonst steht sie danach selbst auf.
// Koordinaten: Physik x vorn, y links, z oben → three.js (x, z, −y), so wie in duck3d.js.

import * as THREE from './vendor/three.module.min.js';
import { uebersetzeText } from './i18n.js';

const SEND_HZ = 30;                 // so oft gehen Hand- und Zugziel an den Server
const Z_MIN = 0.035, Z_MAX = 1.2;   // m – Höhe des Ziels
const WURF_MAX = 6, WURF_AB = 0.3;  // m/s – schneller wirft die Physik nicht; darunter wird abgelegt
const WURF_GAIN = 1.0;              // Mausschwung über den Boden (m/s) → Abwurftempo
const ZIEL_ZUG_MAX = 0.5;           // m – so weit zurückgezogen wirft die Schleuder mit WURF_MAX
const G = 9.81;
const tr = (text) => uebersetzeText(text) || text;
const BLAU = 0x4589ff, ORANGE = 0xf0962c, HELL = 0xf4f4f4;   // blaue Achse = senkrecht wie in CAD

export function initKollision(h) {
  const { $, scene, api, send, toast, stageEl, state, listener, estop } = h;
  const btn = $('kol-btn'), panel = $('kol-panel');
  const meshes = new Map();          // id → THREE.Mesh
  const group = new THREE.Group();
  scene.scene.add(group);
  let status = null, on = false, sf = null, objekte = [], placing = null, sentAt = 0;
  let serverHeld = null;             // was die Hand laut Physik hält
  let zugInfo = null;                // Zug laut Physik: {anker, ziel, kraft_n, teil}
  let drag = null;                   // {art: 'zug'|'ding', …} solange die Taste gedrückt ist
  let hover = null;                  // {art: 'ente'|'ding'|'pfeil', …} was unter dem Zeiger liegt
  let gewaehlt = null;               // zuletzt angefasstes Ding (trägt den blauen Pfeil)
  let pointer = null;                // letzte Zeigerposition (clientX/Y)
  let shift = false;
  let wurfWinkel = 30;               // Grad

  const stufe = () => (panel.querySelector('input[name="kol-stufe"]:checked') || {}).value || 'mittel';
  const STAERKE = { leicht: 0.25, mittel: 0.5, kraeftig: 0.85 };
  let auswahl = 'ball';              // gewähltes Ding für Tasten (werfen, rollen, vor die Ente legen)
  const zugMax = () => (status && status.grenzen && status.grenzen.zug && status.grenzen.zug.kraft_n_max) || 6;

  async function call(path, body) {
    const r = await api(`/api/kollision${path}`, 'POST', body).catch(() => null);
    if (!r || !r.ok) toast((r && r.fehler) || 'Geht gerade nicht', true);
    else if (path) setTimeout(() => refresh(true), 300);   // Lage danach holen (liegt es still, kommt kein Strom)
    return r;
  }

  // ── Hilfslinien: Lot + Bodenring, senkrechte Achse, Zug-Feder, Anfasspunkt, blauer Pfeil, Flugbogen ──
  const T = (p) => new THREE.Vector3(p.x, p.z, -p.y);
  const P = (v) => ({ x: v.x, y: -v.z, z: v.y });
  const lineMat = (color, opacity = 0.6) => new THREE.LineBasicMaterial({ color, transparent: true, opacity, depthTest: false });
  function line(mat) {
    const g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(6), 3));
    const l = new THREE.Line(g, mat);
    l.frustumCulled = false; l.visible = false; l.renderOrder = 10;
    group.add(l);
    return l;
  }
  function setLine(l, a, b) {
    const p = l.geometry.attributes.position.array;
    const A = T(a), B = T(b);
    p.set([A.x, A.y, A.z, B.x, B.y, B.z]);
    l.geometry.attributes.position.needsUpdate = true;
    if (l.material.isLineDashedMaterial) l.computeLineDistances();
    l.visible = true;
  }
  const lot = line(lineMat(HELL, 0.45));
  const achse = line(lineMat(BLAU, 0.9));
  const feder = line(new THREE.LineDashedMaterial({ color: ORANGE, dashSize: 0.015, gapSize: 0.01, transparent: true, depthTest: false }));
  const ringGeo = new THREE.RingGeometry(0.03, 0.04, 32);
  const bodenRing = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({ color: HELL, transparent: true, opacity: 0.5, side: THREE.DoubleSide }));
  bodenRing.rotation.x = -Math.PI / 2; bodenRing.visible = false;
  const punktMat = new THREE.MeshBasicMaterial({ color: ORANGE, depthTest: false });
  const anfass = new THREE.Mesh(new THREE.SphereGeometry(0.007, 16, 12), punktMat);
  const zielPunkt = new THREE.Mesh(new THREE.SphereGeometry(0.006, 16, 12), new THREE.MeshBasicMaterial({ color: HELL, depthTest: false }));
  anfass.renderOrder = zielPunkt.renderOrder = 11;
  anfass.visible = zielPunkt.visible = false;
  // blauer Pfeil (Achsgriff wie Onshapes Triade, nur die senkrechte Achse)
  const pfeilMat = new THREE.MeshBasicMaterial({ color: BLAU, transparent: true, opacity: 0.85, depthTest: false });
  const pfeil = new THREE.Group();
  const schaft = new THREE.Mesh(new THREE.CylinderGeometry(0.004, 0.004, 0.07, 12), pfeilMat);
  schaft.position.y = 0.035;
  const spitze = new THREE.Mesh(new THREE.ConeGeometry(0.013, 0.028, 16), pfeilMat);
  spitze.position.y = 0.084;
  const pfeilFang = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.1, 8), new THREE.MeshBasicMaterial({ visible: false }));
  pfeilFang.position.y = 0.05;                     // größere unsichtbare Fangfläche zum leichten Treffen
  pfeil.add(schaft, spitze, pfeilFang);
  pfeil.traverse((o) => { o.renderOrder = 12; });
  pfeil.visible = false;
  group.add(bodenRing, anfass, zielPunkt, pfeil);
  const BOGEN_N = 48;
  const bogenGeo = new THREE.BufferGeometry();
  bogenGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(BOGEN_N * 3), 3));
  const bogen = new THREE.Line(bogenGeo, new THREE.LineDashedMaterial({ color: ORANGE, dashSize: 0.03, gapSize: 0.02 }));
  bogen.visible = false; bogen.frustumCulled = false;
  const landung = new THREE.Mesh(new THREE.RingGeometry(0.03, 0.045, 32),
    new THREE.MeshBasicMaterial({ color: ORANGE, transparent: true, opacity: 0.8, side: THREE.DoubleSide }));
  landung.rotation.x = -Math.PI / 2; landung.visible = false;
  group.add(bogen, landung);
  // Hinweis und Maße am Zeiger (wie SketchUps Messfeld; fürs Auge – das Bedienfeld sagt dasselbe in Worten)
  const mass = document.createElement('div');
  mass.className = 'kol-mass';
  mass.setAttribute('aria-hidden', 'true');
  mass.hidden = true;
  stageEl.append(mass);

  // ── an/aus ────────────────────────────────────────────────────────────
  const saved = {};
  function cameraForTool(enable) {   // linke Taste gehört dem Werkzeug, rechte dreht, Rad zoomt (wie in CAD)
    const c = scene.controls;
    if (!c) return;
    if (enable) {
      if (!saved.mouse) { saved.mouse = { ...c.mouseButtons }; saved.touch = { ...c.touches }; }
      c.mouseButtons = { LEFT: -1, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.ROTATE };
      c.touches = { ONE: -1, TWO: THREE.TOUCH.DOLLY_ROTATE };
    } else if (saved.mouse) {
      c.mouseButtons = saved.mouse; c.touches = saved.touch;
      saved.mouse = saved.touch = null;
    }
  }
  function render() {
    const ok = !!(status && status.verfuegbar);
    // Seit 0.38.24 auch ohne echte Physik sichtbar (Frage „wo finde ich den Modus, Objekte zu platzieren?“) –
    // ein Klick schaltet dann die Physik ein, statt dass der Knopf einfach fehlt
    const vorbereiten = !ok && !!(status && status.braucht_physik);
    btn.hidden = !ok && !vorbereiten;
    btn.classList.toggle('is-vorbereiten', vorbereiten);
    btn.title = vorbereiten ? tr('Spielen: Dinge hinlegen, schubsen und werfen – braucht die echte Physik. Klick schaltet sie ein.')
      : tr('Kollisionsmodus: die Ente schubsen, Ball und Würfel greifen, rollen und werfen – nur im Simulator mit echter Physik');
    on = ok && !!status.aktiv;
    btn.setAttribute('aria-pressed', String(on));
    panel.hidden = !on;
    group.visible = on;
    stageEl.classList.toggle('stage--kollision', on);
    cameraForTool(on);
    const sw = panel.querySelector('[data-set="auto_recover"]');
    if (sw && status && typeof status.selbst_aufstehen === 'boolean' && document.activeElement !== sw) sw.checked = status.selbst_aufstehen;
    const pr = panel.querySelector('[data-set="kollision_protest"]');
    if (pr && status && typeof status.protest === 'boolean' && document.activeElement !== pr) pr.checked = status.protest;
    if (!on) { endDrag(false); setHover(null); placing = null; waehle(null); }
    if (status && Array.isArray(status.objekte)) renderPalette(status.objekte);
    const n = status && status.episoden;
    const zahl = typeof n === 'number' ? n : (n && n.anzahl) || 0;
    $('kol-stats').textContent = zahl ? `${zahl} Stöße, Züge und Würfe fürs Training aufgezeichnet.` : 'Jeder Stoß wird fürs Training aufgezeichnet.';
  }
  async function set(next) {
    const r = await call('', { aktiv: next });
    if (r && r.ok) { status = { ...status, ...r, aktiv: next }; render(); if (next) toast('Kollisionsmodus an: Ente oder Ding anfassen und ziehen'); }
  }
  btn.addEventListener('click', async () => {
    if (status && !status.verfuegbar && status.braucht_physik) {
      toast(tr('Echte Physik startet – gleich danach noch einmal auf „Spielen“'));
      await api('/api/settings', 'POST', { sim_physik: true }).catch(() => null);
      return;
    }
    set(!on);
  });
  $('kol-close').addEventListener('click', () => { set(false); btn.focus(); });

  // ── Dinge: Leiste zum Hinlegen ────────────────────────────────────────
  const palette = $('kol-palette');
  let paletteKey = '';
  function renderPalette(list) {
    objekte = list;
    const key = list.map((o) => o.id).join(',');
    if (key !== paletteKey) {
      paletteKey = key;
      palette.replaceChildren(...list.map((o) => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = 'chip kol-ding';
        b.dataset.id = o.id;
        const dot = document.createElement('i');
        dot.style.background = o.farbe;          // die Farbe des Dings in der 3D-Ansicht
        dot.setAttribute('aria-hidden', 'true');
        b.append(dot, document.createTextNode(o.name));
        b.addEventListener('click', () => choose(o.id));
        return b;
      }));
      if (!list.some((o) => o.id === auswahl) && list.length) auswahl = list[0].id;
    }
    for (const b of palette.children) {
      // Gedrückt heißt hier „liegt bereit zum Hinlegen“ – nicht vorausgewählt (Hinweis aus dem Test 1.11.)
      b.setAttribute('aria-pressed', String(b.dataset.id === placing));
      b.classList.toggle('is-armed', b.dataset.id === placing);
    }
    const o = list.find((x) => x.id === auswahl);
    $('kol-ding-name').textContent = o ? o.name : '';
  }
  function choose(id) {
    auswahl = id;
    placing = placing === id ? null : id;           // zweimal tippen: doch nicht hinlegen
    stageEl.classList.toggle('stage--legen', !!placing);
    renderPalette(objekte);
    const o = objekte.find((x) => x.id === id);
    $('kol-hint').textContent = placing ? `${o ? o.name : 'Ding'}: auf den Boden klicken, um es hinzulegen.` : '';
  }

  // ── Tasten ────────────────────────────────────────────────────────────
  for (const b of panel.querySelectorAll('[data-seite]')) {
    b.addEventListener('click', () => call('/stoss', { ziel: 'rumpf', seite: b.dataset.seite, stufe: stufe() }));
  }
  for (const b of panel.querySelectorAll('[data-ding]')) {
    b.addEventListener('click', () => {
      const a = b.dataset.ding;
      if (a === 'legen') return call('/objekt', { aktion: 'setzen', name: auswahl });       // vor die Ente
      if (a === 'wurf') return call('/wurf', { name: auswahl, ziel: 'ente', staerke: STAERKE[stufe()] });
      if (a === 'rollen') return call('/rollen', { name: auswahl, ziel: 'ente', stufe: stufe() });
      return call('/objekt', { aktion: 'parken', name: auswahl });
    });
  }
  // In der Luft abstellen: losgelassen (ohne Schwung) bleibt es stehen – z. B. ein Ball auf Kopfhöhe zum Dagegenlaufen
  const festSw = $('kol-fest');
  try { festSw.checked = localStorage.getItem('duckpilot.kol-fest') === '1'; } catch { /* ohne Speicher: aus */ }
  festSw.addEventListener('change', () => {
    try { localStorage.setItem('duckpilot.kol-fest', festSw.checked ? '1' : '0'); } catch { /* egal */ }
    if (!festSw.checked) fallenLassen();                 // Schalter aus = alles, was schwebt, fällt
  });
  // Fallen lassen (0.33): Doppelklick auf ein schwebendes Ding, „Fallen lassen“/F fürs gewählte, „Alle fallen lassen“
  function fallenLassen(id) {
    const schwebend = objekte.filter((o) => o.fest && (!id || o.id === id));
    if (!schwebend.length) return;
    call('/objekt', { aktion: 'fallen', name: id || 'alle' });
    toast(id ? `${schwebend[0].name} fällt` : 'Alles, was in der Luft stand, fällt');
  }
  $('kol-alle-fallen').addEventListener('click', () => fallenLassen());
  $('kol-fallen').addEventListener('click', () => gewaehlt && fallenLassen(gewaehlt));
  function zeigeFallen() {
    $('kol-alle-fallen').hidden = !objekte.some((o) => o.fest);
    $('kol-fallen').hidden = !(gewaehlt && objekte.some((o) => o.id === gewaehlt && o.fest));
  }
  const wurfart = () => (panel.querySelector('input[name="kol-wurfart"]:checked') || {}).value || 'schwung';
  const winkel = $('kol-winkel');
  function setWinkel(g) {
    wurfWinkel = Math.min(60, Math.max(0, Math.round(g)));
    winkel.value = String(wurfWinkel);
    winkel.style.setProperty('--_fill', `${(wurfWinkel / 60) * 100}%`);
    $('kol-winkel-wert').textContent = `${wurfWinkel}°`;
  }
  winkel.addEventListener('input', () => setWinkel(Number(winkel.value)));
  // Auswahl wie in CAD: das zuletzt angefasste Ding trägt den blauen Pfeil; Entf oder „Wegräumen“ nimmt es weg
  const auswahlBox = $('kol-auswahl');
  function waehle(id) {
    gewaehlt = id || null;
    const o = gewaehlt && objekte.find((x) => x.id === gewaehlt);
    auswahlBox.hidden = !o;
    if (o) $('kol-auswahl-name').textContent = o.name;
    zeigeFallen();
  }
  function wegraeumen() {
    if (!gewaehlt) return;
    const id = gewaehlt;
    if (drag && (drag.art === 'ding' || drag.art === 'schleuder') && drag.id === id) { drag.abbruch = true; endDrag(false); }
    waehle(null);
    call('/objekt', { aktion: 'parken', name: id });
  }
  $('kol-weg').addEventListener('click', wegraeumen);
  // 48 gleichmäßig verteilte Stöße in einer unsichtbaren Welt – Trainingsdaten und Vorher/Nachher-Vergleich
  $('kol-reihe').addEventListener('click', () => { if (window.duckpilot && window.duckpilot.showView) window.duckpilot.showView('training', 'stossreihe'); });
  window.addEventListener('keydown', (e) => {
    if (!on || !gewaehlt || (e.key !== 'f' && e.key !== 'F') || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.target.closest('input, textarea, select, [contenteditable]')) return;
    e.preventDefault();
    fallenLassen(gewaehlt);
  });
  stageEl.addEventListener('dblclick', (e) => {
    if (!on || !hover || hover.art !== 'ding') return;
    const o = objekte.find((x) => x.id === hover.id);
    if (!o || !o.fest) return;
    e.preventDefault(); e.stopPropagation();
    fallenLassen(o.id);
  }, { capture: true });
  window.addEventListener('keydown', (e) => {
    if (!on || !gewaehlt || (e.key !== 'Delete' && e.key !== 'Backspace')) return;
    if (e.target.closest('input, textarea, select, [contenteditable]')) return;
    e.preventDefault();
    wegraeumen();
  });
  setWinkel(wurfWinkel);
  const setShift = (v) => { if (shift !== v) { shift = v; if (drag && drag.art === 'ding' && !drag.pfeil) reanchor(); } };
  window.addEventListener('keydown', (e) => { if (on && e.key === 'Shift') setShift(true); });
  window.addEventListener('keydown', (e) => {   // Zielen abbrechen: Ding bleibt, wo es war
    if (on && e.key === 'Escape' && drag && drag.art === 'schleuder') { e.preventDefault(); e.stopPropagation(); drag.abbruch = true; endDrag(false); }
  }, true);
  window.addEventListener('keyup', (e) => { if (e.key === 'Shift') setShift(false); });
  window.addEventListener('blur', () => setShift(false));

  // ── Dinge zeichnen (Form und Maße kommen vom Server) ───────────────────
  function size3(o) {
    const g = o.groesse;
    return Array.isArray(g) ? g : [g, g, g];
  }
  function meshFor(o) {
    let m = meshes.get(o.id);
    if (m) return m;
    const [a, b, c] = size3(o);
    let geo;
    if (o.form === 'kugel') geo = new THREE.SphereGeometry(a, 24, 16);
    else if (o.form === 'zylinder') geo = new THREE.CylinderGeometry(a, a, (b || a) * 2, 24);   // Achse: Physik z → three y
    else geo = new THREE.BoxGeometry(a * 2, c * 2, b * 2);                                    // halbe Kanten x, y, z
    m = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ color: new THREE.Color(o.farbe), roughness: 0.55 }));
    m.castShadow = true;
    m.userData.kollision = o.id;
    group.add(m);
    meshes.set(o.id, m);
    return m;
  }
  // Lage der Dinge: aus dem Strom (solange sich etwas bewegt) und aus dem Status (ruhende Dinge, z. B. frisch
  // hingelegt – sonst gäbe es sie in der Ansicht erst, wenn sich etwas bewegt, und man könnte sie nicht anfassen)
  function applyObjekte(list) {
    for (const o of list) {
      if (!Array.isArray(o.pos) || !Array.isArray(o.quat)) continue;
      const m = meshFor(o);
      m.visible = !!o.im_raum;
      const [x, y, z] = o.pos, [w, qx, qy, qz] = o.quat;
      m.position.set(x, z, -y);
      m.quaternion.set(qx, qz, -qy, w);
    }
  }
  let ruheT = 0;
  function onObjekte(msg) {
    const list = msg.objekte || [];
    applyObjekte(list);
    // Der Strom endet, kurz bevor alles ganz still liegt: danach einmal die Endlage holen
    clearTimeout(ruheT);
    ruheT = setTimeout(() => refresh(true), 700);
    if (list.length && list.map((o) => o.id).join(',') !== paletteKey) renderPalette(list);
    else if (list.length) objekte = list;            // aktuelle Lage für Pfeil, Bogen und Maße
    if (gewaehlt && list.some((o) => o.id === gewaehlt && !o.im_raum)) waehle(null);
    zeigeFallen();
    if (msg.hand) serverHeld = msg.hand.gehalten || null;
    zugInfo = msg.zug && msg.zug.aktiv ? msg.zug : null;
  }

  // ── Zeiger: was liegt darunter? ───────────────────────────────────────
  const ray = new THREE.Raycaster();
  const cam = () => (scene.mode === 'entenblick' ? scene.povCam : scene.camera);
  function camAxes() {
    const c = cam();
    const fwd = c.getWorldDirection(new THREE.Vector3());
    const flat = new THREE.Vector3(fwd.x, 0, fwd.z);
    if (flat.lengthSq() < 1e-6) flat.set(0, 0, -1);
    flat.normalize();
    return { fwd, flat };
  }
  function aim(e) {
    const rect = scene.canvas.getBoundingClientRect();
    const ndc = new THREE.Vector2(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
    ray.setFromCamera(ndc, cam());
  }
  function hitPlane(point3, normal3) {          // Strahl ∩ Ebene → Physik-Punkt
    const d = ray.ray.direction, o = ray.ray.origin;
    const den = d.dot(normal3);
    if (Math.abs(den) < 1e-4) return null;
    const t = point3.clone().sub(o).dot(normal3) / den;
    if (t <= 0 || t > 30) return null;
    return P(o.clone().addScaledVector(d, t));
  }
  const clampZ = (p) => (p ? { ...p, z: Math.min(Z_MAX, Math.max(Z_MIN, p.z)) } : p);
  function floorAt() { return hitPlane(new THREE.Vector3(0, 0, 0), new THREE.Vector3(0, 1, 0)); }
  function pick() {                              // Reihenfolge: blauer Pfeil, Dinge, Ente
    if (pfeil.visible) {
      const hp = ray.intersectObject(pfeil, true)[0];
      if (hp && gewaehlt) return { art: 'pfeil', id: gewaehlt };
    }
    const hd = ray.intersectObjects([...meshes.values()].filter((m) => m.visible), false)[0];
    const duck = scene.duck && scene.duck.root;
    const he = duck ? ray.intersectObject(duck, true)[0] : null;
    if (hd && (!he || hd.distance <= he.distance)) return { art: 'ding', id: hd.object.userData.kollision, c: hd.object.position.clone() };
    if (he) {
      let o = he.object, koerper = null;
      while (o && o !== duck) { if (o.name && !o.isMesh) { koerper = o.name; break; } o = o.parent; }
      return { art: 'ente', p: P(he.point), koerper };
    }
    return null;
  }
  function setHover(hv) {
    for (const [id, m] of meshes) m.material.emissive.setHex(hv && hv.art === 'ding' && hv.id === id ? 0x333333 : 0x000000);
    pfeilMat.opacity = hv && hv.art === 'pfeil' ? 1 : 0.85;
    hover = hv;
    anfass.visible = !!(hv && hv.art === 'ente' && !drag);
    if (anfass.visible) anfass.position.copy(T(hv.p));
    stageEl.classList.toggle('stage--greifbar', !!hv && !drag);
  }
  const offStage = (e) => e.target.closest('.kol-panel, .view-tools, .hud-tele, .talk');
  const touchy = (e) => e.pointerType === 'touch' || e.pointerType === 'pen';

  function sendThrottled(msg, force = false) {
    const now = performance.now();
    if (!force && now - sentAt < 1000 / SEND_HZ) return;
    sentAt = now;
    send(msg);
  }
  const dingPos = (id) => { const o = objekte.find((x) => x.id === id); return o ? { x: o.pos[0], y: o.pos[1], z: o.pos[2] } : null; };

  // ── Ziehen ────────────────────────────────────────────────────────────
  function startZug(hv) {
    const ax = camAxes();
    drag = { art: 'zug', ebene: T(hv.p), normal: ax.fwd.clone(), start: hv.p, ziel: hv.p };
    send({ type: 'kollision_zug_start', x: hv.p.x, y: hv.p.y, z: hv.p.z, ...(hv.koerper ? { koerper: hv.koerper } : {}) });
  }
  function startDing(hv, senkrecht) {
    const c = hv.art === 'pfeil' ? dingPos(hv.id) : P(hv.c);
    if (!c) return;
    waehle(hv.id); auswahl = hv.id; renderPalette(objekte);
    const o = objekte.find((x) => x.id === hv.id) || {};
    if (wurfart() === 'ziel' && !senkrecht) {
      // Schleuder: Das Ding bleibt, wo es ist; man zieht nach hinten, der Bogen zeigt, wo es hinfliegt
      drag = { art: 'schleuder', id: hv.id, anker: { ...c }, zug: { ...c }, warFest: !!o.fest, masse: Number(o.masse) || 0.1 };
    } else {
      drag = { art: 'ding', id: hv.id, pfeil: senkrecht, start: { ...c }, ziel: { ...c }, flick: [] };
      reanchor();
    }
    send({ type: 'kollision_hand', aus: true });                       // neu erscheinen lassen: direkt im Ding
    send({ type: 'kollision_hand', x: c.x, y: c.y, z: Math.max(Z_MIN, c.z) });
    send({ type: 'kollision_greifen', name: hv.id });
  }
  // Ebene fürs Ding: waagrecht in seiner Höhe, oder senkrecht (blaue Achse) quer zur Kamera
  function reanchor() {
    if (!drag || drag.art !== 'ding') return;
    const at = drag.ziel;
    drag.senkrecht = drag.pfeil || shift;
    drag.ebene = T(at);
    drag.normal = drag.senkrecht ? camAxes().flat : new THREE.Vector3(0, 1, 0);
    drag.achseXY = { x: at.x, y: at.y };
    drag.flick = [];
  }
  function dragMove() {
    if (drag.art === 'schleuder') {
      const p = hitPlane(T(drag.anker), new THREE.Vector3(0, 1, 0));
      if (p) drag.zug = { x: p.x, y: p.y, z: drag.anker.z };
      return;                                    // die Hand bleibt am Ding – es bewegt sich erst beim Loslassen
    }
    if (drag.art === 'zug') {
      const p = clampZ(hitPlane(drag.ebene, drag.normal));
      if (!p) return;
      drag.ziel = p;
      sendThrottled({ type: 'kollision_zug', x: p.x, y: p.y, z: p.z });
      return;
    }
    let p = hitPlane(drag.ebene, drag.normal);
    if (!p) return;
    if (drag.senkrecht) p = { x: drag.achseXY.x, y: drag.achseXY.y, z: p.z };   // nur die blaue Achse
    else p.z = drag.ebene.y;                                                    // bleibt in seiner Höhe
    p = clampZ(p);
    drag.ziel = p;
    drag.flick.push({ t: performance.now(), p });
    if (drag.flick.length > 24) drag.flick.shift();
    sendThrottled({ type: 'kollision_hand', x: p.x, y: p.y, z: p.z });
  }
  // Wurf aus den letzten 150 ms: über den Boden → Richtung und Tempo, Winkel vom Regler; senkrecht → hochwerfen
  function throwV() {
    if (!drag || drag.art !== 'ding') return { x: 0, y: 0, z: 0 };
    const now = performance.now();
    // 150 ms Schwung; erst 100 ms ohne Bewegung gilt als „angehalten“ – auch bei langsamer 3D-Ansicht (20 Bilder/s)
    const w = drag.flick.filter((f) => now - f.t <= 150);
    if (w.length < 2 || now - w[w.length - 1].t > 100) return { x: 0, y: 0, z: 0 };
    const a = w[0].p, b = w[w.length - 1].p, dt = (w[w.length - 1].t - w[0].t) / 1000;
    if (dt <= 0.005) return { x: 0, y: 0, z: 0 };
    if (drag.senkrecht) return { x: 0, y: 0, z: Math.max(-WURF_MAX, Math.min(WURF_MAX, ((b.z - a.z) / dt) * WURF_GAIN)) };
    const vx = (b.x - a.x) / dt, vy = (b.y - a.y) / dt;
    const flach = Math.hypot(vx, vy);
    const tempo = Math.min(WURF_MAX, flach * WURF_GAIN);
    if (flach < 1e-6) return { x: 0, y: 0, z: 0 };
    const r = (wurfWinkel * Math.PI) / 180;
    return { x: (vx / flach) * tempo * Math.cos(r), y: (vy / flach) * tempo * Math.cos(r), z: tempo * Math.sin(r) };
  }
  // werfen: mit Schwung losgelassen; abgelehnt: der Server hat Greifen/Anfassen nicht angenommen (nichts mehr senden)
  // Schleuder: zurückgezogen um L → Tempo L/ZIEL_ZUG_MAX · WURF_MAX in Gegenrichtung, Winkel vom Regler
  function schleuderV() {
    if (!drag || drag.art !== 'schleuder') return { x: 0, y: 0, z: 0 };
    const dx = drag.anker.x - drag.zug.x, dy = drag.anker.y - drag.zug.y;
    const L = Math.hypot(dx, dy);
    if (L < 0.01) return { x: 0, y: 0, z: 0 };
    const tempo = Math.min(1, L / ZIEL_ZUG_MAX) * WURF_MAX;
    const r = (wurfWinkel * Math.PI) / 180;
    return { x: (dx / L) * tempo * Math.cos(r), y: (dy / L) * tempo * Math.cos(r), z: tempo * Math.sin(r) };
  }
  function endDrag(werfen = true, abgelehnt = false) {
    if (!drag) return;
    if (drag.art === 'zug') { if (!abgelehnt) send({ type: 'kollision_zug_ende' }); }
    else if (drag.art === 'schleuder') {
      const v = werfen && !drag.abbruch ? schleuderV() : { x: 0, y: 0, z: 0 };
      if (!abgelehnt && Math.hypot(v.x, v.y, v.z) >= WURF_AB) {
        send({ type: 'kollision_loslassen', v: [v.x, v.y, v.z].map((n) => Math.round(n * 1000) / 1000) });
      } else if (!abgelehnt && (drag.warFest || festSw.checked)) {
        send({ type: 'kollision_loslassen', fest: true });            // nicht geworfen: bleibt stehen wie vorher
      }
      send({ type: 'kollision_hand', aus: true });
      feder.visible = anfass.visible = false;
    }
    else {
      const v = werfen ? throwV() : { x: 0, y: 0, z: 0 };
      if (!abgelehnt && Math.hypot(v.x, v.y, v.z) >= WURF_AB) {
        send({ type: 'kollision_loslassen', v: [v.x, v.y, v.z].map((n) => Math.round(n * 1000) / 1000) });
      } else if (!abgelehnt && werfen && festSw.checked) {
        send({ type: 'kollision_loslassen', fest: true });            // bleibt in der Luft stehen
      }
      send({ type: 'kollision_hand', aus: true });   // Hand weg; ein noch gehaltenes Ding fällt dabei (ablegen)
    }
    drag = null;
    stageEl.classList.remove('stage--ziehen');
    feder.visible = zielPunkt.visible = achse.visible = false;
  }

  function move(e) {
    if (!on || placing) return;
    pointer = { clientX: e.clientX, clientY: e.clientY };
    if (touchy(e) && !e.buttons && !drag) return;
    if (offStage(e) && !drag) { setHover(null); return; }
    aim(e);
    if (drag) { dragMove(); return; }
    setHover(pick());
  }
  function down(e) {
    if (!on || e.button !== 0 || offStage(e)) return;
    aim(e);
    if (placing) {
      e.stopPropagation(); e.preventDefault();
      const p = floorAt();
      if (p) call('/objekt', { aktion: 'setzen', name: placing, pos: [p.x, p.y] });
      placing = null;
      stageEl.classList.remove('stage--legen');
      $('kol-hint').textContent = '';
      renderPalette(objekte);
      return;
    }
    const hv = pick();
    if (!hv) return;                                  // ins Leere: nichts (die Kamera dreht mit der rechten Taste)
    e.stopPropagation(); e.preventDefault();
    try { stageEl.setPointerCapture(e.pointerId); } catch { /* egal */ }
    pointer = { clientX: e.clientX, clientY: e.clientY };
    setHover(null);
    if (hv.art === 'ente') startZug(hv);
    else startDing(hv, hv.art === 'pfeil');
    stageEl.classList.add('stage--ziehen');
  }
  function up() {
    if (!on || !drag) return;
    endDrag(true);
  }
  stageEl.addEventListener('pointermove', move, { capture: true });
  stageEl.addEventListener('pointerdown', down, { capture: true });
  stageEl.addEventListener('pointerup', up, { capture: true });
  stageEl.addEventListener('pointercancel', () => endDrag(false));
  stageEl.addEventListener('pointerleave', (e) => { if (e.pointerType === 'mouse' && !drag) setHover(null); });
  stageEl.addEventListener('contextmenu', (e) => { if (on) e.preventDefault(); });   // rechte Taste dreht die Kamera

  // ── je Bild: Hilfslinien, Pfeil, Bogen, Hinweis am Zeiger ─────────────
  function bogenZeigen(start, v, r) {
    const pos = bogenGeo.attributes.position.array;
    let end = start, n = 0, weit = 0;
    for (; n < BOGEN_N; n++) {
      const t = n * 0.04;
      const q = { x: start.x + v.x * t, y: start.y + v.y * t, z: start.z + v.z * t - 0.5 * G * t * t };
      const unten = q.z < r && n > 0;
      if (unten) { const k = (end.z - r) / Math.max(1e-6, end.z - q.z); end = { x: end.x + (q.x - end.x) * k, y: end.y + (q.y - end.y) * k, z: r }; }
      else end = q;
      pos[n * 3] = end.x; pos[n * 3 + 1] = end.z; pos[n * 3 + 2] = -end.y;
      if (unten) { n++; break; }
    }
    bogenGeo.setDrawRange(0, n);
    bogenGeo.attributes.position.needsUpdate = true;
    bogen.computeLineDistances();
    bogen.visible = true;
    landung.position.set(end.x, 0.003, -end.y);
    landung.visible = true;
    weit = Math.hypot(end.x - start.x, end.y - start.y);
    return weit;
  }
  // Bogen bis zum Boden – oder bis er die Ente trifft (Strahl je Bogenstück gegen ihr 3D-Modell)
  const bogenRay = new THREE.Raycaster();
  function bogenMitTreffer(start, v, r) {
    const pos = bogenGeo.attributes.position.array;
    const duck = scene.duck && scene.duck.root;
    let prev = start, n = 0, treffer = null;
    pos[0] = start.x; pos[1] = start.z; pos[2] = -start.y; n = 1;
    for (let i = 1; i < BOGEN_N; i++) {
      const t = i * 0.03;
      let q = { x: start.x + v.x * t, y: start.y + v.y * t, z: start.z + v.z * t - 0.5 * G * t * t };
      if (duck) {
        const a = T(prev), b = T(q), dir = b.clone().sub(a), len = dir.length();
        bogenRay.set(a, dir.normalize()); bogenRay.far = len;
        const h = bogenRay.intersectObject(duck, true)[0];
        if (h) {
          const tt = t - 0.03 + 0.03 * (h.distance / len);
          treffer = { p: P(h.point), tempo: Math.hypot(v.x, v.y, v.z - G * tt) };
          q = treffer.p;
        }
      }
      const amBoden = !treffer && q.z < r;
      if (amBoden) { const k = (prev.z - r) / Math.max(1e-6, prev.z - q.z); q = { x: prev.x + (q.x - prev.x) * k, y: prev.y + (q.y - prev.y) * k, z: r }; }
      pos[n * 3] = q.x; pos[n * 3 + 1] = q.z; pos[n * 3 + 2] = -q.y; n++;
      prev = q;
      if (treffer || amBoden) break;
    }
    bogenGeo.setDrawRange(0, n);
    bogenGeo.attributes.position.needsUpdate = true;
    bogen.computeLineDistances();
    bogen.visible = true;
    if (treffer) { anfass.position.copy(T(treffer.p)); anfass.visible = true; landung.visible = false; }
    else { landung.position.set(prev.x, 0.003, -prev.y); landung.visible = true; }
    return { treffer, weit: Math.hypot(prev.x - start.x, prev.y - start.y) };
  }
  function teilAn(p) {                            // grob nach Höhe über ihren Füßen: Kopf, Rumpf, Bein
    const st = state() || {};
    const h = (Array.isArray(st.body) && Number(st.body[0])) || 0.12;
    return p.z > h + 0.05 ? 'Kopf' : p.z > h - 0.04 ? 'Rumpf' : 'Bein';
  }
  const cm = (m) => `${Math.round(m * 100)} cm`;
  const unten = new THREE.Raycaster();
  function landeHoehe(at) {                      // worauf es fiele: Boden oder Möbel senkrecht darunter (m)
    if (!scene.worldGroup) return 0;
    unten.set(T(at), new THREE.Vector3(0, -1, 0));
    // nur feste Flächen: Linien und Punkte (Raster, Umrisse) treffen Raycaster mit großzügiger Toleranz
    const hit = unten.intersectObject(scene.worldGroup, true).find((h) => h.object.isMesh && h.object.visible && h.point.y < at.z - 0.005);
    return hit ? Math.max(0, hit.point.y) : 0;
  }
  const komma = (x, n = 1) => x.toFixed(n).replace('.', ',');
  const TEIL = { kopf: 'Kopf', rumpf: 'Rumpf', bein_links: 'linkes Bein', bein_rechts: 'rechtes Bein' };
  function frame() {
    requestAnimationFrame(frame);
    if (!on) { mass.hidden = true; return; }
    let text = '';
    bogen.visible = landung.visible = false;
    lot.visible = bodenRing.visible = false;
    // blauer Pfeil über dem gewählten Ding (nicht beim Ziehen über den Boden – dann zeigt die Achse)
    const gp = gewaehlt && dingPos(gewaehlt);
    pfeil.visible = !!(gp && (!drag || (drag.art !== 'ding' && drag.art !== 'schleuder')));
    const groesse = (id) => { const o = objekte.find((x) => x.id === id); return o && Array.isArray(o.halbachsen) ? o.halbachsen : [0.03, 0.03, 0.03]; };
    if (pfeil.visible) pfeil.position.copy(T({ ...gp, z: gp.z + groesse(gewaehlt)[2] + 0.01 }));
    const gpo = gp && objekte.find((o) => o.id === gewaehlt);
    if (pfeil.visible && gpo && gpo.fest) {        // steht in der Luft: Lot und Ring zeigen, wie hoch
      const boden = landeHoehe(gp);
      setLine(lot, gp, { x: gp.x, y: gp.y, z: boden });
      bodenRing.position.set(gp.x, boden + 0.002, -gp.y); bodenRing.visible = true;
    }
    if (drag && drag.art === 'schleuder') {
      const a = drag.anker;
      setLine(feder, a, drag.zug);                // Gummiband nach hinten
      feder.material.color.set(ORANGE);
      zielPunkt.position.copy(T(drag.zug)); zielPunkt.visible = true;
      anfass.visible = false;
      const v = schleuderV();
      const tempo = Math.hypot(v.x, v.y, v.z);
      if (tempo >= WURF_AB) {
        const { treffer, weit } = bogenMitTreffer(a, v, groesse(drag.id)[2]);
        text = `Zielwurf ${komma(tempo)} m/s · ${wurfWinkel}° · `
          + (treffer ? `trifft ${teilAn(treffer.p)} mit ${komma(treffer.tempo)} m/s (${komma(drag.masse * treffer.tempo, 2)} N·s)` : `landet in ${komma(weit, 2)} m`);
      } else text = 'Nach hinten ziehen zum Zielen · Esc bricht ab';
    } else if (drag && drag.art === 'zug') {
      const a = zugInfo && zugInfo.anker ? { x: zugInfo.anker[0], y: zugInfo.anker[1], z: zugInfo.anker[2] } : drag.start;
      setLine(feder, a, drag.ziel);
      anfass.position.copy(T(a)); anfass.visible = true;
      zielPunkt.position.copy(T(drag.ziel)); zielPunkt.visible = true;
      const f = zugInfo ? Number(zugInfo.kraft_n) || 0 : 0;
      feder.material.color.set(f >= zugMax() * 0.98 ? ORANGE : HELL);
      const teil = zugInfo && (zugInfo.teil_name || TEIL[zugInfo.teil]);
      text = `${teil ? teil + ': ' : ''}Zug ${komma(f)} N${f >= zugMax() * 0.98 ? ' (am Anschlag)' : ''}`;
    } else if (drag && drag.art === 'ding') {
      const held = serverHeld === drag.id ? dingPos(drag.id) : null;
      const at = held || drag.ziel;
      const boden = landeHoehe(at);
      setLine(lot, at, { x: at.x, y: at.y, z: boden });
      bodenRing.position.set(at.x, boden + 0.002, -at.y); bodenRing.visible = true;
      if (drag.senkrecht) setLine(achse, { x: at.x, y: at.y, z: 0 }, { x: at.x, y: at.y, z: Math.max(at.z + 0.25, 0.4) });
      else achse.visible = false;
      const v = throwV();
      const tempo = Math.hypot(v.x, v.y, v.z);
      const weg = Math.hypot(at.x - drag.start.x, at.y - drag.start.y);
      text = `Höhe ${cm(at.z)}${drag.senkrecht ? ' · senkrecht' : weg > 0.01 ? ` · ${cm(weg)} verschoben` : ''}`
        + (festSw.checked ? ' · loslassen: bleibt hier' : boden > 0.02 ? ` · landet auf ${cm(boden)}` : '');
      if (held && tempo >= WURF_AB) {
        const weit = bogenZeigen(held, v, groesse(drag.id)[2]);
        const grad = Math.round((Math.atan2(v.z, Math.hypot(v.x, v.y)) * 180) / Math.PI);
        text = `Wurf ${komma(tempo)} m/s · ${grad}° · landet in ${komma(weit, 2)} m`;
      }
    } else if (hover) {
      text = hover.art === 'ente' ? 'Ziehen zieht die Ente an dieser Stelle'
        : hover.art === 'pfeil' ? 'Ziehen hebt oder senkt es'
          : `${(objekte.find((o) => o.id === hover.id) || {}).name || 'Ding'}${(objekte.find((o) => o.id === hover.id) || {}).fest ? ' (steht in der Luft)' : ''}: ${wurfart() === 'ziel' ? 'nach hinten ziehen zielt, loslassen wirft' : 'ziehen verschiebt, mit Schwung loslassen wirft'}${hover.id === gewaehlt ? ' · Entf räumt weg' : ''}`;
    }
    if (text && pointer) {
      const sr = stageEl.getBoundingClientRect();
      mass.style.left = `${pointer.clientX - sr.left + 16}px`;
      mass.style.top = `${pointer.clientY - sr.top + 16}px`;
      if (mass.textContent !== text) mass.textContent = text;
      mass.hidden = false;
    } else mass.hidden = true;
  }
  requestAnimationFrame(frame);

  // ── Stopp-Fenster nach einem Sturz (überall in der App) ──────────────
  const box = $('stopp-fenster');
  function closeWindow() {
    clearInterval(sf && sf.timer);
    sf = null;
    box.hidden = true;
    listener() && listener().closeWindow && listener().closeWindow();
  }
  function onEvent(ev) {
    if (ev.type === 'stopp_fenster') {
      const dauer = Number(ev.dauer) || 3;
      clearInterval(sf && sf.timer);
      sf = { ende: performance.now() + dauer * 1000 };
      $('sf-text').textContent = `Sie steht in ${dauer} Sekunden selbst auf. „Stopp“ sagen oder „Liegen lassen“ drücken hält sie liegen.`;
      const tick = () => {
        const s = Math.max(0, Math.ceil((sf.ende - performance.now()) / 1000));
        $('sf-count').textContent = `${s} s`;
        if (s <= 0) clearInterval(sf.timer);
      };
      tick();
      sf.timer = setInterval(tick, 250);
      box.hidden = false;
      const l = listener();
      if (l && l.supported && l.openWindow) l.openWindow(dauer);  // Mikrofon kurz offen – „Stopp“ geht ohne Taste
    } else if (ev.type === 'stopp_fenster_ende') {
      closeWindow();
      if (ev.grund) toast(ev.grund);
    } else if (ev.type === 'kollision' && ev.message) {
      toast(ev.message, true);
      if (drag && (drag.art === 'ding' || drag.art === 'schleuder') && serverHeld !== drag.id) endDrag(false, true);   // Greifen ging nicht
      else if (drag && drag.art === 'zug' && !zugInfo) endDrag(false, true);            // Anfassen ging nicht
    }
  }
  $('sf-stop').addEventListener('click', () => { estop(); closeWindow(); });

  function onStatus(msg) {
    status = { ...status, ...msg };
    if (Array.isArray(msg.objekte)) {
      applyObjekte(msg.objekte);
      if (gewaehlt && msg.objekte.some((o) => o.id === gewaehlt && !o.im_raum)) waehle(null);
    }
    render();
  }
  // nach dem Start, einem Körperwechsel oder wenn die Physik fertig geladen ist: neu fragen
  let refreshAt = 0;
  function refresh(sofort = false) {
    const now = performance.now();
    if (!sofort && now - refreshAt < 500) return;
    refreshAt = now;
    api('/api/kollision').then((r) => { if (r && r.ok) onStatus(r); }).catch(() => {});
  }
  refresh();

  const debug = () => ({ on, placing, hover: hover && hover.art, drag: drag && drag.art, gewaehlt,
    dinge: [...meshes].filter(([, m]) => m.visible).map(([id, m]) => [id, P(m.position)]),
    pfeil: pfeil.visible ? P(pfeil.position) : null, landung: (x, y, z) => landeHoehe({ x, y, z }) });
  return { onStatus, onObjekte, onEvent, refresh, on: () => on, off: () => { if (on) set(false); }, THREE, debug };   // THREE/debug: für Tests
}
