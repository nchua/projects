import * as state from './state.js';
import * as player from './player.js';
import { renderWpm } from './renderer.js';

const AUTO_HIDE_MS = 2000;

let hideTimer = null;
let onClose = null;

function showControls() {
  document.body.classList.add('controls-visible');
  const controls = document.querySelector('.controls');
  if (controls) controls.hidden = false;
  resetHideTimer();
}

function hideControls() {
  document.body.classList.remove('controls-visible');
  clearHideTimer();
}

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

export function mount(opts) {
  onClose = opts.onClose;

  const tap = document.querySelector('.tap-surface');
  const playPause = document.querySelector('.play-pause');
  const closeBtn = document.querySelector('.close');
  const slider = document.querySelector('.wpm-slider');

  if (tap) {
    tap.addEventListener('click', () => {
      if (state.get().playing) {
        player.pause();
        showControls();
      } else {
        hideControls();
        player.start();
      }
    });
  }

  if (playPause) {
    playPause.addEventListener('click', (e) => {
      e.stopPropagation();
      if (state.get().playing) {
        player.pause();
        resetHideTimer();
      } else {
        player.start();
        resetHideTimer();
      }
    });
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      player.pause();
      hideControls();
      if (onClose) onClose();
    });
  }

  if (slider) {
    slider.addEventListener('input', () => {
      const wpm = parseInt(slider.value, 10);
      state.set({ wpm });
      renderWpm(wpm);
      resetHideTimer();
    });
  }

  state.subscribe((s) => {
    if (playPause) playPause.classList.toggle('is-playing', s.playing);
  });
}

export function handleKey(e) {
  const s = state.get();
  if (e.key === ' ') {
    e.preventDefault();
    if (s.playing) {
      player.pause();
      showControls();
    } else {
      hideControls();
      player.start();
    }
  } else if (e.key === 'Escape') {
    e.preventDefault();
    player.pause();
    hideControls();
    if (onClose) onClose();
  }
}

export { showControls, hideControls };
