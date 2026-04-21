// library.js — localStorage layer for the knowledge library.
// Deliberately independent from the reader's own storage.js (which tracks
// loaded-source state and reading progress). This module stores the
// post-read knowledge artifacts: summary, tags, key_quotes, concept graph.

const KEY = 'speedreader.library.v1';

const DEFAULT_STATE = Object.freeze({
  sources: [],
  concepts: [],
  settings: { ai_disclosure_seen: false },
});

function readRaw() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return structuredClone(DEFAULT_STATE);
    const parsed = JSON.parse(raw);
    return {
      sources: Array.isArray(parsed.sources) ? parsed.sources : [],
      concepts: Array.isArray(parsed.concepts) ? parsed.concepts : [],
      settings: { ...DEFAULT_STATE.settings, ...(parsed.settings || {}) },
    };
  } catch {
    return structuredClone(DEFAULT_STATE);
  }
}

function writeRaw(state) {
  try {
    localStorage.setItem(KEY, JSON.stringify(state));
    return true;
  } catch (err) {
    console.warn('library: localStorage write failed', err);
    return false;
  }
}

function uuid() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return 'id-' + Date.now().toString(36) + '-' + Math.random().toString(36).slice(2, 10);
}

function normalizeText(text) {
  return String(text || '').replace(/\s+/g, ' ').trim();
}

export async function textHash(text) {
  const norm = normalizeText(text);
  if (!norm) return '';
  try {
    const enc = new TextEncoder().encode(norm);
    const buf = await crypto.subtle.digest('SHA-256', enc);
    return Array.from(new Uint8Array(buf))
      .map(b => b.toString(16).padStart(2, '0'))
      .join('');
  } catch {
    let h = 0;
    for (let i = 0; i < norm.length; i++) {
      h = (h * 31 + norm.charCodeAt(i)) | 0;
    }
    return 'fb-' + (h >>> 0).toString(16);
  }
}

export function all() {
  const state = readRaw();
  return state.sources.slice().sort((a, b) => (b.finished_at || '').localeCompare(a.finished_at || ''));
}

export function get(id) {
  return readRaw().sources.find(s => s.id === id) || null;
}

export function findByHash(hash) {
  if (!hash) return null;
  return readRaw().sources.find(s => s.text_hash === hash) || null;
}

export function concepts() {
  return readRaw().concepts.slice();
}

export function conceptCounts() {
  const state = readRaw();
  const counts = new Map();
  state.concepts.forEach(c => counts.set(c.id, { ...c, count: c.source_ids.length }));
  return Array.from(counts.values()).sort((a, b) => b.count - a.count);
}

export function size() {
  return readRaw().sources.length;
}

function matchConcept(label, existing) {
  const key = label.trim().toLowerCase();
  return existing.find(c => c.label.trim().toLowerCase() === key) || null;
}

function mintConceptsFor(record, state) {
  const attached = new Set();
  (record.tags || []).forEach(tagRaw => {
    const label = String(tagRaw || '').trim();
    if (!label) return;
    let concept = matchConcept(label, state.concepts);
    if (!concept) {
      concept = { id: uuid(), label, source_ids: [] };
      state.concepts.push(concept);
    }
    if (!concept.source_ids.includes(record.id)) {
      concept.source_ids.push(record.id);
    }
    attached.add(concept.id);
  });
  return Array.from(attached);
}

function detachConceptsFor(sourceId, state) {
  state.concepts = state.concepts
    .map(c => ({ ...c, source_ids: c.source_ids.filter(id => id !== sourceId) }))
    .filter(c => c.source_ids.length > 0);
}

export async function save(input) {
  const text = input.text || '';
  const hash = input.text_hash || await textHash(text);
  const now = new Date().toISOString();
  const state = readRaw();

  const existing = hash ? state.sources.find(s => s.text_hash === hash) : null;
  if (existing) {
    existing.last_read_at = now;
    if (input.wpm) existing.wpm = input.wpm;
    if (input.user_recall && !existing.user_recall) existing.user_recall = input.user_recall;
    writeRaw(state);
    return { id: existing.id, created: false };
  }

  const record = {
    id: uuid(),
    title: input.title || 'Untitled',
    url: input.url || null,
    source_type: input.source_type || 'text',
    ingested_at: input.ingested_at || now,
    finished_at: now,
    last_read_at: now,
    wpm: input.wpm || null,
    char_count: text.length,
    text_hash: hash,
    user_recall: input.user_recall || null,
    summary: input.summary || '',
    tags: Array.isArray(input.tags) ? input.tags.slice() : [],
    key_quotes: Array.isArray(input.key_quotes) ? input.key_quotes.slice() : [],
    starred_quotes: [],
  };

  state.sources.push(record);
  mintConceptsFor(record, state);
  writeRaw(state);

  return { id: record.id, created: true };
}

export function remove(id) {
  const state = readRaw();
  const before = state.sources.length;
  state.sources = state.sources.filter(s => s.id !== id);
  if (state.sources.length === before) return false;
  detachConceptsFor(id, state);
  writeRaw(state);
  return true;
}

export function starQuote(sourceId, quote) {
  const state = readRaw();
  const src = state.sources.find(s => s.id === sourceId);
  if (!src) return false;
  if (!src.starred_quotes.includes(quote)) {
    src.starred_quotes.push(quote);
    writeRaw(state);
  }
  return true;
}

export function unstarQuote(sourceId, quote) {
  const state = readRaw();
  const src = state.sources.find(s => s.id === sourceId);
  if (!src) return false;
  const idx = src.starred_quotes.indexOf(quote);
  if (idx >= 0) {
    src.starred_quotes.splice(idx, 1);
    writeRaw(state);
  }
  return true;
}

export const settings = {
  get() { return readRaw().settings; },
  update(patch) {
    const state = readRaw();
    state.settings = { ...state.settings, ...patch };
    writeRaw(state);
    return state.settings;
  },
};

export function exportAll() {
  return readRaw();
}

export function importAll(data) {
  if (!data || typeof data !== 'object') return false;
  return writeRaw({
    sources: Array.isArray(data.sources) ? data.sources : [],
    concepts: Array.isArray(data.concepts) ? data.concepts : [],
    settings: { ...DEFAULT_STATE.settings, ...(data.settings || {}) },
  });
}

export function clearAll() {
  localStorage.removeItem(KEY);
}
