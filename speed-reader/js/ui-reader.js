import * as state from './state.js';
import * as player from './player.js';
import { renderWpm, renderProgress } from './renderer.js';
import * as storage from './storage.js';

const AUTO_HIDE_MS = 2000;

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

function seekByWord(delta) {
  const target = player.getIndex() + delta;
  player.seek(target);
  showControls();
  const s = state.get();
  if (s.tokens[target]) renderProgress(target, s.tokens.length);
}

function seekBySentence(delta) {
  const s = state.get();
  const tokens = s.tokens;
  let i = player.getIndex();
  if (delta > 0) {
    let found = false;
    for (let j = i; j < tokens.length; j++) {
      const t = tokens[j];
      if (t.isBreak || /[.!?]/.test(t.trailing)) { i = j + 1; found = true; break; }
    }
    if (!found) i = tokens.length - 1;
  } else {
    i -= 2;
    while (i > 0) {
      const t = tokens[i];
      if (t.isBreak || /[.!?]/.test(t.trailing)) { i = i + 1; break; }
      i--;
    }
    i = Math.max(0, i);
  }
  player.seek(i);
  showControls();
  if (tokens[i]) renderProgress(i, tokens.length);
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
      const s = state.get();
      const target = Math.floor(ratio * s.tokens.length);
      player.seek(target);
      renderProgress(target, s.tokens.length);
      showControls();
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
  } else if (e.key === 'ArrowLeft') {
    e.preventDefault();
    if (e.shiftKey) seekByWord(-1);
    else seekBySentence(-1);
  } else if (e.key === 'ArrowRight') {
    e.preventDefault();
    if (e.shiftKey) seekByWord(1);
    else seekBySentence(1);
  }
}
