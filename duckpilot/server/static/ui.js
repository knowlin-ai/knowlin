// Kleine DOM-Helfer, die fast jedes Modul braucht (seit 0.38.17 aus app.js ausgelagert)
export const $ = (id) => document.getElementById(id);
export const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export const REDUCED = !!(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);

export function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

export function toast(text, bad = false) {
  const t = document.createElement('div');
  t.className = bad ? 'toast toast--bad' : 'toast';
  t.textContent = text;
  $('toasts').append(t);
  setTimeout(() => t.remove(), 2500);
}
