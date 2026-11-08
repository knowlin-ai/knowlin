// Odi ausprobieren (T4, seit 0.38.29): Gangformel und Wortverständnis – ohne Seite und ohne 3D, damit Tests sie prüfen.
// Die Gangformel ist die des einfachen Simulators (duckpilot/backends/sim.py → display_joints), Winkel in der
// Konvention der Microduck; das Modell der Open Duck rechnet sie selbst um (head.von_microduck).

// ── Gangformel des einfachen Simulators (sim.py, display_joints) ─────────────────────────────────────────────
const STAND_LEG = [0.0, -0.0873, -0.4579, -0.0049, 0.4530];
const SIT_LEG = [0.0, 0.0, -0.5236, 1.0472, 0.0];
const HOME_NECK = 0.3491, HOME_HEAD = 0.3491;
export const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

export function gelenke({ fold = 0, vx = 0, vyaw = 0, phase = 0, kopf = { neck: 0, pitch: 0, yaw: 0, roll: 0 } } = {}) {
  const base = STAND_LEG.map((a, i) => a + (SIT_LEG[i] - a) * fold);
  const stride = clamp(vx / 0.25, -1, 1);
  const turn = clamp(vyaw / 1.0, -1, 1);
  const moving = fold > 0.5 ? 0 : 1;
  const lift = moving * Math.min(1, Math.abs(stride) + Math.abs(turn) * 0.6);
  const beine = [[1, phase], [-1, phase + Math.PI]].map(([seite, ph]) => {
    const swing = Math.sin(ph), up = Math.max(0, Math.sin(ph)) * lift;
    return [base[0] + 0.16 * turn * swing * seite, base[1] + 0.05 * Math.cos(ph) * lift, base[2] + 0.22 * stride * swing * moving,
      base[3] + 0.70 * up, base[4] + 0.30 * up - 0.18 * stride * swing * moving];
  });
  const rechts = beine[1].map((v) => -v);
  return [...beine[0], HOME_NECK + kopf.neck, HOME_HEAD + kopf.pitch, kopf.yaw, kopf.roll, 0, ...rechts];
}

// ── Was Odi versteht (ein paar Wörter, Deutsch und Englisch) ───────────────────────────────────────────────────
// Reihenfolge zählt: „geh zum Ball“ ist der Ball, „dreh dich nach rechts“ ist rechts. Deutsche Wortstämme ohne Ende
// (tanz → tanze, tanzen), englische Wörter ganz.
const WOERTER = [
  ['ball', /ball/],
  ['hallo', /(hallo|(^|\s)hi\b|hello|(^|\s)hey\b|moin|servus)/],
  ['aufstehen', /(^|\s)(steh|aufsteh|stand)/],
  ['sitzen', /(^|\s)(setz|sitz|sit\b)/],
  ['tanzen', /(^|\s)(tanz|dance)/],
  ['nicken', /(^|\s)(nick|nod\b|ja\b|yes\b)/],
  ['schuetteln', /(schüttel|schuettel|shake|(^|\s)nein\b|(^|\s)no\b)/],
  ['umschauen', /(^|\s)(schau|guck|umschau|look)/],
  ['halt', /(^|\s)(stopp?\b|halt|anhalt|bleib|stay)/],
  ['zurueck', /(zurück|zurueck|rückwärts|rueckwaerts|back)/],
  ['rechts', /(rechts|right)/],
  ['links', /(links|left|(^|\s)dreh|(^|\s)turn)/],
  ['vor', /(^|\s)(geh|lauf|vor|komm|walk|go\b|forward|come)/],
];
export function verstehen(satz) {
  const s = ` ${String(satz || '').toLowerCase()} `;
  for (const [was, muster] of WOERTER) if (muster.test(s)) return was;
  return null;
}
