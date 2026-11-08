// Herkunft (seit 0.38.10, Wunsch des Maintainers): wo Knowlin etwas gelernt hat – ohne Körper („kopf“) oder in einer
// Verkörperung („duckpilot:sim“, „reachy_mini:echt“ …). Namen kommen vom Server (`herkuenfte`: Kennung → Name).
import { uebersetzeText } from './i18n.js';

const tr = (t) => (t ? uebersetzeText(t) || t : '');

export function herkunftName(id, namen = {}) {
  if (!id) return tr('Herkunft unbekannt');
  const [modul, ort] = String(id).split(':');
  const name = namen[modul] || (modul === 'kopf' ? 'Knowlin' : modul);
  if (modul === 'kopf') return tr(`${name} (ohne Körper)`);
  return ort === 'echt' ? tr(`${name} (echt)`) : tr(`${name} (Simulator)`);
}

// {"duckpilot:sim": 3, "kopf": 1} → „3× Quacki (Simulator), 1× Knowlin (ohne Körper)“
export function herkunftListe(h, namen = {}) {
  const teile = Object.entries(h || {}).sort((a, b) => b[1] - a[1]);
  if (!teile.length) return tr('Herkunft unbekannt (aus der Zeit vor 0.38.10)');
  return teile.map(([id, n]) => `${n}× ${herkunftName(id, namen)}`).join(', ');
}

// Passt ein Eintrag zum Filter? Filter: '' (alle), 'kopf', '<modul>', 'sim', 'echt', 'unbekannt'
export function passt(h, filter) {
  if (!filter) return true;
  const ids = Object.keys(h || {});
  if (filter === 'unbekannt') return !ids.length;
  if (filter === 'sim' || filter === 'echt') return ids.some((i) => i.endsWith(`:${filter}`));
  return ids.some((i) => i === filter || i.startsWith(`${filter}:`));
}
