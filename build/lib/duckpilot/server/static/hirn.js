// Zustand → Hirnaktivität: das Erfahrungsnetz als lebendiger Graph.
// Knoten = Dinge aus ihrer Welt, Linien = gelernte Verknüpfungen (dicker = stärker). Was gerade aktiv ist, leuchtet;
// frisch gestärkte Verbindungen blitzen kurz auf. Klick auf einen Knoten zeigt, womit er verknüpft ist und warum.
// Farben nach Gruppe (validiert, alle Paare): Wer & Wo blau, Erleben türkis, Gefühle orange, Rahmen grau – dazu
// immer der Name am Knoten (Farbe trägt nie allein die Bedeutung). Namen nur über textContent bzw. fillText.

const GRUPPE = {
  person: 'wer', ort: 'wer', ding: 'erleben', taetigkeit: 'erleben', sinn: 'erleben',
  gefuehl: 'gefuehl', rueckmeldung: 'gefuehl', zeit: 'rahmen',
};
// Farben aus den Tokens (ds/tokens.css, --cat-*), damit Legende und Graph nie auseinanderlaufen
const FARBE = { wer: '#3987e5', erleben: '#199e70', gefuehl: '#d95926', rahmen: '#8d8d8d' };
try {
  const cs = getComputedStyle(document.documentElement);
  for (const k of Object.keys(FARBE)) FARBE[k] = cs.getPropertyValue(`--cat-${k}`).trim() || FARBE[k];
} catch { /* ohne DOM (Tests) bleiben die Vorgaben */ }
const ART = { person: 'Person', ort: 'Ort', ding: 'Ding', taetigkeit: 'Tätigkeit', sinn: 'Sinneseindruck', gefuehl: 'Gefühl', rueckmeldung: 'Rückmeldung', zeit: 'Zeit' };

import { herkunftListe, herkunftName, passt } from './herkunft.js';
import { uebersetzeText } from './i18n.js';

// Namen, die Knowlin selbst vergibt (Tageszeit, Gefühle, Erlebnisse), in der Oberflächensprache zeigen (seit 0.38.16);
// Namen von Menschen und Dingen stehen nicht im Katalog und bleiben, wie sie sind.
const namenCache = new Map();
const zeigName = (n) => {
  if (!namenCache.has(n)) namenCache.set(n, uebersetzeText(n) || n);
  return namenCache.get(n);
};

export function initHirn(h) {
  const { $, el, api, toast } = h;
  let filter = '';                    // Herkunft (seit 0.38.10): '' alle, 'kopf', Modul, 'sim', 'echt', 'unbekannt'
  const wach = () => { const c = h.getConfig ? h.getConfig() : null; return c && c.im_koerper ? c.modul : null; };
  const canvas = $('brain');
  if (!canvas) return { update() {}, show() {} };
  const ctx = canvas.getContext('2d');
  const pos = new Map();              // id → {x, y, vx, vy}
  let data = { knoten: [], kanten: [] };
  let running = false;
  let hover = null;
  let selected = null;
  const flashes = new Map();          // "a|b" → Zeitpunkt
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  // Drehen und Zoomen wie in 3D (seit 0.37.12, Wunsch des Maintainers): Ziehen dreht, Mausrad/zwei Finger zoomen; nach ein
  // paar Sekunden Ruhe kehrt die Ansicht sanft zurück. Die Knoten haben dafür eine Tiefe (z).
  const ansicht = { yaw: 0, pitch: 0, zoom: 1 };
  let zuletztBewegt = 0;
  const RUECKKEHR_MS = 4000;
  const schirm = new Map();          // id → {x, y, f} – projiziert, fürs Treffen per Maus
  // Bei Knowlin selbst (seit 0.38.10, Wunsch des Maintainers): das Netz lebt wie die Mind-Form der Startseite – es dreht sich
  // langsam von selbst, die Knoten schweben, Impulse laufen die Verknüpfungen entlang, dahinter eine weiche Hülle.
  // Im Körper bleibt es ruhig und sachlich; mit „Bewegung reduzieren“ steht es still.
  const kopfModus = () => document.body.classList.contains('im-kopf');
  const lebendig = () => !reduced && kopfModus();
  // Aktivität sanft statt blitzend (Hinweis aus dem Test 5.11.): angezeigter Wert gleitet zum gemeldeten – bei Knowlin langsam
  const zeigAkt = new Map();
  function aktVon(k) {
    const alt = zeigAkt.has(k.id) ? zeigAkt.get(k.id) : k.akt || 0;
    const neu = reduced ? k.akt || 0 : alt + ((k.akt || 0) - alt) * (kopfModus() ? 0.02 : 0.15);
    zeigAkt.set(k.id, neu);
    return neu;
  }
  const impulse = [];                // {a, b, t0, dauer}
  const glut = new Map();            // id → Zeitpunkt, an dem ein Impuls ankam
  let akzent = null;
  function farbenKopf() {
    if (akzent) return akzent;
    const s = getComputedStyle(canvas);
    akzent = { voll: s.getPropertyValue('--accent').trim() || 'orange', weich: s.getPropertyValue('--accent-soft').trim() || 'transparent' };
    return akzent;
  }

  let lastW = 0, lastH = 0;
  function size() {
    const r = canvas.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    if (canvas.width !== Math.round(r.width * dpr)) { canvas.width = Math.round(r.width * dpr); canvas.height = Math.round(r.height * dpr); }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    // Fläche hat sich geändert (Seite war verborgen, Fenster breiter): Knoten mitziehen statt links zu kleben
    if (r.width > 40 && r.height > 40 && (Math.abs(r.width - lastW) > 2 || Math.abs(r.height - lastH) > 2)) {
      if (lastW > 40 && lastH > 40) {
        for (const p of pos.values()) { p.x *= r.width / lastW; p.y *= r.height / lastH; }
      } else {
        for (const p of pos.values()) { p.x = r.width / 2 + (Math.random() - 0.5) * r.width * 0.6; p.y = r.height / 2 + (Math.random() - 0.5) * r.height * 0.6; }
      }
      lastW = r.width; lastH = r.height;
    }
    return [r.width, r.height];
  }

  function update(msg) {
    if (!msg || msg.type !== 'erfahrung') return;
    data = msg;
    const [w, hgt] = size();
    for (const k of data.knoten || []) {
      if (!pos.has(k.id)) pos.set(k.id, { x: w / 2 + (Math.random() - 0.5) * w * 0.6, y: hgt / 2 + (Math.random() - 0.5) * hgt * 0.6, z: (Math.random() - 0.5) * 200, vx: 0, vy: 0, vz: 0 });
    }
    const ids = new Set((data.knoten || []).map((k) => k.id));
    for (const id of [...pos.keys()]) if (!ids.has(id)) pos.delete(id);
    const now = performance.now();
    for (const e of data.kanten || []) if (e.neu) flashes.set(`${e.a}|${e.b}`, now);
    renderMeta();
    renderPick();
    renderFilter();
    if (!running && visible()) loop();
  }

  // Filter nach Herkunft: nur, was es im Netz gibt
  const filterSel = $('brain-herkunft');
  if (filterSel) filterSel.addEventListener('change', () => { filter = filterSel.value; if (visible() && !running) loop(); });
  function renderFilter() {
    if (!filterSel) return;
    const namen = data.herkuenfte || {};
    const da = new Set();
    for (const k of data.knoten || []) for (const id of Object.keys(k.herkunft || {})) da.add(id);
    const module = [...new Set([...da].map((i) => i.split(':')[0]))];
    const opts = [['', 'Alle Herkünfte'], ...module.map((m) => [m, m === 'kopf' ? herkunftName('kopf', namen) : namen[m] || m])];
    if ([...da].some((i) => i.endsWith(':sim'))) opts.push(['sim', 'nur Simulator']);
    if ([...da].some((i) => i.endsWith(':echt'))) opts.push(['echt', 'nur echte Roboter']);
    if ((data.knoten || []).some((k) => !Object.keys(k.herkunft || {}).length)) opts.push(['unbekannt', 'Herkunft unbekannt']);
    const keep = filter;
    filterSel.replaceChildren(...opts.map(([v, t]) => { const o = el('option', null, uebersetzeText(t) || t); o.value = v; return o; }));
    filter = opts.some(([v]) => v === keep) ? keep : '';
    filterSel.value = filter;
  }

  function renderMeta() {
    const z = data.zahlen || { knoten: 0, verbindungen: 0 };
    const pr = data.praegung || {};
    const off = data.an === false;
    $('brain-empty').hidden = !(off || !(data.kanten || []).length);
    $('brain-empty').textContent = off ? 'Das Erfahrungsnetz lernt nur, wenn das Gedächtnis an ist (Charakter → Gedächtnis).'
      : 'Noch nichts erlebt – spiel mit ihr, lob sie, zeig ihr Orte. Was zusammen passiert, verknüpft sich hier.';
    const pText = Math.abs(pr.energie || 0) > 0.02 ? ` · Prägung: etwas ${pr.energie > 0 ? 'lebhafter' : 'ruhiger'} (${pr.grund})` : '';
    $('brain-note').textContent = off ? '' : `${z.knoten} Knoten · ${z.verbindungen} Verbindungen${pText}`;
  }

  function visible() { return !canvas.closest('.view').hidden && canvas.getClientRects().length > 0; }

  function step(w, hgt) {
    const nodes = data.knoten || [];
    const byId = new Map(nodes.map((k) => [k.id, k]));
    for (const a of nodes) {
      const pa = pos.get(a.id);
      if (pa.z === undefined) { pa.z = (Math.random() - 0.5) * 200; pa.vz = 0; }
      for (const b of nodes) {
        if (a === b) continue;
        const pb = pos.get(b.id);
        let dx = pa.x - pb.x; let dy = pa.y - pb.y; const dz = (pa.z || 0) - (pb.z || 0);
        if (Math.abs(dx) + Math.abs(dy) < 0.5) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; }   // genau übereinander: auseinanderschubsen
        const d2 = Math.max(80, dx * dx + dy * dy + dz * dz);
        const f = 2400 / d2;
        const d = Math.sqrt(d2);
        pa.vx += dx * f / d; pa.vy += dy * f / d; pa.vz += dz * f / d;
      }
      pa.vx += (w / 2 - pa.x) * 0.0012; pa.vy += (hgt / 2 - pa.y) * 0.002; pa.vz += -pa.z * 0.002;
    }
    for (const e of data.kanten || []) {
      const pa = pos.get(e.a); const pb = pos.get(e.b);
      if (!pa || !pb || !byId.has(e.a) || !byId.has(e.b)) continue;
      const dx = pb.x - pa.x; const dy = pb.y - pa.y; const dz = (pb.z || 0) - (pa.z || 0);
      const d = Math.max(1, Math.hypot(dx, dy, dz));
      const rest = 90 + 110 * (1 - e.w);
      const f = (d - rest) * 0.004 * (0.4 + e.w);
      pa.vx += dx / d * f; pa.vy += dy / d * f; pa.vz += dz / d * f;
      pb.vx -= dx / d * f; pb.vy -= dy / d * f; pb.vz -= dz / d * f;
    }
    for (const p of pos.values()) {
      p.vx *= 0.82; p.vy *= 0.82; p.vz = (p.vz || 0) * 0.82;
      p.x = Math.max(24, Math.min(w - 24, p.x + p.vx));
      p.y = Math.max(18, Math.min(hgt - 18, p.y + p.vy));
      p.z = Math.max(-260, Math.min(260, (p.z || 0) + p.vz));
    }
  }

  // Projektion: um die Mitte drehen (yaw um die Hochachse, pitch um die Querachse), Perspektive, Zoom
  function projizieren(p, w, hgt) {
    let X = p.x - w / 2, Y = p.y - hgt / 2, Z = p.z || 0;
    if (lebendig() && !p.fest) {                        // schweben: jeder Knoten mit eigener, langsamer Phase
      if (p.ph === undefined) p.ph = Math.random() * Math.PI * 2;
      const t = performance.now() / 1000;
      X += 7 * Math.sin(t * 0.55 + p.ph); Y += 6 * Math.cos(t * 0.43 + p.ph * 1.3); Z += 22 * Math.sin(t * 0.31 + p.ph * 0.7);
    }
    const cy = Math.cos(ansicht.yaw), sy = Math.sin(ansicht.yaw), cp = Math.cos(ansicht.pitch), sp = Math.sin(ansicht.pitch);
    const x1 = X * cy + Z * sy, z1 = -X * sy + Z * cy;
    const y2 = Y * cp - z1 * sp, z2 = Y * sp + z1 * cp;
    const brenn = kopfModus() ? 520 : 700;              // bei Knowlin etwas mehr Tiefe
    const f = ansicht.zoom * brenn / (brenn + z2);
    return { x: w / 2 + x1 * f, y: hgt / 2 + y2 * f, f, z: z2 };
  }

  function zurueck() {
    if (performance.now() - zuletztBewegt < RUECKKEHR_MS || ziehen) return;
    const lebt = lebendig();
    const t = performance.now() / 1000;
    const k = reduced ? 1 : lebt ? 0.015 : 0.06;
    // bei Knowlin: kein Stillstand, sondern ein langsames Kreisen wie Atmen
    ansicht.yaw += ((lebt ? 0.6 * Math.sin(t * 0.11) : 0) - ansicht.yaw) * k;
    ansicht.pitch += ((lebt ? 0.22 * Math.sin(t * 0.07 + 1) : 0) - ansicht.pitch) * k;
    ansicht.zoom += (1 - ansicht.zoom) * k;
  }

  // Weiche Hülle hinter dem Netz (wie die Mind-Form): Radius mit wenigen langsamen Wellen
  function huelle(cx, cy, R, t, lage) {
    const n = 64;
    const pkt = [];
    for (let i = 0; i < n; i++) {
      const th = (i / n) * Math.PI * 2;
      let r = 1;
      for (let j = 2; j <= 4; j++) r += (0.09 / j) * Math.sin(j * th + lage * 2.1 + t * (0.2 + 0.08 * j) * (j % 2 ? 1 : -1));
      pkt.push([cx + Math.cos(th) * R * r, cy + Math.sin(th) * R * r * 0.82]);
    }
    ctx.beginPath();
    const mitte = (a, b) => [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2];
    let m = mitte(pkt[n - 1], pkt[0]);
    ctx.moveTo(m[0], m[1]);
    for (let i = 0; i < n; i++) { m = mitte(pkt[i], pkt[(i + 1) % n]); ctx.quadraticCurveTo(pkt[i][0], pkt[i][1], m[0], m[1]); }
    ctx.closePath();
  }

  function kopfHintergrund(w, hgt, t) {
    const f = farbenKopf();
    const R = Math.min(w, hgt) * 0.46;
    for (let i = 0; i < 3; i++) {
      const cx = w / 2 + Math.sin(t * 0.13 + i * 2.1) * R * 0.08, cy = hgt / 2 + Math.cos(t * 0.11 + i * 1.7) * R * 0.06;
      const r = R * (1 - i * 0.16);
      const g = ctx.createRadialGradient(cx, cy, r * 0.1, cx, cy, r);
      g.addColorStop(0, f.weich); g.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.globalAlpha = 0.55 - i * 0.12;
      ctx.fillStyle = g; huelle(cx, cy, r, t, i); ctx.fill();   // nur weiches Licht, keine Umrisse („Kreise raus“)
    }
    ctx.globalAlpha = 1;
  }

  // Impulse: laufen die Verknüpfungen entlang – öfter auf starken und gerade aktiven, nie mehr als 14 zugleich
  function impulseSetzen(now) {
    const kanten = data.kanten || [];
    if (!kanten.length || impulse.length >= 5) return;
    const byId = new Map((data.knoten || []).map((k) => [k.id, k]));
    const e = kanten[Math.floor(Math.random() * kanten.length)];
    const akt = Math.max(byId.get(e.a)?.akt || 0, byId.get(e.b)?.akt || 0);
    if (Math.random() > 0.006 + 0.03 * e.w + 0.05 * akt) return;          // selten, gemächlich
    const hin = Math.random() < 0.5;
    impulse.push({ a: hin ? e.a : e.b, b: hin ? e.b : e.a, t0: now, dauer: 2600 + 1800 * (1 - e.w) });
  }

  function impulseMalen(now) {
    const f = farbenKopf();
    for (let i = impulse.length - 1; i >= 0; i--) {
      const s = impulse[i];
      const pa = schirm.get(s.a), pb = schirm.get(s.b);
      const u = (now - s.t0) / s.dauer;
      if (!pa || !pb || u >= 1) { if (u >= 1) glut.set(s.b, now); impulse.splice(i, 1); continue; }
      const e = u < 0.5 ? 2 * u * u : 1 - 2 * (1 - u) * (1 - u);      // sanft an, sanft ab
      const x = pa.x + (pb.x - pa.x) * e, y = pa.y + (pb.y - pa.y) * e;
      const g = ctx.createRadialGradient(x, y, 0, x, y, 7);
      g.addColorStop(0, f.voll); g.addColorStop(1, 'rgba(0, 0, 0, 0)');
      ctx.fillStyle = g; ctx.globalAlpha = 0.55 * Math.sin(Math.PI * u);
      ctx.beginPath(); ctx.arc(x, y, 7, 0, Math.PI * 2); ctx.fill();
    }
    ctx.globalAlpha = 1;
  }

  function radius(k) { return Math.min(14, 4 + Math.sqrt(k.n || 1) * 1.4); }

  function draw(w, hgt) {
    ctx.clearRect(0, 0, w, hgt);
    const now = performance.now();
    const lebt = lebendig();
    if (lebt) { kopfHintergrund(w, hgt, now / 1000); impulseSetzen(now); }
    const nodes = data.knoten || [];
    schirm.clear();
    for (const k of nodes) { const p = pos.get(k.id); if (p) schirm.set(k.id, projizieren(p, w, hgt)); }
    // Verbindungen
    for (const e of data.kanten || []) {
      const pa = schirm.get(e.a); const pb = schirm.get(e.b);
      if (!pa || !pb) continue;
      const lit = Math.max(zeigAkt.get(e.a) || 0, 0) * Math.max(zeigAkt.get(e.b) || 0, 0);
      const fl = flashes.get(`${e.a}|${e.b}`);
      const kopf = kopfModus();
      const dauer = kopf ? 4000 : 2500;
      const roh = fl ? Math.max(0, 1 - (now - fl) / dauer) : 0;
      const flash = kopf ? 0.45 * Math.sin(Math.PI * roh) : roh;          // bei Knowlin: an- und abschwellen
      const tiefeA = kopf ? Math.max(0.35, Math.min(1, (pa.f + pb.f) / 2)) : 1;
      ctx.strokeStyle = flash > 0.02 ? `rgba(255, 255, 255, ${(0.35 + 0.6 * flash) * tiefeA})`
        : `rgba(198, 198, 198, ${(0.12 + 0.45 * e.w + 0.4 * lit) * tiefeA})`;
      ctx.lineWidth = (0.6 + 3 * e.w + 2 * flash) * Math.min(1.6, (pa.f + pb.f) / 2);
      ctx.beginPath(); ctx.moveTo(pa.x, pa.y); ctx.lineTo(pb.x, pb.y); ctx.stroke();
    }
    if (lebt) impulseMalen(now);
    // Knoten mit Leuchten nach Aktivierung
    for (const k of nodes) aktVon(k);
    const ranked = [...nodes].sort((a, b) => (zeigAkt.get(b.id) - zeigAkt.get(a.id)) || (b.n - a.n));
    const labelled = new Set(ranked.slice(0, 16).map((k) => k.id));
    const tiefe = [...nodes].filter((k) => schirm.has(k.id)).sort((a, b) => schirm.get(b.id).z - schirm.get(a.id).z);
    for (const k of tiefe) {                              // hinten zuerst, vorne zuletzt
      const p = schirm.get(k.id);
      const col = FARBE[GRUPPE[k.art] || 'erleben'];
      const r = radius(k) * Math.max(0.4, Math.min(2.2, p.f));
      const an = glut.get(k.id);                        // ein Impuls ist angekommen: sanft an- und abschwellen
      const ka = zeigAkt.get(k.id) || 0;
      const akt = Math.max(ka, an && now - an < 2400 ? 0.3 * Math.sin(Math.PI * (now - an) / 2400) : 0);
      if (akt > 0.05) {
        const g = ctx.createRadialGradient(p.x, p.y, r, p.x, p.y, r + 18 * akt);
        g.addColorStop(0, col + 'aa'); g.addColorStop(1, col + '00');
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(p.x, p.y, r + 18 * akt, 0, Math.PI * 2); ctx.fill();
      }
      const drin = passt(k.herkunft, filter);           // außerhalb des Filters: nur blass, damit das Netz stehen bleibt
      if (kopfModus()) {                                 // Kugel mit Lichtpunkt oben links, hinten im Nebel
        const kugel = ctx.createRadialGradient(p.x - r * 0.35, p.y - r * 0.4, r * 0.1, p.x, p.y, r);
        kugel.addColorStop(0, 'rgba(255, 255, 255, 0.9)'); kugel.addColorStop(0.35, col); kugel.addColorStop(1, col + '88');
        ctx.fillStyle = kugel;
        ctx.globalAlpha = (0.5 + 0.5 * Math.min(1, ka + 0.4)) * Math.max(0.25, Math.min(1, (p.f - 0.55) * 1.6)) * (drin ? 1 : 0.15);
      } else {
        ctx.fillStyle = col;
        ctx.globalAlpha = (0.55 + 0.45 * Math.min(1, ka + 0.3)) * Math.max(0.35, Math.min(1, p.f)) * (drin ? 1 : 0.15);
      }
      ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2); ctx.fill();
      ctx.globalAlpha = 1;
      const w = wach();                                 // die wache Verkörperung: ihr Anteil mit feinem Ring
      if (!filter && w && passt(k.herkunft, w)) {
        ctx.strokeStyle = col; ctx.lineWidth = 1; ctx.globalAlpha = 0.6;
        ctx.beginPath(); ctx.arc(p.x, p.y, r + 2.5, 0, Math.PI * 2); ctx.stroke(); ctx.globalAlpha = 1;
      }
      if (k.id === selected || k.id === hover) {
        ctx.strokeStyle = '#ffffff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(p.x, p.y, r + 3, 0, Math.PI * 2); ctx.stroke();
      }
      if (labelled.has(k.id) || k.id === hover || k.id === selected) {
        ctx.font = `${ka > 0.3 ? 600 : 400} 12px "IBM Plex Sans", sans-serif`;
        ctx.fillStyle = ka > 0.3 ? '#f4f4f4' : '#c6c6c6';
        ctx.textAlign = 'center';
        ctx.fillText(zeigName(k.name), p.x, p.y - r - 6);
      }
    }
  }

  function loop() {
    running = true;
    const tick = () => {
      if (!visible()) { running = false; return; }
      const [w, hgt] = size();
      if (!reduced) step(w, hgt); else for (let i = 0; i < 3; i++) step(w, hgt);
      zurueck();
      draw(w, hgt);
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }

  function at(ev) {
    const r = canvas.getBoundingClientRect();
    const x = ev.clientX - r.left; const y = ev.clientY - r.top;
    let best = null; let bd = 1e9;
    for (const k of data.knoten || []) {
      const p = schirm.get(k.id);
      if (!p) continue;
      const d = Math.hypot(p.x - x, p.y - y);
      if (d < Math.max(12, radius(k) * p.f + 6) && d < bd) { best = k; bd = d; }
    }
    return best;
  }
  // Ziehen dreht, Rad und zwei Finger zoomen
  let ziehen = null;
  const finger = new Map();
  canvas.style.touchAction = 'none';
  canvas.addEventListener('pointerdown', (ev) => {
    finger.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    ziehen = { x: ev.clientX, y: ev.clientY, weit: 0, abstand: null };
    try { canvas.setPointerCapture(ev.pointerId); } catch { /* egal */ }
  });
  canvas.addEventListener('pointermove', (ev) => {
    if (!ziehen || !finger.has(ev.pointerId)) return;
    const alt = finger.get(ev.pointerId);
    finger.set(ev.pointerId, { x: ev.clientX, y: ev.clientY });
    if (finger.size >= 2) {                                  // zwei Finger: zoomen
      const [a, b] = [...finger.values()];
      const d = Math.hypot(a.x - b.x, a.y - b.y);
      if (ziehen.abstand) ansicht.zoom = Math.max(0.5, Math.min(3, ansicht.zoom * d / ziehen.abstand));
      ziehen.abstand = d;
    } else {
      const dx = ev.clientX - alt.x, dy = ev.clientY - alt.y;
      ziehen.weit += Math.abs(dx) + Math.abs(dy);
      ansicht.yaw += dx * 0.01;
      ansicht.pitch = Math.max(-1.3, Math.min(1.3, ansicht.pitch + dy * 0.01));
    }
    zuletztBewegt = performance.now();
  });
  const loslassen = (ev) => {
    finger.delete(ev.pointerId);
    if (!finger.size) { if (ziehen && ziehen.weit > 6) unterdruecken = true; ziehen = null; zuletztBewegt = performance.now(); }
  };
  canvas.addEventListener('pointerup', loslassen);
  canvas.addEventListener('pointercancel', loslassen);
  let unterdruecken = false;                                   // nach dem Drehen kein Klick auf einen Knoten
  canvas.addEventListener('wheel', (ev) => {
    ev.preventDefault();
    ansicht.zoom = Math.max(0.5, Math.min(3, ansicht.zoom * Math.exp(-ev.deltaY * 0.0015)));
    zuletztBewegt = performance.now();
  }, { passive: false });
  canvas.addEventListener('mousemove', (ev) => { const k = at(ev); hover = k ? k.id : null; canvas.style.cursor = k ? 'pointer' : 'default'; });
  canvas.addEventListener('mouseleave', () => { hover = null; });
  canvas.addEventListener('click', (ev) => { if (unterdruecken) { unterdruecken = false; return; } showDetail(at(ev)); });
  // Ohne Maus (WCAG 2.1.1): derselbe Knoten über eine Auswahlliste
  const pick = $('brain-pick');
  if (pick) pick.addEventListener('change', () => showDetail((data.knoten || []).find((k) => k.id === pick.value) || null));
  function renderPick() {
    if (!pick) return;
    const keep = pick.value;
    const knoten = [...(data.knoten || [])].sort((a, b) => a.name.localeCompare(b.name, 'de'));
    pick.replaceChildren(el('option', null, knoten.length ? 'Knoten wählen …' : 'noch keine Knoten'),
      ...knoten.map((k) => { const o = el('option', null, `${zeigName(k.name)} (${zeigName(ART[k.art] || k.art)})`); o.value = k.id; return o; }));
    pick.firstChild.value = '';
    pick.value = knoten.some((k) => k.id === keep) ? keep : '';
    pick.disabled = !knoten.length;
  }
  async function showDetail(k) {
    selected = k ? k.id : null;
    const box = $('brain-detail');
    if (!k) { box.hidden = true; return; }
    const r = await api(`/api/erfahrung/knoten/${encodeURIComponent(k.id)}`).catch(() => null);
    if (!r || !r.ok) { box.hidden = true; return; }
    box.hidden = false;
    const head = el('div', 'brain-detail-head');
    head.append(el('b', null, zeigName(r.knoten.name)), el('span', 'chip', zeigName(ART[r.knoten.art] || r.knoten.art)),
      el('small', null, `${r.knoten.n}× erlebt`));
    const herkunft = el('p', 'field-help brain-herkunft-text',
      `${uebersetzeText('Gelernt:') || 'Gelernt:'} ${herkunftListe((r.knoten.herkunft || k.herkunft), data.herkuenfte)}`);
    const forget = el('button', 'btn btn--ghost btn--sm pc-only', 'Vergessen');
    forget.type = 'button';
    forget.addEventListener('click', async () => {
      const x = await api('/api/erfahrung/vergessen', 'POST', { id: k.id }).catch(() => null);
      if (x && x.ok) { toast(`„${r.knoten.name}“ vergessen`); box.hidden = true; selected = null; }
    });
    head.append(forget);
    const list = el('ul', 'brain-links');
    for (const v of r.verbindungen) {
      const li = el('li');
      const bar = el('span', 'brain-bar');
      bar.style.setProperty('--w', String(v.w));
      li.append(bar, el('span', 'brain-link-name', zeigName(v.name)),
        el('small', null, v.warum.length ? `zuletzt: ${v.warum[v.warum.length - 1]}` : `${v.n}× zusammen`));
      list.append(li);
    }
    box.replaceChildren(head, herkunft, r.verbindungen.length ? list : el('p', 'field-help', 'Noch mit nichts verknüpft.'));
  }

  window.addEventListener('resize', () => { if (visible()) size(); });

  function show() {
    api('/api/erfahrung').then(update).catch(() => {});
    if (!running) loop();
  }

  return { update, show };
}
