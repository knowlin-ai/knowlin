// Hirnaktivität als Galaxie (seit 0.38.67, Wunsch des Maintainers: „Die Optik fand ich ja ganz cool – vielleicht kann man
// das noch etwas interaktiver gestalten“, Vorbild: ein Wissensgraph als Sternenhimmel).
//
// Jede Art (Personen, Orte, Dinge, Tätigkeiten …) bildet einen Nebel mit eigener Mitte; die Knoten sind leuchtende Sterne,
// die Verknüpfungen feine Lichtfäden auch zwischen den Nebeln. Hier liegen nur Berechnung und Zeichnen ohne Zustand –
// den Ablauf (Kamera, Klicks, Tasten, Aufnahme) steuert hirn.js. Farben bleiben die der Gruppen; jede Art bekommt nur
// eine leichte Tönung, ihr Name steht immer am Nebel (Farbe trägt nie allein die Bedeutung).

export const ARTEN = ['person', 'ort', 'ding', 'taetigkeit', 'sinn', 'gefuehl', 'rueckmeldung', 'zeit'];
export const NEBEL_NAME = {
  person: 'Personen', ort: 'Orte', ding: 'Dinge', taetigkeit: 'Tätigkeiten', sinn: 'Sinne', gefuehl: 'Gefühle',
  rueckmeldung: 'Rückmeldungen', zeit: 'Zeit',
};
const TOENUNG = { person: -18, ort: 18, ding: -22, taetigkeit: 0, sinn: 24, gefuehl: -10, rueckmeldung: 16, zeit: 0 };

/** Zufall mit festem Samen – derselbe Nebel sieht bei jedem Bild gleich aus. */
export function zufall(samen) {
  let s = samen >>> 0 || 1;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}

function hsl(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(hex).trim());
  if (!m) return [210, 70, 55];
  const n = parseInt(m[1], 16);
  const r = (n >> 16) / 255, g = ((n >> 8) & 255) / 255, b = (n & 255) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), l = (max + min) / 2;
  if (max === min) return [0, 0, l * 100];
  const d = max - min, s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h = max === r ? (g - b) / d + (g < b ? 6 : 0) : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [h * 60, s * 100, l * 100];
}

/** Farbe einer Art: Gruppenfarbe, leicht getönt und für den dunklen Himmel aufgehellt. */
export function artFarbe(art, gruppenFarbe) {
  const [h, s, l] = hsl(gruppenFarbe);
  return (a = 1) => `hsla(${Math.round(h + (TOENUNG[art] || 0))}, ${Math.round(Math.min(95, s + 10))}%, ${Math.round(Math.max(55, l + 8))}%, ${a})`;
}

/** Mitten der Nebel: auf einer Ellipse um die Bildmitte, in fester Reihenfolge der Arten (gleiche Lage bei jedem Besuch). */
export function zentren(arten, w, h) {
  const da = ARTEN.filter((a) => arten.includes(a));
  const out = {};
  if (da.length === 1) { out[da[0]] = { x: w / 2, y: h / 2 }; return out; }
  da.forEach((a, i) => {
    const t = -Math.PI / 2 + (i / da.length) * Math.PI * 2 + 0.35;
    out[a] = { x: w / 2 + Math.cos(t) * w * 0.32, y: h / 2 + Math.sin(t) * h * 0.26 };
  });
  return out;
}

/** Staub eines Nebels: Punkte in einer Scheibe mit zwei sanften Spiralarmen (Koordinaten relativ zur Mitte, Radius 1). */
export function staub(art, anzahl) {
  const z = zufall([...art].reduce((s, c) => s * 31 + c.charCodeAt(0), 7));
  const arme = 2 + (art.length % 2);
  const out = [];
  for (let i = 0; i < anzahl; i++) {
    const r = Math.sqrt(z());
    const arm = Math.floor(z() * arme);
    const winkel = (arm / arme) * Math.PI * 2 + r * 2.6 + (z() - 0.5) * 1.1 * (1 - r * 0.5);
    out.push({
      x: Math.cos(winkel) * r, y: Math.sin(winkel) * r * 0.8, z: (z() - 0.5) * 0.3,
      a: 0.25 + z() * 0.55, s: z() < 0.08 ? 1.8 : 1, ph: z() * Math.PI * 2,
    });
  }
  return out;
}

/** Sternenhimmel im Hintergrund (Koordinaten 0 … 1). */
export const HIMMEL = (() => {
  const z = zufall(4711);
  return Array.from({ length: 260 }, () => ({ x: z(), y: z(), a: 0.15 + z() * 0.5, s: z() < 0.1 ? 1.4 : 0.8, ph: z() * 6.3 }));
})();

export function hintergrund(ctx, w, h, t, ruhig) {
  const g = ctx.createRadialGradient(w * 0.5, h * 0.45, 0, w * 0.5, h * 0.5, Math.max(w, h) * 0.75);
  g.addColorStop(0, '#0d1126'); g.addColorStop(1, '#03040b');
  ctx.fillStyle = g;
  ctx.fillRect(0, 0, w, h);
  ctx.fillStyle = '#ffffff';
  for (const s of HIMMEL) {
    ctx.globalAlpha = s.a * (ruhig ? 1 : 0.65 + 0.35 * Math.sin(t * 1.3 + s.ph));
    ctx.fillRect(s.x * w, s.y * h, s.s, s.s);
  }
  ctx.globalAlpha = 1;
}

/** Ein Stern: weißer Kern, farbiger Schein (additiv). */
export function stern(ctx, x, y, r, farbe, hell) {
  const R = r * (2.6 + 1.6 * hell);
  const g = ctx.createRadialGradient(x, y, 0, x, y, R);
  g.addColorStop(0, `rgba(255, 255, 255, ${0.85 * Math.min(1, 0.5 + hell)})`);
  g.addColorStop(0.18, farbe(0.85));
  g.addColorStop(0.45, farbe(0.22 + 0.25 * hell));
  g.addColorStop(1, farbe(0));
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.arc(x, y, R, 0, Math.PI * 2); ctx.fill();
}

/** Beschriftung eines Nebels wie auf einer Sternkarte: Punkt, NAME in Großbuchstaben, Anzahl. */
export function nebelSchild(ctx, x, y, name, anzahl, farbe) {
  ctx.save();
  ctx.font = '600 11px "IBM Plex Mono", ui-monospace, monospace';
  try { ctx.letterSpacing = '2px'; } catch { /* ältere Browser: ohne Sperrung */ }
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';
  ctx.fillStyle = farbe(1);
  ctx.beginPath(); ctx.arc(x - 8, y, 3, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = 'rgba(240, 242, 255, 0.92)';
  const text = name.toLocaleUpperCase();
  ctx.fillText(text, x, y);
  const breite = ctx.measureText(text).width;
  ctx.font = '400 10px "IBM Plex Mono", ui-monospace, monospace';
  ctx.fillStyle = 'rgba(200, 205, 230, 0.6)';
  ctx.fillText(String(anzahl), x + breite + 6, y + 1);
  ctx.restore();
}

/** Reihenfolge fürs „Wachsen sehen“: was zuerst erlebt wurde, zuerst. */
export function wachsReihe(knoten) {
  return [...knoten].sort((a, b) => (a.erst || 0) - (b.erst || 0) || (b.n || 0) - (a.n || 0)).map((k) => k.id);
}

/** Passt ein Knoten zur Suche? Groß-/Kleinschreibung und Umlaute egal, Name oder Art. */
export function trifft(k, suche, zeigName) {
  if (!suche) return true;
  const norm = (s) => String(s || '').toLocaleLowerCase('de').normalize('NFD').replace(/[̀-ͯ]/g, '');
  const q = norm(suche);
  return norm(zeigName(k.name)).includes(q) || norm(k.name).includes(q) || norm(NEBEL_NAME[k.art]).includes(q);
}
