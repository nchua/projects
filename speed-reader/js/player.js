import * as state from './state.js';
import { dwellMs } from './timing.js';

let timer = null;
let index = 0;
let onAdvance = null;
let onEnd = null;

function cancel() {
  if (timer !== null) {
    clearTimeout(timer);
    timer = null;
  }
}

function tick() {
  timer = null;
  const s = state.get();
  if (!s.playing) return;
  if (index >= s.tokens.length) {
    state.set({ playing: false });
    if (onEnd) onEnd();
    return;
  }
  const token = s.tokens[index];
  if (onAdvance) onAdvance(token);
  const ms = dwellMs(token, s.wpm);
  index++;
  if (state.get().playing) {
    timer = setTimeout(tick, ms);
  }
}

export function start() {
  cancel();
  if (index >= state.get().tokens.length) index = 0;
  state.set({ playing: true });
  tick();
}

export function pause() {
  cancel();
  state.set({ playing: false });
}

export function toggle() {
  const s = state.get();
  if (s.playing) {
    pause();
    return false;
  }
  start();
  return true;
}

export function resetIndex() {
  cancel();
  index = 0;
}

export function seek(newIndex) {
  cancel();
  const s = state.get();
  index = Math.max(0, Math.min(s.tokens.length - 1, newIndex));
  if (s.playing) {
    timer = setTimeout(tick, 0);
  }
}

export function getIndex() { return index; }

export function configure(opts) {
  if (opts.onAdvance) onAdvance = opts.onAdvance;
  if (opts.onEnd) onEnd = opts.onEnd;
}
