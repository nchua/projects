import * as state from './state.js';
import { tokenize } from './tokenizer.js';
import * as textSrc from './sources/text.js';
import * as pdfSrc from './sources/pdf.js';
import * as epubSrc from './sources/epub.js';
import * as urlSrc from './sources/url.js';
import * as storage from './storage.js';
import { SourceType } from './storage.js';

const ONBOARDING_TEXT = 'Speed reading replaces the small hops your eyes make across a page with a fixed point. Words arrive where your focus already is. The red letter marks the optimal recognition point — rest your attention there and the rest of the word resolves on its own. Start at a pace that feels comfortable, then push past it.';

let onStart = null;
let textarea = null;
let playBtn = null;
let fileInput = null;
let statusEl = null;
let libraryEl = null;
let libraryListEl = null;
let libraryDot = null;

function isUrl(s) {
  const t = s.trim();
  if (t.includes('\n') || t.includes(' ')) return false;
  try {
    const u = new URL(t);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch { return false; }
}

function sourceInfoFor(file) {
  const name = (file.name || '').toLowerCase();
  if (name.endsWith('.pdf')) return { mod: pdfSrc, sourceType: SourceType.PDF };
  if (name.endsWith('.epub')) return { mod: epubSrc, sourceType: SourceType.EPUB };
  return { mod: textSrc, sourceType: SourceType.TEXT };
}

function setStatus(msg, isError = false) {
  if (!statusEl) return;
  statusEl.textContent = msg || '';
  statusEl.classList.toggle('is-error', !!msg && isError);
}

function hasContent() {
  return textarea && textarea.value.trim().length > 0;
}

function updateEnabled() {
  if (playBtn) playBtn.disabled = !hasContent();
}

function firstLine(text) {
  const line = text.split('\n').find(l => l.trim().length > 0) || '';
  return line.trim().slice(0, 80);
}

function trySaveWithEviction(payload) {
  let res = storage.saveSource(payload);
  if (!res.ok && res.quota && storage.deleteOldestEntry()) {
    res = storage.saveSource(payload);
  }
  return res;
}

async function runPipeline(loadingMsg, loader) {
  setStatus(loadingMsg);
  try {
    const result = await loader();
    const text = result?.text || '';
    if (!text.trim()) throw new Error('No readable text found');
    const tokens = tokenize(text);
    if (tokens.length === 0) throw new Error('No readable text found');

    const payload = {
      title: result.title || firstLine(text),
      sourceType: result.sourceType || SourceType.TEXT,
      sourceUrl: result.sourceUrl || null,
      text,
      tokens,
    };
    const save = trySaveWithEviction(payload);
    if (!save.ok) {
      setStatus(save.quota ? 'Storage is full. Delete a saved item and try again.' : 'Could not save.', true);
      state.set({ tokens, sourceId: null });
    } else {
      state.set({ tokens, sourceId: save.entry.id });
    }

    textarea.value = '';
    updateEnabled();
    if (save.ok) setStatus('');
    renderLibrary();
    if (onStart) onStart();
  } catch (err) {
    console.error(err);
    setStatus(err.message || 'Something went wrong', true);
  }
}

function textLoader(raw) {
  return () => Promise.resolve({ text: raw, sourceType: SourceType.TEXT });
}

function urlLoader(url) {
  return async () => {
    const { title, text } = await urlSrc.extract(url);
    return { title, text, sourceType: SourceType.URL, sourceUrl: url };
  };
}

function fileLoader(file) {
  const { mod, sourceType } = sourceInfoFor(file);
  return async () => {
    const { title, text } = await mod.extract(file);
    return { title: title || file.name, text, sourceType };
  };
}

function go() {
  if (!hasContent()) return;
  const raw = textarea.value;
  if (isUrl(raw)) {
    runPipeline('Fetching article…', urlLoader(raw.trim()));
  } else {
    runPipeline('', textLoader(raw));
  }
}

function resumeEntry(id) {
  const tokens = storage.getSourceTokens(id);
  const entry = storage.getLibrary()[id];
  if (!entry) return;
  if (!tokens) {
    setStatus('Saved item was evicted from storage — removed.', true);
    storage.deleteEntry(id);
    renderLibrary();
    return;
  }
  state.set({ tokens, sourceId: id });
  closeLibrary();
  if (onStart) onStart({ startIndex: entry.lastIndex });
}

function formatAgo(ts) {
  const diff = Math.max(0, Date.now() - ts);
  const mins = Math.round(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.round(hrs / 24)}d ago`;
}

function buildRow(entry) {
  const row = document.createElement('div');
  row.className = 'library-row';
  row.dataset.id = entry.id;

  const resume = document.createElement('button');
  resume.type = 'button';
  resume.className = 'library-resume';
  resume.dataset.action = 'resume';

  const titleEl = document.createElement('div');
  titleEl.className = 'library-title';
  titleEl.textContent = entry.title;
  resume.appendChild(titleEl);

  const metaEl = document.createElement('div');
  metaEl.className = 'library-meta';
  const pct = entry.tokenCount > 0 ? Math.round((entry.lastIndex / entry.tokenCount) * 100) : 0;
  metaEl.textContent = `${pct}% · ${formatAgo(entry.updatedAt)}`;
  resume.appendChild(metaEl);

  const del = document.createElement('button');
  del.type = 'button';
  del.className = 'library-delete';
  del.dataset.action = 'delete';
  del.setAttribute('aria-label', 'Delete');
  del.textContent = '×';

  row.appendChild(resume);
  row.appendChild(del);
  return row;
}

function renderLibrary() {
  if (!libraryListEl || !libraryDot) return;
  const entries = storage.entriesByRecency();
  libraryDot.hidden = entries.length === 0;
  libraryListEl.replaceChildren();
  if (entries.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'library-empty';
    empty.textContent = 'Nothing saved yet.';
    libraryListEl.appendChild(empty);
    return;
  }
  for (const e of entries) libraryListEl.appendChild(buildRow(e));
}

function handleLibraryClick(e) {
  const resumeBtn = e.target.closest('[data-action="resume"]');
  const deleteBtn = e.target.closest('[data-action="delete"]');
  const row = e.target.closest('.library-row');
  if (!row) return;
  const id = row.dataset.id;
  if (deleteBtn) {
    storage.deleteEntry(id);
    renderLibrary();
  } else if (resumeBtn) {
    resumeEntry(id);
  }
}

function openLibrary() { if (libraryEl) libraryEl.classList.add('is-open'); }
function closeLibrary() { if (libraryEl) libraryEl.classList.remove('is-open'); }
function toggleLibrary() {
  if (!libraryEl) return;
  libraryEl.classList.contains('is-open') ? closeLibrary() : openLibrary();
}

function maybeOnboard() {
  const settings = storage.getSettings();
  if (settings.onboarded) return;
  if (textarea && textarea.value.length === 0) textarea.value = ONBOARDING_TEXT;
  updateEnabled();
  storage.patchSettings({ onboarded: true });
}

export function mount(opts) {
  onStart = opts.onStart;

  textarea = document.querySelector('.paste');
  playBtn = document.querySelector('.home-play');
  fileInput = document.querySelector('.file-input');
  statusEl = document.querySelector('.status');
  libraryEl = document.querySelector('.library-panel');
  libraryListEl = document.querySelector('.library-list');
  libraryDot = document.querySelector('.library-dot');
  const uploadBtn = document.querySelector('[data-action="upload"]');
  const urlBtn = document.querySelector('[data-action="url"]');
  const libraryClose = document.querySelector('.library-close');

  if (!textarea) return;

  textarea.addEventListener('input', () => { updateEnabled(); if (statusEl?.textContent) setStatus(''); });
  updateEnabled();
  maybeOnboard();

  if (playBtn) playBtn.addEventListener('click', go);

  textarea.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      go();
    }
  });

  if (uploadBtn && fileInput) {
    uploadBtn.disabled = false;
    uploadBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', () => {
      const file = fileInput.files?.[0];
      if (file) runPipeline('Reading file…', fileLoader(file));
      fileInput.value = '';
    });
  }

  if (urlBtn) {
    urlBtn.disabled = false;
    urlBtn.addEventListener('click', () => {
      const url = prompt('Article URL:');
      if (url) runPipeline('Fetching article…', urlLoader(url.trim()));
    });
  }

  if (libraryDot) libraryDot.addEventListener('click', toggleLibrary);
  if (libraryClose) libraryClose.addEventListener('click', closeLibrary);
  if (libraryListEl) libraryListEl.addEventListener('click', handleLibraryClick);

  renderLibrary();
}

export function focus() {
  if (textarea) textarea.focus();
}
