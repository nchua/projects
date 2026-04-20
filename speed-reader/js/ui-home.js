import * as state from './state.js';
import { tokenize } from './tokenizer.js';
import * as textSrc from './sources/text.js';
import * as pdfSrc from './sources/pdf.js';
import * as epubSrc from './sources/epub.js';
import * as urlSrc from './sources/url.js';
import * as storage from './storage.js';

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
  if (name.endsWith('.pdf')) return { mod: pdfSrc, sourceType: 'pdf' };
  if (name.endsWith('.epub')) return { mod: epubSrc, sourceType: 'epub' };
  return { mod: textSrc, sourceType: 'text' };
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

function showQuotaToast(onAfterClear) {
  setStatus('Storage full. Removed oldest saved item.', true);
  const removed = storage.deleteOldestEntry();
  renderLibrary();
  if (removed && onAfterClear) onAfterClear();
}

async function runPipeline({ loadingMsg, loader, titleFallback, sourceType, sourceUrl }) {
  setStatus(loadingMsg);
  try {
    const { title, text } = await loader();
    if (!text || !text.trim()) throw new Error('No readable text found');
    const tokens = tokenize(text);
    if (tokens.length === 0) throw new Error('No readable text found');

    const save = storage.saveSource({
      title: title || titleFallback || firstLine(text),
      sourceType,
      sourceUrl,
      text,
      tokens,
    });
    if (!save.ok && save.quota) {
      if (storage.deleteOldestEntry()) {
        const retry = storage.saveSource({ title: title || titleFallback || firstLine(text), sourceType, sourceUrl, text, tokens });
        if (!retry.ok) { setStatus('Could not save — storage is full.', true); return; }
        state.set({ tokens, sourceId: retry.entry.id });
      } else {
        setStatus('Could not save — storage is full.', true); return;
      }
    } else if (save.ok) {
      state.set({ tokens, sourceId: save.entry.id });
    } else {
      state.set({ tokens, sourceId: null });
    }

    textarea.value = '';
    updateEnabled();
    setStatus('');
    renderLibrary();
    if (onStart) onStart();
  } catch (err) {
    console.error(err);
    setStatus(err.message || 'Something went wrong', true);
  }
}

function go() {
  if (!hasContent()) return;
  const raw = textarea.value;
  if (isUrl(raw)) {
    const trimmed = raw.trim();
    runPipeline({
      loadingMsg: 'Fetching article…',
      loader: () => urlSrc.extract(trimmed),
      sourceType: 'url',
      sourceUrl: trimmed,
    });
  } else {
    runPipeline({
      loadingMsg: '',
      loader: () => Promise.resolve({ title: '', text: raw }),
      sourceType: 'text',
    });
  }
}

function resumeEntry(id) {
  const tokens = storage.getSourceTokens(id);
  const lib = storage.getLibrary();
  const entry = lib[id];
  if (!tokens || !entry) {
    setStatus('Saved item is no longer available.', true);
    storage.deleteEntry(id);
    renderLibrary();
    return;
  }
  state.set({ tokens, sourceId: id });
  closeLibrary();
  if (onStart) onStart({ startIndex: entry.lastIndex || 0 });
}

function formatAgo(ts) {
  const diff = Math.max(0, Date.now() - ts);
  const mins = Math.round(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.round(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.round(hrs / 24);
  return `${days}d ago`;
}

function renderLibrary() {
  if (!libraryListEl) return;
  const entries = storage.entriesByRecency();
  libraryDot.hidden = entries.length === 0;
  libraryListEl.innerHTML = '';
  if (entries.length === 0) {
    const empty = document.createElement('div');
    empty.className = 'library-empty';
    empty.textContent = 'Nothing saved yet.';
    libraryListEl.appendChild(empty);
    return;
  }
  for (const e of entries) {
    const pct = e.tokenCount > 0 ? Math.round((e.lastIndex / e.tokenCount) * 100) : 0;
    const row = document.createElement('div');
    row.className = 'library-row';
    row.innerHTML = `
      <button class="library-resume" type="button">
        <div class="library-title">${escapeHtml(e.title)}</div>
        <div class="library-meta">${pct}% · ${formatAgo(e.updatedAt)}</div>
      </button>
      <button class="library-delete" type="button" aria-label="Delete">×</button>
    `;
    row.querySelector('.library-resume').addEventListener('click', () => resumeEntry(e.id));
    row.querySelector('.library-delete').addEventListener('click', () => {
      storage.deleteEntry(e.id);
      renderLibrary();
    });
    libraryListEl.appendChild(row);
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
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
      if (file) {
        const { mod, sourceType } = sourceInfoFor(file);
        runPipeline({
          loadingMsg: 'Reading file…',
          loader: () => mod.extract(file),
          titleFallback: file.name,
          sourceType,
        });
      }
      fileInput.value = '';
    });
  }

  if (urlBtn) {
    urlBtn.disabled = false;
    urlBtn.addEventListener('click', () => {
      const url = prompt('Article URL:');
      if (url) {
        const trimmed = url.trim();
        runPipeline({
          loadingMsg: 'Fetching article…',
          loader: () => urlSrc.extract(trimmed),
          sourceType: 'url',
          sourceUrl: trimmed,
        });
      }
    });
  }

  if (libraryDot) libraryDot.addEventListener('click', toggleLibrary);
  if (libraryClose) libraryClose.addEventListener('click', closeLibrary);

  renderLibrary();
}

export function focus() {
  if (textarea) textarea.focus();
}
