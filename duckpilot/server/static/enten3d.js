// Weitere Enten mit eigenem 3D-Modell (DPM2, `duckmodel.js`): Open Duck Mini (seit 0.38.4, liegt bei Knowlin) und
// WonderDuck (seit 0.53, Hiwonders Modell – beim ersten Wecken auf diesem PC geladen und gebacken). Bis ihr Modell da
// ist, steht die einfache Ente. Ausgelagert aus duck3d.js (Grenze 64 KB).
import { loadModel, RealDuck } from './duckmodel.js';
import { Duck } from './ente3d.js';

export const ENTEN = {
  open_duck_mini: { url: '/static/model/open_duck_mini.dpm', einfach: 'open_duck' },
  wonderduck: { url: '/api/modell/wonderduck.dpm', einfach: undefined },
};

// Die Figur für `view.koerper` (eine dieser Enten) – lädt ihr Modell einmal nach und wählt dann neu
export function enteWaehlen(view, art) {
  const e = ENTEN[art];
  view.enten = view.enten || {};
  const z = view.enten[art] || (view.enten[art] = {});
  if (!z.echt && !z.laedt) {
    z.laedt = true;
    loadModel(e.url).then((m) => {
      z.echt = new RealDuck(m);
      if (view.koerper === art) view._figurWaehlen();
    }).catch((err) => console.info(`Modell ${art} nicht da, einfache Ente bleibt:`, err.message))
      .finally(() => { z.laedt = false; });
  }
  return view.modelStyle === 'original' && z.echt ? z.echt : z.einfach || (z.einfach = new Duck(e.einfach));
}

// Hiwonders Modell ist fertig gebacken (Meldung „wonderduck“): fehlte es vorher (404), jetzt laden
export function enteNeuLaden(view, art) {
  if (view.koerper === art) view._figurWaehlen();
}
