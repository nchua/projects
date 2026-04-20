import * as state from './state.js';
import * as player from './player.js';
import { renderWpm } from './renderer.js';
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

export function mount(opts) {
  onClose = opts.onClose;

  const tap = document.querySelector('.tap-surface');
  playPauseEl = document.querySelector('.play-pause');
  const closeBtn = document.querySelector('.close');
  const slider = document.querySelector('.wpm-slider');

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

  state.subscribe((s) => {
    if (playPauseEl) playPauseEl.classList.toggle('is-playing', s.playing);
  });
}

export function handleKey(e) {
  if (e.target && e.target.tagName === 'BUTTON') return;
  if (e.key === ' ') {
    e.preventDefault();
    togglePlay();
  } else if (e.key === 'Escape') {
    e.preventDefault();
    close();
  }
}
