// Einstellungen: Sprungleiste links. Ein Knopf je sichtbarem Abschnitt (Titel aus der Kachel),
// der aktuelle Abschnitt ist markiert. Keine Ankerlinks – die Adresse (#settings/…) bleibt der Router.

export function initSettingsNav(h) {
  const { $, el, showView } = h;
  const nav = $('settings-nav');
  const scroller = document.querySelector('#view-settings .page');
  if (!nav || !scroller) return { render() {} };
  let observer = null;

  function sections() {
    return [...document.querySelectorAll('#view-settings .settings-list > section[id^="set-"]')]
      .filter((s) => !s.hidden && getComputedStyle(s).display !== 'none');
  }

  function mark(id) {
    for (const b of nav.querySelectorAll('button')) b.setAttribute('aria-current', String(b.dataset.target === id));
  }

  function render() {
    const list = sections();
    nav.replaceChildren(...list.map((s) => {
      const b = el('button', null, (s.querySelector('h3') || {}).textContent || s.id);
      b.type = 'button';
      b.dataset.target = s.id;
      b.addEventListener('click', () => { showView('settings', s.id.slice(4)); mark(s.id); });
      return b;
    }));
    if (observer) observer.disconnect();
    observer = new IntersectionObserver((entries) => {
      const seen = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
      if (seen.length) mark(seen[0].target.id);
    }, { root: scroller, rootMargin: '0px 0px -70% 0px' });
    for (const s of list) observer.observe(s);
    if (list.length) mark(list[0].id);
  }

  return { render };
}
