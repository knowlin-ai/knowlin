// Ereignisse vom Körper: Liste im Dashboard, Laufschrift auf der Bühne, Raumklang, Spuren in 3D und auf der Karte
// (seit 0.38.17 aus app.js ausgelagert)
import { $, css } from './ui.js';
import { eventItem, eventLevel, SHOWN_EVENTS } from './dashboard.js';
import { playSound, playClip } from './voice.js';

export function initEreignisse({ getState, scene, map, addLine }) {
  // Räumlicher Klang (seit 0.38.4): wo ein anderer Roboter steht, gesehen von der eigenen Verkörperung (x vorn, y links)
  function ortVon(ev) {
    const st = getState();
    if (!ev.ente || typeof ev.x !== 'number' || !st) return null;
    const dx = ev.x - st.x, dy = ev.y - st.y, c = Math.cos(-st.yaw), s = Math.sin(-st.yaw);
    return { x: dx * c - dy * s, y: dx * s + dy * c };
  }
  const TICKER = new Set(['trick', 'gefuehl', 'goofy', 'charakter', 'fall', 'bump', 'pick', 'drop', 'kick', 'kick_miss', 'pick_miss', 'recover', 'reflex', 'memory', 'connected', 'disconnected']);
  function onEvent(ev) {
    if (ev.type === 'sound') {
      const cl = document.body.classList;   // nie Entenlaute bei Reachy & Co. und nicht, solange du bei Knowlin bist
      if (cl.contains('keine-ente') || cl.contains('im-kopf')) return;
      if (ev.clip) playClip(ev.clip);
      else if (!ev.on_robot) playSound(ev.tag, ev.klang, ortVon(ev));   // weitere Enten quaken mit eigener Stimme, von dort
      return;
    }
    if (SHOWN_EVENTS.has(ev.type) && ev.type !== 'curious') {
      const list = $('events');
      list.prepend(eventItem(ev));
      while (list.children.length > 60) list.lastChild.remove();
    }
    if (TICKER.has(ev.type) && ev.message) ticker(ev);
    const st = getState();
    if (st) {
      const at = [st.x, st.y];
      if (ev.type === 'fall') { scene.pulse('fall', ...at); map.ping(...at, css('--critical')); }
      if (ev.type === 'kick') { scene.pulse('kick', ...at); map.ping(...at, css('--accent')); }
      if (ev.type === 'memory') map.ping(...at, css('--data-1'));
      if (ev.type === 'goofy') { scene.feathers(); map.ping(...at, css('--accent')); }
    }
    if (ev.type === 'fall') addLine('event', 'Umgefallen!');
    if (ev.type === 'memory' && ev.message) addLine('event', ev.message);
  }

  function ticker(ev) {
    const list = $('ticker');
    const li = document.createElement('li');
    li.dataset.level = eventLevel(ev);
    li.textContent = ev.message;
    list.append(li);
    while (list.children.length > 4) list.firstChild.remove();
    setTimeout(() => li.classList.add('gone'), 4200);
    setTimeout(() => li.remove(), 4900);
  }

  return { onEvent };
}
