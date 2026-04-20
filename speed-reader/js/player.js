import * as state from './state.js';
import { dwellMs } from './timing.js';

let timer = null;
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
  if (s.index >= s.tokens.length) {
    state.set({ playing: false });
    if (onEnd) onEnd();
    return;
  }
  const token = s.tokens[s.index];
  if (onAdvance) onAdvance(token, s.index);
  const ms = dwellMs(token, s.wpm);
  const nextIndex = s.index + 1;
  state.set({ index: nextIndex });
  if (state.get().playing) {
    timer = setTimeout(tick, ms);
  }
}

export function start() {
  cancel();
  state.set({ playing: true });
  tick();
}

export function pause() {
  cancel();
  state.set({ playing: false });
}

export function seek(index) {
  cancel();
  const s = state.get();
  const clamped = Math.max(0, Math.min(s.tokens.length - 1, index));
  state.set({ index: clamped });
  if (s.playing) {
    timer = setTimeout(tick, 0);
  }
}

export function configure(opts) {
  if (opts.onAdvance) onAdvance = opts.onAdvance;
  if (opts.onEnd) onEnd = opts.onEnd;
}
