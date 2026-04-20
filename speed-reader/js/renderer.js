import { splitWord, measurePivotHalf, clearMeasurementCache } from './orp.js';

let slot = null;
let elPre = null;
let elPiv = null;
let elPost = null;
let elWpm = null;
let fontSpec = '';
let lastHalf = -1;

function computeFontSpec() {
  if (!slot) return '';
  const cs = getComputedStyle(slot);
  return `${cs.fontStyle} ${cs.fontWeight} ${cs.fontSize} ${cs.fontFamily}`;
}

export function mount() {
  slot = document.querySelector('.word-slot');
  elPre = document.querySelector('.word-slot .pre');
  elPiv = document.querySelector('.word-slot .piv');
  elPost = document.querySelector('.word-slot .post');
  elWpm = document.querySelector('.wpm-label em');
  fontSpec = computeFontSpec();

  window.addEventListener('resize', refreshFontSpec);
}

function refreshFontSpec() {
  const next = computeFontSpec();
  if (next !== fontSpec) {
    fontSpec = next;
    clearMeasurementCache();
    lastHalf = -1;
  }
}

export function renderToken(token) {
  if (!slot) return;
  const { pre, piv, post } = splitWord(token);
  elPre.textContent = pre;
  elPiv.textContent = piv;
  elPost.textContent = post;

  const half = measurePivotHalf(piv, fontSpec);
  if (half !== lastHalf) {
    slot.style.setProperty('--pivot-half', half + 'px');
    lastHalf = half;
  }
}

export function renderWpm(wpm) {
  if (elWpm) elWpm.textContent = `${wpm} wpm`;
}

export function clearWord() {
  if (!slot) return;
  elPre.textContent = '';
  elPiv.textContent = '';
  elPost.textContent = '';
}
