// Charakter je Verkörperung (seit 0.38.10, Wunsch des Maintainers): Knowlin hat einen eigenen Grundcharakter (Einstellungen →
// Knowlin); seit 5.11. wirkt er nur auf Knowlin – jede Verkörperung hat ihren eigenen Charakter, anpassbar in ihrem Körper
// oder als Punkt in Knowlins Feld (`figur_profil`) – plus Eigenschaften, die nur ihre Gestalt hat (Schnabel, Antennen,
// Tollpatschigkeit …). Die Liste kommt vom Server (`config.gestalt`).
import { initGedankenspur } from './gedankenspur.js';
import { t, uebersetzeText } from './i18n.js';
import { KNOWLIN_NAMEN, KNOWLIN_TEXTE, PersonalityPad } from './personality.js';

const tr = (t) => (t ? uebersetzeText(t) || t : '');

// Vergleich mit Knowlin ganz aus dem Katalog (de/en.json „charakter.*“), damit er auf Englisch vollständig übersetzt ist
function richtung(d, plus, minus) {
  if (Math.abs(d) < 0.05) return '';
  const wie = Math.abs(d) >= 0.25 ? t('charakter.deutlich', {}, 'deutlich') : t('charakter.etwas', {}, 'etwas');
  return `${wie} ${d > 0 ? plus : minus}`;
}

export function initCharakter({ $, el, save }) {
  initGedankenspur();                     // Gedankenspur unter Persönlichkeit (seit 0.38.44)
  // Grundcharakter als Feld mit Quadranten (Wunsch des Maintainers 5.11.) – die Verkörperungen als Punkte, einzeln ziehbar
  const feld = $('pad-knowlin') && new PersonalityPad($('pad-knowlin'), {
    onCommit: (w) => save(w), namen: KNOWLIN_NAMEN, texte: KNOWLIN_TEXTE, goofy: false, leerlauf: false,
    achsen: { oben: 'verspielt', unten: 'seriös', links: 'ruhig', rechts: 'lebhaft' },
    titel: 'Grundcharakter von Knowlin', schluessel: ['grund_energie', 'grund_humor'],
    onMarke: (modul, energie, humor) => save({ figur_profil: { modul, energie, humor } }),
  });
  const liste = $('gestalt-liste');
  if (!liste) return { zeigen() {} };
  let an = [];

  function zeigen(cfg) {
    if (!cfg) return;
    if (feld) {
      feld.set(cfg.grund_energie ?? 0.35, cfg.grund_humor ?? 0.1);
      feld.marken((cfg.verkoerperungen || []).map((f) => ({ id: f.modul, name: f.name, x: f.energie, y: f.humor, aktiv: f.wach })));
    }
    const name = cfg.duck_name || '';
    const de = (cfg.energie ?? 0.5) - (cfg.grund_energie ?? 0.35);
    const dh = (cfg.humor ?? 0.25) - (cfg.grund_humor ?? 0.1);
    const teile = [richtung(de, t('charakter.lebhafter', {}, 'lebhafter'), t('charakter.ruhiger', {}, 'ruhiger')),
      richtung(dh, t('charakter.verspielter', {}, 'verspielter'), t('charakter.ernster', {}, 'ernster'))].filter(Boolean);
    $('auspraegung').textContent = teile.length
      ? t('charakter.vergleich', { name, wie: teile.join(` ${t('charakter.und', {}, 'und')} `) }, '{name} ist {wie} als Knowlin.')
      : t('charakter.gleich', { name }, '{name} ist wie Knowlin selbst.');
    const gestalt = cfg.gestalt || [];
    $('gestalt').hidden = !gestalt.length;
    an = gestalt.filter((e) => e.an).map((e) => e.id);
    liste.replaceChildren(...gestalt.map((e) => {
      const lab = el('label', 'switch');
      const box = el('input');
      box.type = 'checkbox';
      box.checked = e.an;
      box.addEventListener('change', () => {
        an = box.checked ? [...an, e.id] : an.filter((x) => x !== e.id);
        save({ eigenschaften: an });
      });
      const t = el('span', null, tr(e.name));
      t.append(el('small', null, tr(e.text)));
      lab.append(box, t);
      return lab;
    }));
  }

  return { zeigen };
}
