const state = {
  tokens: [],
  wpm: 350,
  playing: false,
  sourceId: null,
};

const subs = new Set();

export function get() { return state; }

export function set(patch) {
  let changed = false;
  for (const k in patch) {
    if (state[k] !== patch[k]) {
      state[k] = patch[k];
      changed = true;
    }
  }
  if (changed) subs.forEach(fn => fn(state));
}

export function subscribe(fn) {
  subs.add(fn);
  return () => subs.delete(fn);
}
