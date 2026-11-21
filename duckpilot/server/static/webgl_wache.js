// Wenn die Grafikkarte die 3D-Ansicht zurücksetzt (seit 0.49.1, Maintainer: „auf einmal ist alles weiß“): Unter Windows
// kann der Grafiktreiber den WebGL-Kontext wegnehmen – etwa wenn die Stimme (Qwen) gleichzeitig auf derselben Grafikkarte
// rechnet. Dann bleibt die Fläche leer. Statt still weiß: Hinweis mit „Neu laden“; kommt der Kontext zurück, lädt das
// Fenster einmal von selbst neu (höchstens einmal pro Minute, damit es sich nicht im Kreis dreht).
export function initWebglWache(canvas, stage, tr = (t) => t) {
  if (!canvas || !stage) return;
  let hinweis = null;
  const neuLaden = () => {
    try { sessionStorage.setItem('knowlin-webgl-neu', String(Date.now())); } catch { /* ohne Speicher: trotzdem laden */ }
    location.reload();
  };
  canvas.addEventListener('webglcontextlost', (ev) => {
    ev.preventDefault();                       // sonst kommt der Kontext nie zurück
    if (hinweis) return;
    hinweis = document.createElement('div');
    hinweis.className = 'webgl-weg';
    hinweis.setAttribute('role', 'alert');
    const text = document.createElement('p');
    text.textContent = tr('Die Grafikkarte hat die 3D-Ansicht zurückgesetzt – die Ente selbst läuft weiter.');
    const knopf = document.createElement('button');
    knopf.type = 'button';
    knopf.className = 'btn btn--primary btn--sm';
    knopf.textContent = tr('3D-Ansicht neu laden');
    knopf.addEventListener('click', neuLaden);
    hinweis.append(text, knopf);
    stage.append(hinweis);
  });
  canvas.addEventListener('webglcontextrestored', () => {
    let zuletzt = 0;
    try { zuletzt = Number(sessionStorage.getItem('knowlin-webgl-neu')) || 0; } catch { /* egal */ }
    if (Date.now() - zuletzt > 60000) neuLaden();
  });
}
