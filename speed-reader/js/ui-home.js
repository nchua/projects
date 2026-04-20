import * as state from './state.js';
import { tokenize } from './tokenizer.js';
import * as textSrc from './sources/text.js';
import * as pdfSrc from './sources/pdf.js';
import * as epubSrc from './sources/epub.js';
import * as urlSrc from './sources/url.js';

let onStart = null;
let textarea = null;
let playBtn = null;
let fileInput = null;
let statusEl = null;

function isUrl(s) {
  const t = s.trim();
  if (t.includes('\n') || t.includes(' ')) return false;
  try {
    const u = new URL(t);
    return u.protocol === 'http:' || u.protocol === 'https:';
  } catch {
    return false;
  }
}

function sourceFor(file) {
  const name = (file.name || '').toLowerCase();
  if (name.endsWith('.pdf')) return pdfSrc;
  if (name.endsWith('.epub')) return epubSrc;
  return textSrc;
}

function setStatus(msg) {
  if (statusEl) statusEl.textContent = msg || '';
}

function hasContent() {
  return textarea && textarea.value.trim().length > 0;
}

function updateEnabled() {
  if (playBtn) playBtn.disabled = !hasContent();
}

async function runPipeline(loadingMsg, extractor) {
  setStatus(loadingMsg);
  try {
    const { text } = await extractor();
    if (!text || !text.trim()) throw new Error('No readable text found');
    const tokens = tokenize(text);
    if (tokens.length === 0) throw new Error('No readable text found');
    textarea.value = '';
    updateEnabled();
    setStatus('');
    state.set({ tokens });
    if (onStart) onStart();
  } catch (err) {
    console.error(err);
    setStatus(err.message || 'Something went wrong');
  }
}

function go() {
  if (!hasContent()) return;
  const raw = textarea.value;
  if (isUrl(raw)) {
    runPipeline('Fetching article…', () => urlSrc.extract(raw.trim()));
  } else {
    runPipeline('', () => Promise.resolve({ text: raw }));
  }
}

export function mount(opts) {
  onStart = opts.onStart;

  textarea = document.querySelector('.paste');
  playBtn = document.querySelector('.home-play');
  fileInput = document.querySelector('.file-input');
  statusEl = document.querySelector('.status');
  const uploadBtn = document.querySelector('[data-action="upload"]');
  const urlBtn = document.querySelector('[data-action="url"]');

  if (!textarea) return;

  textarea.addEventListener('input', () => { updateEnabled(); if (statusEl?.textContent) setStatus(''); });
  updateEnabled();

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
      if (file) runPipeline('Reading file…', () => sourceFor(file).extract(file));
      fileInput.value = '';
    });
  }

  if (urlBtn) {
    urlBtn.disabled = false;
    urlBtn.addEventListener('click', () => {
      const url = prompt('Article URL:');
      if (url) runPipeline('Fetching article…', () => urlSrc.extract(url.trim()));
    });
  }
}

export function focus() {
  if (textarea) textarea.focus();
}
