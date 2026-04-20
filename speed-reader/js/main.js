import * as storage from './storage.js';
import * as state from './state.js';
import * as player from './player.js';
import * as home from './ui-home.js';
import * as reader from './ui-reader.js';
import { renderToken, renderWpm, clearWord } from './renderer.js';

storage.init();

const settings = storage.getSettings();
state.set({ wpm: settings.wpm });

const slider = document.querySelector('.wpm-slider');
if (slider) slider.value = String(state.get().wpm);
renderWpm(state.get().wpm);

function toHome() {
  document.body.classList.remove('screen-reader');
  document.body.classList.add('screen-home');
  document.querySelector('.reader').setAttribute('aria-hidden', 'true');
  clearWord();
  home.focus();
}

function toReader() {
  document.body.classList.remove('screen-home');
  document.body.classList.add('screen-reader');
  document.querySelector('.reader').setAttribute('aria-hidden', 'false');
  reader.showControls();
  const s = state.get();
  if (s.tokens.length > 0) renderToken(s.tokens[0]);
}

player.configure({
  onAdvance: (token) => renderToken(token),
  onEnd: () => reader.showControls(),
});

home.mount({ onStart: toReader });
reader.mount({ onClose: toHome });

window.addEventListener('keydown', (e) => {
  if (document.body.classList.contains('screen-reader')) {
    reader.handleKey(e);
  }
});

state.subscribe((s) => {
  const savedWpm = storage.getSettings().wpm;
  if (s.wpm !== savedWpm) {
    storage.setSettings({ ...storage.getSettings(), wpm: s.wpm });
  }
});

home.focus();
