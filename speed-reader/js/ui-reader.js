import * as state from './state.js';
import * as player from './player.js';
import { renderWpm, renderProgress } from './renderer.js';
import * as storage from './storage.js';

const AUTO_HIDE_MS = 2000;
const SENTENCE_END_RE = /[.!?]/;

let hideTimer = null;
let onClose = null;
let playPauseEl = null;

function clearHideTimer() {
  if (hideTimer !== null) {
    clearTimeout(hideTimer);
    hideTimer = null;
  }
}

function resetHideTimer() {
  clearHideTimer();
  hideTimer = setTimeout(() => {
    if (state.get().playing) hideControls();
  }, AUTO_HIDE_MS);
}

export function showControls() {
  document.body.classList.add('controls-visible');
  resetHideTimer();
}

export function hideControls() {
  document.body.classList.remove('controls-visible');
  clearHideTimer();
}

function togglePlay() {
  const nowPlaying = player.toggle();
  if (nowPlaying) hideControls();
  else showControls();
}

function close() {
  player.pause();
  hideControls();
  if (onClose) onClose();
}

function isBoundary(t) {
  return t.isBreak || SENTENCE_END_RE.test(t.trailing);
}

function nextSentenceStart(tokens, from, dir) {
  if (dir > 0) {
    for (let j = from; j < tokens.length; j++) {
      if (isBoundary(tokens[j])) return j + 1;
    }
    return tokens.length - 1;
  }
  let i = from - 2;
  while (i > 0) {
    if (isBoundary(tokens[i])) return i + 1;
    i--;
  }
  return 0;
}

function seekTo(target) {
  const s = state.get();
  const clamped = Math.max(0, Math.min(s.tokens.length - 1, target));
  player.seek(clamped);
  renderProgress(clamped, s.tokens.length);
  showControls();
}

export function mount(opts) {
  onClose = opts.onClose;

  const tap = document.querySelector('.tap-surface');
  playPauseEl = document.querySelector('.play-pause');
  const closeBtn = document.querySelector('.close');
  const slider = document.querySelector('.wpm-slider');
  const progressBar = document.querySelector('.progress');

  if (tap) tap.addEventListener('click', togglePlay);

  if (playPauseEl) {
    playPauseEl.addEventListener('click', (e) => {
      e.stopPropagation();
      togglePlay();
      playPauseEl.blur();
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      close();
    });
  }

  if (slider) {
    slider.addEventListener('input', () => {
      const wpm = parseInt(slider.value, 10);
      state.set({ wpm });
      storage.patchSettings({ wpm });
      renderWpm(wpm);
      resetHideTimer();
    });
  }

  if (progressBar) {
    progressBar.addEventListener('click', (e) => {
      const rect = progressBar.getBoundingClientRect();
      const ratio = (e.clientX - rect.left) / rect.width;
      seekTo(Math.floor(ratio * state.get().tokens.length));
    });
  }

  state.subscribe((s) => {
    if (playPauseEl) playPauseEl.classList.toggle('is-playing', s.playing);
  });
}

export function handleKey(e) {
  if (e.target && e.target.tagName === 'BUTTON' && e.key === ' ') return;
  if (e.key === ' ') {
    e.preventDefault();
    togglePlay();
  } else if (e.key === 'Escape') {
    e.preventDefault();
    close();
  } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
    e.preventDefault();
    const dir = e.key === 'ArrowRight' ? 1 : -1;
    if (e.shiftKey) {
      seekTo(player.getIndex() + dir);
    } else {
      seekTo(nextSentenceStart(state.get().tokens, player.getIndex(), dir));
    }
  }
}
