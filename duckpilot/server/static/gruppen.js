// Bereiche der Leiste und ihre Reiter (seit 0.48 eigene Datei, damit app.js Platz behält).
// ── Bereiche ───────────────────────────────────────────────────────────
// Fünf Bereiche in der Leiste, nach dem, was man tut:
//   Steuern   – sie bewegen, mit ihr reden, Tricks abspielen
//   Alltag    – Uhr, Timer, Erinnerungen, Termine, To-dos (Erweiterung „Alltagsbuddy“)
//   Charakter – wer sie ist: Persönlichkeit, Stimme, Gespräch (womit sie denkt), Gedächtnis
//   Lernen    – Neues beibringen: Akrobatik, Parcours, Training
//   System    – Zustand und Pflege, Einstellungen, Erweiterungen
// Bereiche mit mehreren Seiten zeigen oben Reiter. Ein Reiter ist eine Seite (view) oder ein Teil
// einer Seite (part, über data-part).
export const GROUPS = [
  { id: 'steuern', tabs: [{ view: 'cockpit', label: 'Cockpit' }, { view: 'tricks', part: 'tricks', label: 'Tricks' },
    { view: 'tricks', part: 'tanz', label: 'Tanzen' }, { view: 'tricks', part: 'team', label: 'Team' },
    { view: 'tricks', part: 'hub', label: 'Vom Hub' }, { view: 'tricks', part: 'spiele', label: 'Spiele' },
    { view: 'tricks', part: 'zubehoer', label: 'Zubehör' },
    { view: 'tricks', part: 'ablauf', label: 'Ablauf' }] },
  { id: 'alltag', tabs: [{ view: 'alltag' }] },
  { id: 'umgebung', tabs: [{ view: 'umgebung' }] },                 // seit 0.38: eigener Bereich (Befund, Wahl)
  { id: 'charakter', tabs: [{ view: 'persoenlichkeit', label: 'Persönlichkeit' }, { view: 'stimme', part: 'stimme', label: 'Stimme' },
    { view: 'stimme', part: 'gespraech', label: 'Gespräch' }, { view: 'memory', label: 'Gedächtnis' },
    { view: 'knowlets', label: 'Knowlets' }] },
  { id: 'lernen', tabs: [{ view: 'akrobatik', label: 'Akrobatik' }, { view: 'parcours', label: 'Parcours' }, { view: 'training', label: 'Training' },
    { view: 'mentor', label: 'Mentor' }] },                           // Mentor (seit 0.48): auch im Körper

  { id: 'system', tabs: [{ view: 'dashboard', label: 'Körper' }, { view: 'settings', label: 'Einstellungen' },
    { view: 'tricks', part: 'pakete', label: 'Erweiterungen' }] },
  { id: 'design', tabs: [{ view: 'design' }] },
  { id: 'start', tabs: [{ view: 'start' }], kopf: true },           // Knowlin-Startseite (seit 0.38), ohne Leistenknopf
  // Kopf zuerst (seit 0.38.4): auf Knowlins Seiten die geteilten Bereiche, ohne die Körperbereiche
  { id: 'wissen', tabs: [{ view: 'memory', label: 'Gedächtnis' }, { view: 'knowlets', label: 'Knowlets' },
    { view: 'mentor', label: 'Mentor' }], kopf: true },               // Mentor als eigenes Modul (seit 0.48)
  { id: 'einstellungen', tabs: [{ view: 'settings', label: 'Einstellungen' }, { view: 'stimme', part: 'stimme', label: 'Knowlins Stimme' }], kopf: true },
];
