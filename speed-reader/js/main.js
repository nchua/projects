import * as storage from './storage.js';
import * as state from './state.js';
import * as player from './player.js';
import * as home from './ui-home.js';
import * as reader from './ui-reader.js';
import * as finish from './ui-finish.js';
import * as rendererMod from './renderer.js';
import { renderToken, renderWpm, renderProgress, clearWord } from './renderer.js';

const PROGRESS_SAVE_EVERY = 50;
const FINISH_REVEAL_RATIO = 0.8;

storage.init();

const settings = storage.getSettings();
state.set({ wpm: settings.wpm });

rendererMod.mount();

const slider = document.querySelector('.wpm-slider');
if (slider) slider.value = String(state.get().wpm);
renderWpm(state.get().wpm);

let lastPersistedIndex = 0;
let finishRevealedForSource = false;

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

function maybeRevealFinish() {
  if (finishRevealedForSource) return;
  const s = state.get();
  if (!s.tokens || s.tokens.length === 0) return;
  const ratio = player.getIndex() / s.tokens.length;
  if (ratio >= FINISH_REVEAL_RATIO) {
    finishRevealedForSource = true;
    finish.reveal();
  }
}

function currentSourceMeta() {
  const s = state.get();
  const entry = s.sourceId ? storage.getLibrary()[s.sourceId] : null;
  return {
    title: entry?.title || '',
    url: entry?.sourceUrl || null,
    sourceType: entry?.sourceType || 'text',
    wpm: s.wpm,
    sourceId: s.sourceId,
  };
}

function openFinishFlow() {
  const s = state.get();
  const meta = currentSourceMeta();
  const text = finish.reconstructText(s.tokens);
  finish.open({
    title: meta.title,
    url: meta.url,
    sourceType: meta.sourceType,
    wpm: meta.wpm,
    sourceId: meta.sourceId,
    text,
  });
}

function toHome() {
  flushProgress();
  document.body.classList.remove('screen-reader');
  document.body.classList.add('screen-home');
  document.querySelector('.reader').setAttribute('aria-hidden', 'true');
  clearWord();
  finish.reset();
  finishRevealedForSource = false;
  home.focus();
}

function toReader(opts = {}) {
  document.body.classList.remove('screen-home');
  document.body.classList.add('screen-reader');
  document.querySelector('.reader').setAttribute('aria-hidden', 'false');
  reader.showControls();

  // New source / session — hide Finish until progress or end.
  finish.reset();
  finishRevealedForSource = false;

  const s = state.get();
  const start = Math.max(0, Math.min(s.tokens.length - 1, opts.startIndex || 0));
  player.resetIndex();
  if (start > 0) player.seek(start);
  lastPersistedIndex = start;

  if (s.tokens.length > 0) renderToken(s.tokens[start] || s.tokens[0]);
  renderProgress(start, s.tokens.length);

  // If resuming near the end, reveal the Finish button immediately.
  maybeRevealFinish();
}

player.configure({
  onAdvance: (token) => {
    renderToken(token);
    renderProgress(player.getIndex(), state.get().tokens.length);
    saveProgress();
    maybeRevealFinish();
  },
  onEnd: () => {
    flushProgress();
    reader.showControls();
    finishRevealedForSource = true;
    finish.reveal();
  },
});

home.mount({ onStart: toReader });
reader.mount({ onClose: toHome });
finish.mount();

// The Finish button lives inside the reader controls. We listen for clicks
// on [data-action="finish-open"] here rather than in ui-finish.js because
// opening the flow requires access to `state` + `storage` to build the
// payload (which the finish module deliberately does not import).
document.addEventListener('click', (e) => {
  const btn = e.target && e.target.closest ? e.target.closest('[data-action="finish-open"]') : null;
  if (!btn) return;
  e.preventDefault();
  e.stopPropagation();
  // Pause playback before showing the modal so dwell continues where it was.
  player.pause();
  openFinishFlow();
});

window.addEventListener('keydown', (e) => {
  // When the Finish modal is open, let it own keyboard handling.
  if (finish.isOpen()) return;
  if (document.body.classList.contains('screen-reader')) {
    reader.handleKey(e);
  }
});

window.addEventListener('beforeunload', flushProgress);

home.focus();
