const PREFIX = 'sr:';
const VERSION = 1;

const K = {
  version: PREFIX + 'v',
  settings: PREFIX + 'settings',
  library: PREFIX + 'library',
};

const DEFAULT_SETTINGS = { wpm: 350, lastSourceId: null };

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function write(key, value) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function init() {
  const v = read(K.version, null);
  if (v === null) {
    write(K.version, VERSION);
    write(K.settings, DEFAULT_SETTINGS);
    write(K.library, {});
  }
}

export function getSettings() { return read(K.settings, DEFAULT_SETTINGS); }
export function setSettings(s) { return write(K.settings, s); }
export function patchSettings(patch) {
  return write(K.settings, { ...getSettings(), ...patch });
}
export function getLibrary() { return read(K.library, {}); }
export function setLibrary(l) { return write(K.library, l); }
