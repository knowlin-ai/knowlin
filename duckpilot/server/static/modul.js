// Körpermodus (seit 0.38.1, seit 0.38.4 für alle Körper nach derselben Logik): Gleicher Aufbau für jeden Körper,
// angepasst wird nur, was er hat. <body> bekommt die Klassen koerper-microduck|reachy|open-duck und ohne-<eigenschaft>
// (aus den Körper-Eigenschaften des Servers); style.css blendet damit aus, was fehlt (braucht-beine,
// braucht-tiefensensor) oder nur zu einem Körper gehört (nur-microduck, nur-reachy, nur-ente, ohne-microduck).
// Was nicht geht, ist nicht da – statt anklickbar zu sein und dann abzulehnen.
import { uebersetzeText } from './i18n.js';

const tr = (text) => uebersetzeText(text) || text;

// Körper je Einstellung `modul`: CSS-Klasse und Name in der Kopfzeile
export const KOERPER = {
  duckpilot: { klasse: 'microduck', name: 'Microduck', ente: true },
  reachy_mini: { klasse: 'reachy', name: 'Reachy Mini', ente: false },
  open_duck_mini: { klasse: 'open-duck', name: 'Open Duck Mini v2', ente: true },
  so101: { klasse: 'so101', name: 'SO-101', ente: false },             // Arm (seit 0.38.47, G5)
};
const OHNE = ['beine', 'tiefensensor', 'schnabel', 'antennen', 'kamera', 'kopf', 'arm'];
// Unterseiten, die es nur bei der Microduck gibt (Pollens Policies, Hub-Tricks, weitere Microducks)
const NUR_MICRODUCK = ['tricks/team', 'tricks/hub', 'akrobatik', 'parcours', 'training'];
// Unterseiten, die es nur bei Reachy Mini gibt (Kamera-Spiele, seit 0.38.13)
const NUR_REACHY = ['tricks/spiele'];

export function setzeModul(config, { $, hiddenTabs }) {
  const k = KOERPER[config.modul] || KOERPER.duckpilot;
  const eig = new Set(config.eigenschaften || ['beine', 'kopf', 'schnabel', 'tiefensensor']);
  const cl = document.body.classList;
  for (const x of Object.values(KOERPER)) cl.toggle(`koerper-${x.klasse}`, x === k);
  for (const e of OHNE) cl.toggle(`ohne-${e}`, !eig.has(e));
  cl.toggle('keine-ente', !k.ente);                       // Entenstimme, Entenlaute, Leerlauf-Gesten nur bei Enten
  const microduck = k.klasse === 'microduck';
  for (const t of NUR_MICRODUCK) { if (microduck) hiddenTabs.delete(t); else hiddenTabs.add(t); }
  for (const t of NUR_REACHY) { if (k.klasse === 'reachy') hiddenTabs.delete(t); else hiddenTabs.add(t); }
  if (eig.has('kopf')) hiddenTabs.delete('tricks/tanz'); else hiddenTabs.add('tricks/tanz');   // Tanzen braucht einen Kopf
  const lernen = $('rail-lernen');
  if (lernen) lernen.hidden = !microduck;
  // Kopfzeile „Knowlin › Verkörperung · Körper“
  const koerper = $('geist-koerper');
  if (koerper) koerper.textContent = tr(k.name);
}
