const PREFIX = 'sr:';
const VERSION = 1;

const K = {
  version: PREFIX + 'v',
  settings: PREFIX + 'settings',
  library: PREFIX + 'library',
  progress: PREFIX + 'progress',
  sourcePrefix: PREFIX + 'source:',
};

export const SourceType = Object.freeze({
  TEXT: 'text',
  PDF: 'pdf',
  EPUB: 'epub',
  URL: 'url',
});

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
  if (read(K.version, null) === null) {
    trySafe(() => {
      write(K.version, VERSION);
      write(K.settings, DEFAULT_SETTINGS);
      write(K.library, {});
      write(K.progress, {});
    });
  }
}

export function getSettings() { return read(K.settings, DEFAULT_SETTINGS); }
export function patchSettings(patch) {
  return trySafe(() => write(K.settings, { ...getSettings(), ...patch }));
}

function rawLibrary() { return read(K.library, {}); }
function rawProgress() { return read(K.progress, {}); }

export function getLibrary() {
  const lib = rawLibrary();
  const prog = rawProgress();
  for (const id in lib) {
    if (id in prog) lib[id] = { ...lib[id], lastIndex: prog[id] };
  }
  return lib;
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

  const lib = rawLibrary();
  lib[id] = entry;
  const libRes = trySafe(() => write(K.library, lib));
  if (!libRes.ok) {
    localStorage.removeItem(sourceKey(id));
    return { ok: false, quota: libRes.quota };
  }
  patchSettings({ lastSourceId: id });
  return { ok: true, entry };
}

export function getSourceTokens(id) { return read(sourceKey(id), null); }

export function updateEntryProgress(id, lastIndex) {
  if (!id) return { ok: true };
  const prog = rawProgress();
  if (prog[id] === lastIndex) return { ok: true };
  prog[id] = lastIndex;
  return trySafe(() => write(K.progress, prog));
}

export function deleteEntry(id) {
  const lib = rawLibrary();
  const prog = rawProgress();
  delete lib[id];
  delete prog[id];
  localStorage.removeItem(sourceKey(id));
  const r1 = trySafe(() => write(K.library, lib));
  trySafe(() => write(K.progress, prog));
  return r1;
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
  return Object.values(getLibrary()).sort((a, b) => b.updatedAt - a.updatedAt);
}
