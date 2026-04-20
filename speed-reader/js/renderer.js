import { splitWord, measurePivotHalf, clearMeasurementCache } from './orp.js';

let slot = null;
let elPre = null;
let elPiv = null;
let elPost = null;
let elWpm = null;
let elProgress = null;
let fontSpec = '';
let lastHalf = -1;
let lastProgress = -1;

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
  elProgress = document.querySelector('.progress-fill');
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

export function renderProgress(index, total) {
  if (!elProgress || total <= 0) return;
  const pct = Math.min(100, Math.max(0, (index / total) * 100));
  if (Math.abs(pct - lastProgress) < 0.1) return;
  lastProgress = pct;
  elProgress.style.width = pct + '%';
}

export function clearWord() {
  if (!slot) return;
  elPre.textContent = '';
  elPiv.textContent = '';
  elPost.textContent = '';
}
