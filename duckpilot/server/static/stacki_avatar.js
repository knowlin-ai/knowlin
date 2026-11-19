// Vorschaubilder für die Gesichter von Stack-chan (seit 0.39): jedes Bild zeigt den Avatar mit ruhigem Blick, gezeichnet mit
// derselben Funktion wie der Bildschirm in der 3D-Ansicht. Die Wahl selbst speichert das Einstellungsfeld (data-set).
import { gesichtZeichnen } from './stackchan3d.js';

function vorschau() {
  for (const c of document.querySelectorAll('canvas.avatarbild')) {
    const ctx = c.getContext('2d');
    if (ctx) gesichtZeichnen(ctx, { a: 'ruhig', bx: 0.3, s: c.dataset.avatar || 'standard' });
  }
}

if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', vorschau);
else vorschau();
