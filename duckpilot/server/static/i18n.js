// Gerüst für mehrere Sprachen (seit 0.33; Englisch folgt in 0.34).
// Texte kommen als Katalog vom Server (GET /api/i18n/{sprache}, Lücken sind dort schon mit Deutsch gefüllt).
// In Skripten: t('geplant.fuer', { version: '0.34' }, 'geplant für {version}') – der dritte Wert gilt, bis der
// Katalog geladen ist. Im HTML: data-i18n="schlüssel" (Textinhalt) bzw.
// data-i18n-attr="aria-label:schlüssel,title:schlüssel2". Unbekannte Schlüssel bleiben sichtbar stehen, damit eine
// Lücke auffällt. Ohne geladenen Katalog bleibt der deutsche Text aus dem HTML stehen.
//
// Seit 0.34 dazu ein Übersetzer für die ganze Seite (Sprache ≠ Deutsch): Er schaut jeden sichtbaren Text an – auch was
// Skripte später schreiben – und ersetzt ihn, wenn er im Oberflächenkatalog steht (ui_en.json: deutscher Text →
// Englisch, „#“ = Zahl). So braucht nicht jeder Text einen Schlüssel. Was fehlt, bleibt deutsch und landet in
// window.__i18nFehlt (für tools/i18n_texte.py und den Browser-Test). translate="no" schützt einen Bereich
// (Gesprächsverlauf, Namen).
let texte = {};
let ui = {};
let aktuell = 'de';
let vorlagen = [];                   // [RegExp, Übersetzung] – „#“ = Zahl, „*“ = beliebiger Text (Name …)
const ATTRS = ['title', 'aria-label', 'placeholder', 'alt'];
export const DEUTSCH = /[äöüÄÖÜß„]|\b(der|die|das|den|dem|und|nicht|ist|mit|ein|eine|noch|auf|zum|zur|vom|beim|sie|ihr|für|wie|was|bei|nach|oder|aus|kein|keine|gerade|alle|neu)\b/i;

export async function ladeSprache(sprache = 'aktuell') {
  try {
    const r = await fetch(`/api/i18n/${encodeURIComponent(sprache)}`, { cache: 'no-store' });
    if (r.ok) {
      const j = await r.json();
      texte = j.texte || {}; ui = j.ui || {}; aktuell = j.sprache || 'de';
      vorlagen = Object.entries(ui).filter(([k]) => /[#*]/.test(k)).map(([k, v]) => [vorlage(k), v]);
    }
  } catch { /* offline: deutscher Text aus dem HTML bleibt */ }
  document.documentElement.lang = aktuell;
  if (aktuell !== 'de') starteUebersetzer();
  return aktuell;
}

const fehlt = new Set();
if (typeof window !== 'undefined') window.__i18nFehlt = fehlt;
export const uiKatalog = () => ui;

function vorlage(k) {
  const re = k.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/#/g, '([-−+]?\\d+(?:[.,]\\d+)?)').replace(/\*/g, '(.+?)');
  return new RegExp(`^${re}$`);
}

// Einen Text übersetzen: exakt, sonst über eine Vorlage (Zahlen: Dezimalkomma → Punkt; Namen werden selbst
// nachgeschlagen, z. B. der Charakter). null = nicht im Katalog.
export function uebersetzeText(roh, tiefe = 0) {
  const s = roh.replace(/\s+/g, ' ').trim();
  if (!s) return null;
  const ersetze = (ziel) => (s.length === roh.length ? ziel : roh.replace(roh.trim(), ziel));
  if (s in ui) return ersetze(ui[s]);
  if (!/[A-Za-zÄÖÜäöüß]{3}/.test(s) && /\d,\d/.test(s)) return roh.replace(/(\d),(\d)/g, '$1.$2');   // 0,25 m/s → 0.25 m/s
  if (/[A-Za-zÄÖÜäöüß]{2}/.test(s) && tiefe < 2) {
    for (const [re, ziel] of vorlagen) {
      const m = s.match(re);
      if (!m) continue;
      const teile = m.slice(1);
      let i = 0;
      return ersetze(ziel.replace(/[#*]/g, (z) => {
        const v = teile[i++] ?? '';
        return z === '#' ? v.replace(',', '.') : (uebersetzeText(v, tiefe + 1) ?? v);
      }));
    }
  }
  if (tiefe === 0 && DEUTSCH.test(s)) fehlt.add(s);
  return null;
}

function geschuetzt(node) {
  const el = node.nodeType === 1 ? node : node.parentElement;
  return !el || !!el.closest('[translate="no"], script, style, textarea, code');
}

function knoten(node) {
  if (node.nodeType === 3) {
    if (geschuetzt(node)) return;
    const neu = uebersetzeText(node.nodeValue);
    if (neu !== null && neu !== node.nodeValue) node.nodeValue = neu;
    return;
  }
  // Elemente: Textfelder selbst nicht anfassen (dort tippt man), ihren Platzhalter aber schon
  if (node.nodeType !== 1 || (node.tagName !== 'TEXTAREA' && geschuetzt(node)) || node.closest('[translate="no"], code')) return;
  for (const a of ATTRS) {
    const v = node.getAttribute(a);
    if (v) { const neu = uebersetzeText(v); if (neu !== null && neu !== v) node.setAttribute(a, neu); }
  }
  for (const k of node.childNodes) knoten(k);
}

let beobachter = null;
function starteUebersetzer() {
  if (beobachter || !document.body) return;
  knoten(document.body);
  document.title = uebersetzeText(document.title) || document.title;
  beobachter = new MutationObserver((liste) => {
    for (const m of liste) {
      if (m.type === 'characterData') knoten(m.target);
      else if (m.type === 'attributes') knoten(m.target.nodeType === 1 ? m.target : m.target.parentNode);
      else for (const n of m.addedNodes) knoten(n);
    }
  });
  beobachter.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ATTRS });
}

export function t(schluessel, werte = {}, ersatz) {
  const roh = texte[schluessel] ?? ersatz;      // ersatz: der deutsche Text, solange der Katalog noch nicht da ist
  if (roh === undefined) return schluessel;
  return roh.replace(/\{(\w+)(?::\.(\d)f)?\}/g, (m, k, nachkomma) => {
    if (!(k in werte)) return m;
    const v = werte[k];
    return nachkomma !== undefined && typeof v === 'number' ? v.toFixed(Number(nachkomma)) : String(v);
  });
}

export function uebersetze(root = document) {
  if (!Object.keys(texte).length) return;
  for (const el of root.querySelectorAll('[data-i18n]')) {
    const s = texte[el.dataset.i18n];
    if (s !== undefined) el.textContent = s;
  }
  for (const el of root.querySelectorAll('[data-i18n-attr]')) {
    for (const paar of el.dataset.i18nAttr.split(',')) {
      const [attr, key] = paar.split(':').map((x) => x.trim());
      if (attr && key && texte[key] !== undefined) el.setAttribute(attr, texte[key]);
    }
  }
}

export const sprache = () => aktuell;
