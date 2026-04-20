import { splitWord, measurePivotHalf } from './orp.js';

const slot = () => document.querySelector('.word-slot');
const elPre = () => document.querySelector('.word-slot .pre');
const elPiv = () => document.querySelector('.word-slot .piv');
const elPost = () => document.querySelector('.word-slot .post');
const elWpm = () => document.querySelector('.wpm-label em');

function currentFontSpec() {
  const el = slot();
  if (!el) return '400 64px ui-serif, Georgia, serif';
  const cs = getComputedStyle(el);
  return `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
}

export function renderToken(token) {
  if (!slot()) return;
  const { pre, piv, post } = splitWord(token);
  elPre().textContent = pre;
  elPiv().textContent = piv;
  elPost().textContent = post;

  const half = measurePivotHalf(piv, currentFontSpec());
  slot().style.setProperty('--pivot-half', half + 'px');
}

export function renderWpm(wpm) {
  const el = elWpm();
  if (el) el.textContent = `${wpm} wpm`;
}

export function clearWord() {
  if (!slot()) return;
  elPre().textContent = '';
  elPiv().textContent = '';
  elPost().textContent = '';
}
