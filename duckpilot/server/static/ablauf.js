// Ablauf-Baukasten und Duck Cards (seit 0.49). Server: /api/ablauf (routes/ablauf.py), Meldungen als „knowlin:ablauf“.
// Die Reihe besteht aus Karten wie auf dem Tisch: je Schritt eine Kartennummer (duck-cards/0) und die Zusatzkarten
// darunter (Tempo, Blick); Wiederholen … Ende klammern. Zum Abspielen legt der Browser die Karten gedanklich hin und der
// Server liest sie mit demselben Leser wie die echten Karten – eine Regel für beide Wege.
// Die Webcam erkennt die AprilTags hier im Browser (vendor/aruco36h11.js); an Knowlin gehen nur Nummern und Lagen.
import { uebersetzeText } from './i18n.js';

const tr = (t) => uebersetzeText(t) || t;
const PALETTE = [0, 1, 2, 3, 4, 40, 41, 42, 43, 44, 60, 61, 62, 63, 64, 80, 81, 82, 83, 84, 102, 103];
const TEMPO = [[22, 'normal'], [20, 'langsam'], [21, 'schnell']];
const BLICK = [[0, '–'], [40, 'links'], [41, 'rechts'], [42, 'hoch'], [43, 'runter'], [44, 'geradeaus']];
const GRUPPE = (k) => (k < 20 ? 'gehen' : k < 60 ? 'schauen' : k < 80 ? 'trick' : k < 100 ? 'laut' : 'klammer');
const ABSTAND = 60, GROESSE = 40;

export function initAblauf({ $, api, toast }) {
  if (!$('ab-palette')) return { laden() {} };
  let namen = {}, stand = null;
  const reihen = { haupt: [], sturz: [] };       // je Eintrag {k, tempo?, blick?, mal?}
  const fehler = (r) => toast(tr((r && r.fehler) || 'Das ging nicht'), true);
  const name = (k) => tr(namen[k]?.name || `Karte ${k}`);
  const ziel = () => document.querySelector('input[name="ab-ziel"]:checked')?.value || 'haupt';

  function auswahl(werte, jetzt, label, aendern) {
    const s = document.createElement('select');
    s.className = 'input ab-zusatz';
    s.setAttribute('aria-label', tr(label));
    for (const [v, t] of werte) s.append(new Option(tr(t), v, false, Number(jetzt) === v));
    s.addEventListener('change', () => aendern(Number(s.value)));
    return s;
  }

  function knopf(text, label, tun) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn btn--ghost btn--sm ab-mini';
    b.textContent = text;
    b.setAttribute('aria-label', tr(label));
    b.addEventListener('click', tun);
    return b;
  }

  function zeichnen() {
    for (const r of ['haupt', 'sturz']) {
      const ol = $(r === 'haupt' ? 'ab-haupt' : 'ab-sturz');
      let tiefe = 0;
      ol.replaceChildren(...reihen[r].map((e, i) => {
        if (e.k === 103) tiefe = Math.max(0, tiefe - 1);
        const li = document.createElement('li');
        li.className = `ab-schritt ab-${GRUPPE(e.k)}`;
        li.style.setProperty('--tiefe', tiefe);
        li.draggable = true;
        li.dataset.i = i;
        const b = document.createElement('b');
        b.textContent = name(e.k);
        li.append(b);
        if (e.k <= 1) li.append(auswahl(TEMPO, e.tempo ?? 22, 'Tempo', (v) => { e.tempo = v; }));
        if (e.k <= 4) li.append(auswahl(BLICK, e.blick ?? 0, 'Blick dabei', (v) => { e.blick = v || undefined; }));
        if (e.k === 102) {
          const n = document.createElement('input');
          Object.assign(n, { type: 'number', min: 1, max: 10, value: e.mal ?? 2, className: 'input ab-zusatz' });
          n.setAttribute('aria-label', tr('Wie oft?'));
          n.addEventListener('change', () => { e.mal = Math.max(1, Math.min(10, Number(n.value) || 2)); });
          li.append(n, document.createTextNode('×'));
          tiefe += 1;
        }
        const zug = (d) => () => { const j = i + d; if (j < 0 || j >= reihen[r].length) return; [reihen[r][i], reihen[r][j]] = [reihen[r][j], reihen[r][i]]; zeichnen(); };
        li.append(knopf('↑', `${name(e.k)} nach vorn`, zug(-1)), knopf('↓', `${name(e.k)} nach hinten`, zug(1)),
          knopf('✕', `${name(e.k)} entfernen`, () => { reihen[r].splice(i, 1); zeichnen(); }));
        li.addEventListener('dragstart', (ev) => ev.dataTransfer.setData('text/plain', JSON.stringify({ r, i })));
        return li;
      }));
    }
    $('ab-stand').textContent = reihen.haupt.length ? '' : tr('Noch leer – Karten oben anklicken oder hineinziehen.');
  }

  function ablegen(ev, r) {
    ev.preventDefault();
    let d;
    try { d = JSON.parse(ev.dataTransfer.getData('text/plain')); } catch { return; }
    const li = ev.target.closest?.('.ab-schritt');
    const an = li ? Number(li.dataset.i) : reihen[r].length;
    if (d.neu != null) reihen[r].splice(an, 0, { k: d.neu });
    else {
      const [e] = reihen[d.r].splice(d.i, 1);
      reihen[r].splice(d.r === r && d.i < an ? an - 1 : an, 0, e);
    }
    zeichnen();
  }
  for (const [r, id] of [['haupt', 'ab-haupt'], ['sturz', 'ab-sturz']]) {
    $(id).addEventListener('dragover', (ev) => ev.preventDefault());
    $(id).addEventListener('drop', (ev) => ablegen(ev, r));
  }

  function palette() {
    $('ab-palette').replaceChildren(...PALETTE.filter((k) => namen[k]).map((k) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = `ab-karte ab-${GRUPPE(k)}`;
      b.textContent = name(k);
      b.draggable = true;
      b.addEventListener('click', () => { reihen[ziel()].push({ k }); zeichnen(); });
      b.addEventListener('dragstart', (ev) => ev.dataTransfer.setData('text/plain', JSON.stringify({ neu: k })));
      return b;
    }));
  }

  // Die Reihe als hingelegte Karten (wie vom Tisch gelesen): Zeile 0 der Ablauf, Zeile 200 „Wenn sie fällt“
  function alsTags() {
    const tags = [];
    const legen = (liste, y, x0) => liste.forEach((e, i) => {
      const x = x0 + i * ABSTAND;
      tags.push({ id: e.k, x, y, w: GROESSE });
      const unter = [e.k <= 1 ? (e.tempo ?? 22) : null, e.blick || null].filter((v) => v != null);
      unter.forEach((u, j) => tags.push({ id: u, x: x + (j ? 8 : -8) * (unter.length - 1), y: y + 45, w: GROESSE }));
    });
    legen(reihen.haupt, 0, 0);
    if (reihen.sturz.length) { tags.push({ id: 120, x: 0, y: 200, w: GROESSE }); legen(reihen.sturz, 200, ABSTAND); }
    return tags;
  }
  const malListe = () => [...reihen.haupt, ...reihen.sturz].filter((e) => e.k === 102).map((e) => e.mal ?? 2);
  function malSetzen(schritte, mal) {
    for (const s of schritte) if (s.art === 'wiederholen') { s.mal = mal.shift() ?? s.mal; malSetzen(s.schritte, mal); }
  }
  async function bauen() {
    if (!reihen.haupt.length) { toast(tr('Der Ablauf ist leer.'), true); return null; }
    const r = await api('/api/ablauf/karten', 'POST', { tags: alsTags() }).catch((e) => ({ fehler: e.message }));
    if (!r.ok) { fehler(r); return null; }
    const mal = malListe();
    malSetzen(r.ablauf.schritte, mal);
    malSetzen(r.ablauf.bei_sturz, mal);
    zeigeMeldungen(r.meldungen);
    return { ...r.ablauf, name: $('ab-name').value.trim() };
  }

  function ausGruppen(gruppen, schritte) {
    const mal = [];
    (function sammeln(l) { for (const s of l) if (s.art === 'wiederholen') { mal.push(s.mal); sammeln(s.schritte); } })(schritte);
    return gruppen.map(([k, ...unter]) => ({ k, tempo: unter.find((u) => u >= 20 && u < 40),
      blick: unter.find((u) => u >= 40 && u < 60), mal: k === 102 ? mal.shift() : undefined }));
  }
  function uebernehmen(ab, gruppen, sturz) {
    reihen.haupt = ausGruppen(gruppen, ab.schritte);
    reihen.sturz = ausGruppen(sturz, ab.bei_sturz || []);
    if (ab.name) $('ab-name').value = ab.name;
    zeichnen();
  }
  function zeigeMeldungen(m) {
    $('ab-meldungen').replaceChildren(...(m || []).map((t) => Object.assign(document.createElement('li'), { textContent: tr(t) })));
  }

  function liste() {
    const alle = Object.entries(stand?.ablaeufe || {});
    if (!alle.length) { $('ab-liste').replaceChildren(Object.assign(document.createElement('li'), { className: 'field-help', textContent: tr('Noch keine Abläufe gespeichert.') })); return; }
    $('ab-liste').replaceChildren(...alle.map(([n, ab]) => {
      const li = document.createElement('li');
      li.className = 'ab-eintrag';
      const kopf = document.createElement('div');
      kopf.className = 'input-row';
      const b = document.createElement('b');
      b.textContent = `${n} · ${ab.anzahl} ${tr('Schritte')}`;
      kopf.append(b,
        knopf(tr('Abspielen'), `${n} abspielen`, () => starten({ name: n })),
        knopf(tr('Bearbeiten'), `${n} bearbeiten`, () => uebernehmen(ab, ab.karten, ab.karten_sturz || [])),
        knopf(tr('Löschen'), `${n} löschen`, async () => { const r = await api(`/api/ablauf/${encodeURIComponent(n)}`, 'DELETE').catch((e) => ({ fehler: e.message })); if (r.ok) { stand = r; liste(); } else fehler(r); }));
      const karten = document.createElement('p');
      karten.className = 'ab-kartenzeile';
      const text = (g) => g.map(([k, ...u]) => [k, ...u].map((x) => `${x} ${name(x)}`).join(' + ')).join(' · ');
      karten.textContent = `${tr('Karten')}: ${text(ab.karten)}${ab.karten_sturz?.length ? ` | 120 ${name(120)}: ${text(ab.karten_sturz)}` : ''}`;
      li.append(kopf, karten);
      return li;
    }));
  }

  async function starten(body) {
    const r = await api('/api/ablauf/start', 'POST', body).catch((e) => ({ fehler: e.message }));
    if (!r.ok) fehler(r); else $('ab-stand').textContent = tr(r.text);
  }
  const laeuft = (ja) => { $('ab-start').hidden = ja; $('ab-stopp').hidden = !ja; };

  $('ab-start').addEventListener('click', async () => { const ab = await bauen(); if (ab) starten({ ablauf: ab }); });
  $('ab-stopp').addEventListener('click', () => api('/api/ablauf/stopp', 'POST', {}).catch(() => null));
  $('ab-leeren').addEventListener('click', () => { reihen.haupt = []; reihen.sturz = []; zeigeMeldungen([]); zeichnen(); });
  $('ab-speichern').addEventListener('click', async () => {
    if (!$('ab-name').value.trim()) { toast(tr('Gib dem Ablauf einen Namen.'), true); $('ab-name').focus(); return; }
    const ab = await bauen();
    if (!ab) return;
    const r = await api('/api/ablauf/speichern', 'POST', { ablauf: ab }).catch((e) => ({ fehler: e.message }));
    if (!r.ok) return fehler(r);
    stand = r;
    liste();
    toast(tr('Gespeichert.'));
  });

  window.addEventListener('knowlin:ablauf', (ev) => {
    const m = ev.detail || {};
    if (m.phase === 'start') laeuft(true);
    else if (m.phase === 'schritt') $('ab-stand').textContent = `${tr('Schritt')} ${m.nr} / ${m.gesamt}`;
    else if (m.phase === 'sturz') $('ab-stand').textContent = tr(m.text);
    else if (m.phase === 'ende') { laeuft(false); $('ab-stand').textContent = tr(m.text); }
  });

  // ── Duck Cards per Webcam ────────────────────────────────────────────
  let strom = null, erkenner = null, takt = 0, zuletzt = [];
  const leinwand = document.createElement('canvas');
  async function kameraAn() {
    try {
      const { AR } = await import('./vendor/aruco36h11.js');
      erkenner = erkenner || new AR.Detector({ dictionaryName: 'APRILTAG_36h11' });
      strom = await navigator.mediaDevices.getUserMedia({ video: { width: 1280, height: 720, facingMode: 'environment' } });
    } catch (e) {
      toast(tr('Die Webcam ließ sich nicht öffnen.'), true);
      return;
    }
    const v = $('ab-video');
    v.srcObject = strom;
    await v.play().catch(() => null);
    $('ab-bild').hidden = false;
    $('ab-kamera').hidden = true;
    $('ab-kamera-zu').hidden = false;
    $('ab-erkannt').hidden = false;
    takt = setInterval(lesen, 300);
  }
  function kameraAus() {
    clearInterval(takt);
    strom?.getTracks().forEach((t) => t.stop());
    strom = null;
    $('ab-bild').hidden = true;
    $('ab-kamera').hidden = false;
    $('ab-kamera-zu').hidden = true;
    $('ab-uebernehmen').hidden = true;
  }
  function lesen() {
    const v = $('ab-video');
    if (!v.videoWidth) return;
    const w = Math.min(960, v.videoWidth), h = Math.round(w * v.videoHeight / v.videoWidth);
    leinwand.width = w; leinwand.height = h;
    const ctx = leinwand.getContext('2d', { willReadFrequently: true });
    ctx.drawImage(v, 0, 0, w, h);
    const marken = erkenner.detectImage(w, h, ctx.getImageData(0, 0, w, h).data);
    zuletzt = marken.map((m) => {
      const xs = m.corners.map((c) => c.x), ys = m.corners.map((c) => c.y);
      return { id: m.id, x: xs.reduce((a, b) => a + b) / 4, y: ys.reduce((a, b) => a + b) / 4, w: Math.max(...xs) - Math.min(...xs), ecken: m.corners };
    });
    const r = $('ab-rahmen');
    r.width = w; r.height = h;
    const c = r.getContext('2d');
    c.lineWidth = 3;
    c.strokeStyle = getComputedStyle(r).color;
    for (const m of zuletzt) {
      c.beginPath();
      m.ecken.forEach((p, i) => (i ? c.lineTo(p.x, p.y) : c.moveTo(p.x, p.y)));
      c.closePath();
      c.stroke();
    }
    $('ab-erkannt').textContent = zuletzt.length
      ? `${tr('Erkannt')}: ${[...zuletzt].sort((a, b) => a.x - b.x).map((m) => name(m.id)).join(', ')}`
      : tr('Noch keine Karte im Bild.');
    $('ab-uebernehmen').hidden = !zuletzt.length;
  }
  $('ab-kamera').addEventListener('click', kameraAn);
  $('ab-kamera-zu').addEventListener('click', kameraAus);
  $('ab-uebernehmen').addEventListener('click', async () => {
    const tags = zuletzt.map(({ id, x, y, w }) => ({ id, x, y, w }));        // nur Nummern und Lagen, kein Bild
    const mal = Number($('ab-mal').value) || 2;
    const r = await api('/api/ablauf/karten', 'POST', { tags, mal }).catch((e) => ({ fehler: e.message }));
    zeigeMeldungen(r.meldungen);
    if (!r.ok) return fehler(r);
    uebernehmen(r.ablauf, r.gruppen, r.gruppen_sturz);
    kameraAus();
    toast(tr(r.vollstaendig ? 'Karten gelesen.' : 'Karten gelesen – nicht alles passte, siehe Hinweise.'));
  });
  new MutationObserver(() => { if ($('ab-bild').closest('[data-part]')?.hidden && strom) kameraAus(); })
    .observe($('ab-palette').closest('[data-part]'), { attributes: true, attributeFilter: ['hidden'] });

  async function laden() {
    stand = await api('/api/ablauf').catch(() => null);
    if (!stand) return;
    namen = stand.karten || {};
    palette();
    zeichnen();
    liste();
    if (stand.laeuft) laeuft(true);
  }
  laden();
  return { laden };
}
