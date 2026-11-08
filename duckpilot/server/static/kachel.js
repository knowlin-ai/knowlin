// Kachel unten links auf der Bühne: Tiefensensor oder Kamerabild (Simulator: Blick aus dem Kopf, Roboter: mediad)
// (seit 0.38.17 aus app.js ausgelagert)
import { $ } from './ui.js';

export function initKachel({ getConfig, getView, scene, recall, remember }) {
  let tileMode = recall('tile') === 'kamera' ? 'kamera' : 'tiefe';
  // Ohne Tiefensensor (Reachy, Open Duck) zeigt die Kachel nur das Kamerabild, ohne Umschalter (0.38.14)
  const nurKamera = () => document.body.classList.contains('ohne-tiefensensor');
  function setTile(mode) {
    tileMode = mode;
    remember('tile', mode);
    const cam = mode === 'kamera' || nurKamera(), robot = getConfig().backend === 'robotd';
    $('sensor-tile').setAttribute('aria-pressed', String(cam));
    $('sensor-tile').disabled = nurKamera();
    $('sensor-tile').title = nurKamera() ? 'Kamerabild aus dem Kopf' : 'Umschalten: Tiefensensor oder Kamerabild';
    $('sensor-tile-tag').textContent = cam ? 'Kamera' : 'Tiefe';
    $('tof').hidden = cam;
    $('tile-cam').hidden = !cam || robot;
    $('tile-cam-img').hidden = !cam || !robot;
    $('sensor-tile').classList.toggle('is-cam', cam);
    $('sensor-head').textContent = cam ? (robot ? 'Kopfkamera' : 'Kopfkamera (Simulator)') : 'Frei bis zum Hindernis';
  }
  $('sensor-tile').addEventListener('click', () => setTile(tileMode === 'kamera' ? 'tiefe' : 'kamera'));
  setTile(tileMode);
  let tileBusy = false;
  setInterval(async () => {
    if ((tileMode !== 'kamera' && !nurKamera()) || getView() !== 'cockpit' || document.hidden) return;
    if (getConfig().backend !== 'robotd') { scene.snapshotPov($('tile-cam')); return; }
    if (tileBusy) return;
    tileBusy = true;
    try {
      const r = await fetch('/api/kamera/bild', { cache: 'no-store' });
      if (r.ok && (r.headers.get('content-type') || '').startsWith('image/')) {
        const url = URL.createObjectURL(await r.blob());
        const img = $('tile-cam-img');
        const old = img.src;
        img.src = url;
        if (old.startsWith('blob:')) URL.revokeObjectURL(old);
      } else {
        $('sensor-head').textContent = 'Kamera nicht erreichbar';
      }
    } catch { /* nächster Versuch */ }
    tileBusy = false;
  }, 250);
  $('hud-help-btn').addEventListener('click', () => {
    const open = $('hud-help').hidden;
    $('hud-help').hidden = !open;
    $('hud-help-btn').setAttribute('aria-expanded', String(open));
  });

  return { setTile, get modus() { return tileMode; } };
}
