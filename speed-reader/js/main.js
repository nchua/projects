import * as storage from './storage.js';
import * as state from './state.js';
import * as player from './player.js';
import * as home from './ui-home.js';
import * as reader from './ui-reader.js';
import * as rendererMod from './renderer.js';
import { renderToken, renderWpm, renderProgress, clearWord } from './renderer.js';

const PROGRESS_SAVE_EVERY = 50;

storage.init();

const settings = storage.getSettings();
state.set({ wpm: settings.wpm });

rendererMod.mount();

const slider = document.querySelector('.wpm-slider');
if (slider) slider.value = String(state.get().wpm);
renderWpm(state.get().wpm);

let lastPersistedIndex = 0;

function saveProgress() {
  const idx = player.getIndex();
  if (Math.abs(idx - lastPersistedIndex) < PROGRESS_SAVE_EVERY) return;
  flushProgress();
}

function flushProgress() {
  const s = state.get();
  if (!s.sourceId) return;
  lastPersistedIndex = player.getIndex();
  storage.updateEntryProgress(s.sourceId, lastPersistedIndex);
}

function toHome() {
  flushProgress();
  document.body.classList.remove('screen-reader');
  document.body.classList.add('screen-home');
  document.querySelector('.reader').setAttribute('aria-hidden', 'true');
  clearWord();
  home.focus();
}

function toReader(opts = {}) {
  document.body.classList.remove('screen-home');
  document.body.classList.add('screen-reader');
  document.querySelector('.reader').setAttribute('aria-hidden', 'false');
  reader.showControls();

  const s = state.get();
  const start = Math.max(0, Math.min(s.tokens.length - 1, opts.startIndex || 0));
  player.resetIndex();
  if (start > 0) player.seek(start);
  lastPersistedIndex = start;

  if (s.tokens.length > 0) renderToken(s.tokens[start] || s.tokens[0]);
  renderProgress(start, s.tokens.length);
}

player.configure({
  onAdvance: (token) => {
    renderToken(token);
    renderProgress(player.getIndex(), state.get().tokens.length);
    saveProgress();
  },
  onEnd: () => {
    flushProgress();
    reader.showControls();
  },
});

home.mount({ onStart: toReader });
reader.mount({ onClose: toHome });

window.addEventListener('keydown', (e) => {
  if (document.body.classList.contains('screen-reader')) {
    reader.handleKey(e);
  }
});

window.addEventListener('beforeunload', flushProgress);

home.focus();
