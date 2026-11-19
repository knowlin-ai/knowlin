// Zoomen und Verschieben für Karten von oben (seit 0.38.66, Wunsch des Maintainers: „das sollte man zoomen können –
// bei größeren Maps sieht man sonst keine Details mehr, und vielleicht geht das auch hochwertiger“).
//
// Mausrad oder zwei Finger zoomen um die Stelle unter dem Zeiger, Ziehen verschiebt, Doppelklick zoomt hinein.
// Tastatur auf der Karte: + und − zoomen, Pfeiltasten verschieben, 0 passt wieder ein. Dazu Knöpfe „+“, „−“ und
// „Einpassen“ über der Karte. Die Zeichnung selbst bleibt beim Aufrufer: Er rechnet seinen eingepassten Ausschnitt aus
// und bekommt mit `ansicht()` den gezoomten zurück (Mitte in Metern, Maßstab in Pixel je Meter).

import { uebersetzeText } from './i18n.js';

const tr = (t) => uebersetzeText(t) || t;
const MIN = 1, MAX = 12;

export class KartenZoom {
  constructor(canvas, neuZeichnen) {
    this.canvas = canvas;
    this.neu = neuZeichnen;
    this.zoom = 1;
    this.panX = 0;                    // Verschiebung der Mitte in Metern
    this.panY = 0;
    this.letzte = null;               // {cx, cy, s, w, h, fitS}
    this.zeiger = new Map();
    this._knoepfe();
    this._ereignisse();
  }

  /** Eingepasster Ausschnitt rein, gezoomter raus (Mitte cx, cy in m; s in Pixel je m; w, h in CSS-Pixeln). */
  ansicht(cx, cy, s, w, h) {
    const v = { cx: cx + this.panX, cy: cy + this.panY, s: s * this.zoom, w, h, fitCx: cx, fitCy: cy, fitS: s };
    this.letzte = v;
    return v;
  }

  get gezoomt() { return this.zoom !== 1 || this.panX !== 0 || this.panY !== 0; }

  einpassen() {
    this.zoom = 1;
    this.panX = this.panY = 0;
    this._fertig();
  }

  /** Um den Punkt (px, py) in CSS-Pixeln der Karte zoomen; ohne Punkt um die Mitte. */
  zoomen(faktor, px, py) {
    const v = this.letzte;
    if (!v) return;
    const neu = Math.max(MIN, Math.min(MAX, this.zoom * faktor));
    if (neu === this.zoom) return;
    const x = px ?? v.w / 2, y = py ?? v.h / 2;
    const wx = v.cx + (x - v.w / 2) / v.s, wy = v.cy - (y - v.h / 2) / v.s;    // Weltpunkt unter dem Zeiger
    const s2 = v.fitS * neu;
    this.zoom = neu;
    if (neu === MIN) { this.panX = this.panY = 0; } else {
      this.panX = wx - (x - v.w / 2) / s2 - v.fitCx;
      this.panY = wy + (y - v.h / 2) / s2 - v.fitCy;
    }
    this._fertig();
  }

  verschieben(dxPx, dyPx) {
    const v = this.letzte;
    if (!v || this.zoom === MIN) return;
    this.panX -= dxPx / v.s;
    this.panY += dyPx / v.s;
    this._fertig();
  }

  _fertig() {
    this.anzeige.textContent = `${Math.round(this.zoom * 100)} %`;
    this.minus.disabled = this.zoom <= MIN;
    this.plus.disabled = this.zoom >= MAX;
    this.passen.disabled = !this.gezoomt;
    this.canvas.style.cursor = this.zoom > MIN ? 'grab' : '';
    this.neu();
  }

  _knoepfe() {
    const c = this.canvas;
    let huelle = c.parentElement;
    if (!huelle.classList.contains('karten-zoom')) {
      huelle = document.createElement('div');
      huelle.className = 'karten-zoom';
      c.replaceWith(huelle);
      huelle.append(c);
    }
    const leiste = document.createElement('div');
    leiste.className = 'karten-zoom-leiste';
    leiste.setAttribute('role', 'group');
    leiste.setAttribute('aria-label', tr('Karte zoomen'));
    const knopf = (text, titel, fn) => {
      const b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn btn--ghost btn--sm karten-zoom-knopf';
      b.textContent = text;
      b.title = tr(titel);
      b.setAttribute('aria-label', tr(titel));
      b.addEventListener('click', fn);
      return b;
    };
    this.minus = knopf('−', 'Herauszoomen', () => this.zoomen(1 / 1.5));
    this.plus = knopf('+', 'Hineinzoomen', () => this.zoomen(1.5));
    this.passen = knopf(tr('Einpassen'), 'Ganze Karte zeigen', () => this.einpassen());
    this.passen.classList.add('karten-zoom-passen');
    this.anzeige = document.createElement('span');
    this.anzeige.className = 'karten-zoom-wert';
    this.anzeige.setAttribute('aria-live', 'polite');
    this.anzeige.textContent = '100 %';
    leiste.append(this.minus, this.anzeige, this.plus, this.passen);
    huelle.append(leiste);
    this.minus.disabled = this.passen.disabled = true;
    if (!c.hasAttribute('tabindex')) c.tabIndex = 0;
    const alt = c.getAttribute('aria-label') || '';
    this._hilfe = tr('Mit + und − zoomen, mit den Pfeiltasten verschieben, 0 passt ein.');
    if (alt && !alt.includes(this._hilfe)) c.setAttribute('aria-description', this._hilfe);
  }

  _ereignisse() {
    const c = this.canvas;
    const lokal = (e) => { const r = c.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    c.addEventListener('wheel', (e) => {
      e.preventDefault();
      const [x, y] = lokal(e);
      this.zoomen(Math.exp(-e.deltaY * (e.deltaMode === 1 ? 0.05 : 0.0018)), x, y);
    }, { passive: false });
    c.addEventListener('dblclick', (e) => { const [x, y] = lokal(e); this.zoomen(2, x, y); });
    c.addEventListener('pointerdown', (e) => {
      this.zeiger.set(e.pointerId, lokal(e));
      try { c.setPointerCapture(e.pointerId); } catch { /* egal */ }
      if (this.zoom > MIN) c.style.cursor = 'grabbing';
    });
    c.addEventListener('pointermove', (e) => {
      if (!this.zeiger.has(e.pointerId)) return;
      const alt = this.zeiger.get(e.pointerId);
      const neu = lokal(e);
      if (this.zeiger.size === 2) {                       // zwei Finger: zoomen um ihre Mitte
        const [a, b] = [...this.zeiger.entries()].map(([id, p]) => (id === e.pointerId ? neu : p));
        const [a0, b0] = [...this.zeiger.values()];
        const d0 = Math.hypot(a0[0] - b0[0], a0[1] - b0[1]), d1 = Math.hypot(a[0] - b[0], a[1] - b[1]);
        if (d0 > 10) this.zoomen(d1 / d0, (a[0] + b[0]) / 2, (a[1] + b[1]) / 2);
      } else {
        this.verschieben(neu[0] - alt[0], neu[1] - alt[1]);
      }
      this.zeiger.set(e.pointerId, neu);
    });
    const los = (e) => {
      this.zeiger.delete(e.pointerId);
      c.style.cursor = this.zoom > MIN ? 'grab' : '';
    };
    c.addEventListener('pointerup', los);
    c.addEventListener('pointercancel', los);
    c.addEventListener('keydown', (e) => {
      const schritt = 40;
      const tasten = {
        '+': () => this.zoomen(1.5), '=': () => this.zoomen(1.5), '-': () => this.zoomen(1 / 1.5),
        0: () => this.einpassen(), ArrowLeft: () => this.verschieben(schritt, 0), ArrowRight: () => this.verschieben(-schritt, 0),
        ArrowUp: () => this.verschieben(0, schritt), ArrowDown: () => this.verschieben(0, -schritt),
      };
      const fn = tasten[e.key];
      if (!fn) return;
      e.preventDefault();
      fn();
    });
    c.style.touchAction = 'none';
  }
}

/** Freie Fläche weich, Hindernisse als klare Zellen: aus den Zelllisten der Karte in den Ausschnitt `v` zeichnen. */
export function zeichneZellen(g, karte, v, farben, deckkraft = 1) {
  const z = karte.zelle_m || 0.05;
  const zellen = [...(karte.frei || []), ...(karte.belegt || [])];
  if (!zellen.length) return;
  let i0 = Infinity, j0 = Infinity, i1 = -Infinity, j1 = -Infinity;
  for (const [i, j] of zellen) { i0 = Math.min(i0, i); j0 = Math.min(j0, j); i1 = Math.max(i1, i); j1 = Math.max(j1, j); }
  const breite = i1 - i0 + 3, hoehe = j1 - j0 + 3;
  // Freie Fläche: ein Pixel je Zelle, weich hochskaliert – keine Treppenkanten, kein Gitterflimmern zwischen Zellen
  const buf = document.createElement('canvas');
  buf.width = breite; buf.height = hoehe;
  const b = buf.getContext('2d');
  b.fillStyle = farben.frei;
  for (const [i, j] of karte.frei || []) b.fillRect(i - i0 + 1, j1 - j + 1, 1, 1);
  const px = (x) => v.w / 2 + (x - v.cx) * v.s, py = (y) => v.h / 2 - (y - v.cy) * v.s;
  const zp = z * v.s;
  g.save();
  g.globalAlpha = deckkraft;
  g.imageSmoothingEnabled = zp < 6;                // nah dran: klare Zellen, weit weg: weiche Fläche
  g.imageSmoothingQuality = 'high';
  g.drawImage(buf, px((i0 - 1) * z), py((j1 + 2) * z), breite * zp, hoehe * zp);
  // Hindernisse: als zusammenhängende Kontur (benachbarte Zellen ohne Fugen), nah dran mit feiner Kante
  g.fillStyle = farben.belegt;
  const belegt = new Set((karte.belegt || []).map(([i, j]) => `${i},${j}`));
  g.beginPath();
  for (const [i, j] of karte.belegt || []) g.rect(px(i * z), py((j + 1) * z), zp, zp);
  g.fill();
  if (zp >= 8) {
    g.strokeStyle = farben.kante || farben.belegt;
    g.lineWidth = 1;
    g.beginPath();
    for (const [i, j] of karte.belegt || []) {             // nur Außenkanten der Hindernisse
      const x = px(i * z), y = py((j + 1) * z);
      if (!belegt.has(`${i},${j + 1}`)) { g.moveTo(x, y); g.lineTo(x + zp, y); }
      if (!belegt.has(`${i},${j - 1}`)) { g.moveTo(x, y + zp); g.lineTo(x + zp, y + zp); }
      if (!belegt.has(`${i - 1},${j}`)) { g.moveTo(x, y); g.lineTo(x, y + zp); }
      if (!belegt.has(`${i + 1},${j}`)) { g.moveTo(x + zp, y); g.lineTo(x + zp, y + zp); }
    }
    g.stroke();
  }
  g.restore();
}

/** Raster in Metern, dichter beim Hineinzoomen (1 m, 50 cm, 10 cm). */
export function zeichneRaster(g, v, farbe) {
  const schritt = v.s > 400 ? 0.1 : v.s > 120 ? 0.5 : 1;
  const x0 = v.cx - v.w / 2 / v.s, x1 = v.cx + v.w / 2 / v.s, y0 = v.cy - v.h / 2 / v.s, y1 = v.cy + v.h / 2 / v.s;
  g.save();
  g.strokeStyle = farbe;
  g.lineWidth = 1;
  g.beginPath();
  for (let x = Math.ceil(x0 / schritt) * schritt; x <= x1; x += schritt) {
    const p = Math.round(v.w / 2 + (x - v.cx) * v.s) + 0.5;
    g.moveTo(p, 0); g.lineTo(p, v.h);
  }
  for (let y = Math.ceil(y0 / schritt) * schritt; y <= y1; y += schritt) {
    const p = Math.round(v.h / 2 - (y - v.cy) * v.s) + 0.5;
    g.moveTo(0, p); g.lineTo(v.w, p);
  }
  g.stroke();
  g.restore();
  return schritt;
}
