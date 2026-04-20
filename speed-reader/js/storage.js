const PREFIX = 'sr:';
const VERSION = 1;

const K = {
  version: PREFIX + 'v',
  settings: PREFIX + 'settings',
  library: PREFIX + 'library',
  sourcePrefix: PREFIX + 'source:',
};

const DEFAULT_SETTINGS = { wpm: 350, lastSourceId: null, onboarded: false };

function read(key, fallback) {
  try {
    const raw = localStorage.getItem(key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

function write(key, value) {
  localStorage.setItem(key, JSON.stringify(value));
}

function trySafe(fn) {
  try { fn(); return { ok: true }; }
  catch (e) {
    const isQuota = e?.name === 'QuotaExceededError' || e?.code === 22 || /quota/i.test(e?.message || '');
    return { ok: false, quota: isQuota, error: e };
  }
}

export function init() {
  const v = read(K.version, null);
  if (v === null) {
    trySafe(() => {
      write(K.version, VERSION);
      write(K.settings, DEFAULT_SETTINGS);
      write(K.library, {});
    });
  }
}

export function getSettings() { return read(K.settings, DEFAULT_SETTINGS); }
export function patchSettings(patch) {
  const next = { ...getSettings(), ...patch };
  return trySafe(() => write(K.settings, next));
}
export function getLibrary() { return read(K.library, {}); }

function writeLibrary(lib) {
  return trySafe(() => write(K.library, lib));
}

function sourceKey(id) { return K.sourcePrefix + id; }

function excerptFrom(text) {
  return text.slice(0, 200).replace(/\s+/g, ' ').trim();
}

export function saveSource({ title, sourceType, text, tokens, sourceUrl }) {
  const id = crypto.randomUUID();
  const now = Date.now();
  const entry = {
    id,
    title: title || 'Untitled',
    sourceType,
    sourceUrl: sourceUrl || null,
    excerpt: excerptFrom(text || ''),
    tokenCount: tokens.length,
    lastIndex: 0,
    addedAt: now,
    updatedAt: now,
  };

  const tokensRes = trySafe(() => write(sourceKey(id), tokens));
  if (!tokensRes.ok) return { ok: false, quota: tokensRes.quota };

  const lib = getLibrary();
  lib[id] = entry;
  const libRes = writeLibrary(lib);
  if (!libRes.ok) {
    localStorage.removeItem(sourceKey(id));
    return { ok: false, quota: libRes.quota };
  }
  patchSettings({ lastSourceId: id });
  return { ok: true, entry };
}

export function getSourceTokens(id) {
  return read(sourceKey(id), null);
}

export function updateEntryProgress(id, lastIndex) {
  const lib = getLibrary();
  const entry = lib[id];
  if (!entry) return { ok: false };
  if (entry.lastIndex === lastIndex) return { ok: true };
  entry.lastIndex = lastIndex;
  entry.updatedAt = Date.now();
  return writeLibrary(lib);
}

export function deleteEntry(id) {
  const lib = getLibrary();
  if (!lib[id]) return { ok: true };
  delete lib[id];
  localStorage.removeItem(sourceKey(id));
  return writeLibrary(lib);
}

export function oldestEntryId() {
  const lib = getLibrary();
  let oldest = null;
  for (const id in lib) {
    if (!oldest || lib[id].updatedAt < lib[oldest].updatedAt) oldest = id;
  }
  return oldest;
}

export function deleteOldestEntry() {
  const id = oldestEntryId();
  if (!id) return false;
  deleteEntry(id);
  return true;
}

export function entriesByRecency() {
  const lib = getLibrary();
  return Object.values(lib).sort((a, b) => b.updatedAt - a.updatedAt);
}
