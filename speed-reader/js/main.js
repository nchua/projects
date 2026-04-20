import * as storage from './storage.js';
import * as state from './state.js';

storage.init();

const settings = storage.getSettings();
state.set({ wpm: settings.wpm });

const slider = document.querySelector('.wpm-slider');
if (slider) slider.value = String(state.get().wpm);
