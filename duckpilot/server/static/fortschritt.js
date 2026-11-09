// Fortschritt beim Nachinstallieren (Physik, Stimme, Lernen …) – seit 0.38.38, Hinweis: „ggf kann bei in app
// Downloads oder Updates ein Fortschrittsbalken sein – man sieht immer nicht, was gerade passiert oder ob es hängt“.
// Der Server liest pips Fortschritt mit (voice/install.py: job.laden = { datei, geladen, gesamt }).

export const mb = (n) => ((n || 0) / 1048576).toFixed((n || 0) < 10485760 ? 1 : 0).replace('.', ',');

// „torch-2.5.1+rocm6.2-cp313-cp313-win_amd64.whl“ → „torch-2.5.1+rocm6.2“ (auch aus einer vollen Adresse)
export function dateiName(datei) {
  if (!datei) return '';
  let n = datei.split('/').pop();
  try { n = decodeURIComponent(n); } catch { /* bleibt roh */ }
  return n.replace(/-(?:cp|py)\d.*$/, '').replace(/\.(?:whl|tar\.gz|zip)$/, '');
}

// Ein Satz, was gerade passiert – mit Schritt, Datei und MB, sobald pip das meldet
export function installStand(job) {
  if (!job) return '';
  const schritt = job.schritte > 1 ? `Schritt ${job.schritt || 1} von ${job.schritte} – ` : '';
  const l = job.laden;
  if (l && l.gesamt) return `${schritt}lädt ${dateiName(l.datei)}: ${mb(l.geladen)} von ${mb(l.gesamt)} MB`;
  if (l && l.installiert) return `${schritt}richtet die geladenen Pakete ein …`;
  const letzte = (job.zeilen || []).slice(-1)[0];
  return `${schritt}${letzte || 'startet …'}`;
}

// Balken: echter Anteil beim Herunterladen, sonst „läuft“ (Dauer unbekannt)
export function installBalken(el, job) {
  const l = job && job.laden;
  const b = el('div', 'bar');
  b.setAttribute('role', 'progressbar');
  if (l && l.gesamt) {
    const anteil = Math.min(1, (l.geladen || 0) / l.gesamt);
    const i = el('i');
    i.style.width = `${Math.round(anteil * 100)}%`;
    b.append(i);
    b.setAttribute('aria-valuenow', String(Math.round(anteil * 100)));
    b.setAttribute('aria-valuemin', '0');
    b.setAttribute('aria-valuemax', '100');
    b.setAttribute('aria-label', `${dateiName(l.datei)} wird geladen`);
  } else {
    b.classList.add('is-busy');
    b.setAttribute('aria-label', 'Installation läuft');
  }
  return b;
}
