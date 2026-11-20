// Leistungsmodus (seit 0.47): Darstellung „Sparsam“ unter Einstellungen → Darstellung. Die 3D-Ansicht rechnet dann mit
// 30 Bildern pro Sekunde ohne Schatten und Verdeckung (duck3d.js), das Gehirn-Bild zeichnet seltener (hirn.js), und
// <body class="sparsam"> nimmt der Oberfläche Bewegung (bereiche/zubehoer.css). Gilt nur in diesem Browser.
export function initLeistungsmodus() {
  let q = null;
  try { q = localStorage.getItem('duckpilot.quality3d'); } catch { /* privat */ }
  document.body.classList.toggle('sparsam', q === 'sparsam');
  for (const r of document.querySelectorAll('input[name=quality3d]')) {
    r.addEventListener('change', () => document.body.classList.toggle('sparsam', r.value === 'sparsam'));
  }
}
