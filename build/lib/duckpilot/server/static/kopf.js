// Gespräch mit Knowlins Kopf auf der Startseite (seit 0.38.8, Quickstart-Entwurf vom 5.11.): „Hallo Mensch“, darunter
// das Dialogfeld, links der Kopf als wabernde Form. Hier antwortet Knowlin selbst – ohne Körper, seriös, mit eigener
// tiefer Stimme. Will der Mensch etwas Körperliches, nennt Knowlin den Körper und fragt, ob er ihn nutzen soll; auf
// „ja“ geht er hinein (derselbe Übergang wie auf den Kacheln) und gibt den Wunsch an die Verkörperung weiter (seit 0.38.9).
import { initMind } from './mind.js';
import { uebersetzeText } from './i18n.js';

const tr = (text) => (text ? uebersetzeText(text) || text : '');
const MAX_ZEILEN = 8;

export function initKopf({ $, el, toast, sendChat, vorlesen, figurWecken, isRemote, aufStartseite, mikro }) {
  const form = $('kopf-form');
  if (!form) return { onChat() {}, denkt() {}, namen() {}, partial() {}, hoert() {}, vorschlaege() {} };
  const mind = initMind($('mind'));
  const verlauf = $('kopf-verlauf');
  const feld = $('kopf-text');
  let denkenEl = null;
  let sprichtGerade = false;
  let kopfName = 'Knowlin';

  const ruhe = () => mind.setZustand(sprichtGerade ? 'spricht' : denkenEl ? 'denkt'
    : document.activeElement === feld && feld.value ? 'hoert' : 'ruhe');

  function zeile(art, text, meta) {
    verlauf.hidden = false;
    const p = el('p', `kopf-zeile kopf-zeile--${art}`);
    p.translate = false;                     // eigene Worte und Antworten nie übersetzen lassen
    p.append(el('span', 'kopf-wer', art === 'mensch' ? tr('Du') : kopfName), el('span', 'kopf-text', text));
    if (meta) p.append(el('span', 'kopf-meta', meta));
    verlauf.append(p);
    while (verlauf.querySelectorAll('.kopf-zeile').length > MAX_ZEILEN) verlauf.querySelector('.kopf-zeile').remove();
    verlauf.scrollTop = verlauf.scrollHeight;
    return p;
  }

  // Vorschlag „soll ich Quacki nutzen?“: der Knopf antwortet mit „ja“ – so steht es auch im Gespräch
  function nutzenKnopf(p, figur) {
    const b = el('button', 'btn btn--primary btn--sm kopf-wecken', tr(`${figur} nutzen`));
    b.type = 'button';
    b.addEventListener('click', () => { b.disabled = true; senden(tr('Ja')); });
    p.append(b);
  }

  // In einen Körper gehen und der Verkörperung den Wunsch weitergeben („tanz“) – nach dem Übergang, dann im Körper
  async function wecken(modul, auftrag) {
    if (isRemote && isRemote()) { toast(tr('Die Verkörperung wechseln geht nur am PC'), true); return; }
    const ok = await figurWecken(modul);
    if (ok && auftrag) setTimeout(() => sendChat(auftrag, 'text'), 500);
  }

  function senden(text) {
    text = (text || '').trim();
    if (!text) return;
    sendChat(text, 'text');
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    senden(feld.value);
    feld.value = '';
    ruhe();
  });
  feld.addEventListener('input', ruhe);
  feld.addEventListener('focus', ruhe);
  feld.addEventListener('blur', ruhe);

  // Halten und sprechen – dieselbe Spracherkennung wie im Cockpit, die Antwort kommt vom Kopf
  const mic = $('kopf-mic');
  if (mic && mikro) {
    mic.addEventListener('pointerdown', (e) => { e.preventDefault(); mikro(true); });
    mic.addEventListener('pointerup', (e) => { e.preventDefault(); mikro(false); });
    mic.addEventListener('pointerleave', () => mikro(false));
    mic.addEventListener('keydown', (e) => { if ((e.key === ' ' || e.key === 'Enter') && !e.repeat) { e.preventDefault(); mikro(true); } });
    mic.addEventListener('keyup', (e) => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); mikro(false); } });
  }

  // Vorschläge unter dem Feld: zum Loslegen, ohne zu wissen, was man fragen kann
  function vorschlaege(figuren) {
    const box = $('kopf-vorschlaege');
    if (!box) return;
    // nur, was Knowlin ohne Körper ausmacht – Körperliches gehört zu den Verkörperungen (Hinweis aus dem Test, 0.38.10)
    const saetze = [tr('Wer bist du?'), tr('Was kannst du?'), tr('Was weißt du über mich?')];
    box.replaceChildren(...saetze.map((s) => {
      const b = el('button', 'btn btn--ghost btn--sm kopf-vorschlag', s);
      b.type = 'button';
      b.addEventListener('click', () => senden(s));
      return b;
    }));
  }

  function denkt(an) {
    if (an && !denkenEl) {
      denkenEl = el('p', 'kopf-zeile kopf-zeile--denkt');
      denkenEl.append(el('span', 'kopf-wer', kopfName), el('span', 'kopf-text', tr('denkt nach …')));
      verlauf.hidden = false;
      verlauf.append(denkenEl);
      verlauf.scrollTop = verlauf.scrollHeight;
    } else if (!an && denkenEl) {
      denkenEl.remove();
      denkenEl = null;
    }
    ruhe();
  }

  function onChat(m) {
    if (m.role === 'user') {
      zeile('mensch', m.text, m.via === 'stimme' || m.via === 'weckwort' ? tr('gesprochen') : null);
      return;
    }
    const meta = m.source === 'claude' ? `Claude, ${m.seconds} s` : m.source === 'lokal' ? tr(`eigenes Modell, ${m.seconds} s`)
      : m.source === 'anbieter' ? tr(`anderes Modell, ${m.seconds} s`) : m.source === 'reflex' ? tr('sofort, ohne Claude')
        : tr('einfache Befehle');
    const p = zeile('kopf', m.text, meta);
    if (m.vorschlag && m.vorschlag.modul) nutzenKnopf(p, m.vorschlag.figur);
    if (!aufStartseite()) toast(`${kopfName}: ${m.text}`);
    vorlesen(m, {
      kopf: true,                            // ohne Schnabel der Verkörperung, nie albern
      onStart: () => { sprichtGerade = true; ruhe(); },
      onEnd: () => { sprichtGerade = false; ruhe(); },
    });
    // In den Körper gehen: erst kurz die Antwort zeigen, dann der Übergang, dann der Auftrag an die Verkörperung
    if (m.wecken) setTimeout(() => wecken(m.wecken, m.auftrag), 900);
  }

  // Namen (seit 0.38.9): „Hallo Mensch“, bis der Mensch seinen Namen sagt oder einstellt; Knowlins Name ebenso
  function namen(cfg) {
    kopfName = (cfg && cfg.kopf_name) || 'Knowlin';
    const mensch = cfg && cfg.nutzer_name;
    $('kopf-gruss').textContent = mensch ? tr(`Hallo ${mensch}`) : tr('Hallo Mensch');
    $('kopf-satz').textContent = tr(`Ich bin ${kopfName}. Eine intelligente, selbstlernende Lebensform.`);
    feld.placeholder = tr(`Schreib ${kopfName} etwas …`);
    $('kopf-verlauf').setAttribute('aria-label', tr(`Gespräch mit ${kopfName}`));
    for (const w of verlauf.querySelectorAll('.kopf-zeile:not(.kopf-zeile--mensch) .kopf-wer')) w.textContent = kopfName;
  }

  return {
    onChat,
    denkt,
    namen,
    vorschlaege,
    partial(t) { if (aufStartseite()) feld.placeholder = t || tr(`Schreib ${kopfName} etwas …`); },
    hoert(an) {
      if (mic) mic.setAttribute('aria-pressed', an ? 'true' : 'false');
      if (an) mind.setZustand('hoert'); else ruhe();
    },
  };
}
