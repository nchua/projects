const state = {
  tokens: [],
  index: 0,
  wpm: 350,
  playing: false,
  chunkSize: 1,
  sourceId: null,
  controlsVisible: false,
};

const subs = new Set();

export function get() { return state; }

export function set(patch) {
  Object.assign(state, patch);
  subs.forEach(fn => fn(state));
}

export function subscribe(fn) {
  subs.add(fn);
  return () => subs.delete(fn);
}
