import * as state from './state.js';
import { tokenize } from './tokenizer.js';

let onStart = null;

export function mount(opts) {
  onStart = opts.onStart;

  const textarea = document.querySelector('.paste');
  const playBtn = document.querySelector('.home-play');

  if (!textarea) return;

  const updateEnabled = () => {
    const hasText = textarea.value.trim().length > 0;
    if (playBtn) playBtn.disabled = !hasText;
  };

  textarea.addEventListener('input', updateEnabled);
  updateEnabled();

  const go = () => {
    const raw = textarea.value;
    if (!raw.trim()) return;
    const tokens = tokenize(raw);
    if (tokens.length === 0) return;
    state.set({ tokens, index: 0, playing: false });
    if (onStart) onStart();
  };

  if (playBtn) playBtn.addEventListener('click', go);

  textarea.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      go();
    }
  });
}

export function focus() {
  const textarea = document.querySelector('.paste');
  if (textarea) textarea.focus();
}
