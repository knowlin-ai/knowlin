// Verbindungstest vor dem ersten Start am echten Roboter (seit 0.38.16): prüft eine Adresse nur lesend (erreichbar,
// Version, Akku) und zeigt jeden Befund mit Zeichen und Text – nie Farbe allein. Bewegt wird dabei nichts.
import { uebersetzeText } from './i18n.js';

const tr = (t) => (t ? uebersetzeText(t) || t : '');
const ZEICHEN = { ok: '✓', hinweis: '!', fehler: '✕' };
const WORT = { ok: 'in Ordnung', hinweis: 'Hinweis', fehler: 'Problem' };

export function zeigeBefund(liste, ergebnis) {
  liste.replaceChildren(...(ergebnis.schritte || []).map((s) => {
    const li = document.createElement('li');
    li.className = `befund befund--${s.stand}`;
    const z = document.createElement('span');
    z.className = 'befund-zeichen';
    z.setAttribute('aria-hidden', 'true');
    z.textContent = ZEICHEN[s.stand] || '·';
    const was = document.createElement('b');
    was.textContent = `${tr(s.was)}: `;
    const wort = document.createElement('span');
    wort.className = 'sr-only';
    wort.textContent = `${tr(WORT[s.stand] || '')} – `;
    const text = document.createElement('span');
    text.append(was, wort, document.createTextNode(tr(s.text)));       // Texte vom Server nur als Text
    li.append(z, text);
    return li;
  }));
  liste.hidden = false;
}

// Ein Knopf prüft die Adresse aus einem Feld; das Ergebnis landet in der Liste darunter.
export function verbindePruefknopf({ knopf, feld, liste, koerper, api, toast }) {
  if (!knopf || !feld || !liste) return;
  knopf.addEventListener('click', async () => {
    knopf.disabled = true;
    liste.hidden = false;
    liste.replaceChildren(Object.assign(document.createElement('li'), { textContent: tr('Prüfe die Verbindung …') }));
    try {
      const r = await api('/api/verbindungstest', 'POST', { koerper, adresse: (feld.value || feld.placeholder || '').trim() });
      zeigeBefund(liste, r);
      toast(tr(r.ok ? 'Verbindung in Ordnung' : 'Verbindung noch nicht in Ordnung – siehe Liste'), !r.ok);
    } catch {
      liste.replaceChildren(Object.assign(document.createElement('li'), { textContent: tr('Prüfen ging nicht – läuft Knowlin noch?') }));
    } finally {
      knopf.disabled = false;
    }
  });
}
