import * as state from './state.js';
import { tokenize } from './tokenizer.js';
import * as textSrc from './sources/text.js';
import * as pdfSrc from './sources/pdf.js';
import * as epubSrc from './sources/epub.js';
import * as urlSrc from './sources/url.js';

const URL_RE = /^\s*https?:\/\/\S+\s*$/i;

let onStart = null;
let textarea = null;
let playBtn = null;
let fileInput = null;

function setStatus(msg) {
  if (textarea) textarea.placeholder = msg;
}

function hasContent() {
  return textarea && textarea.value.trim().length > 0;
}

function updateEnabled() {
  if (playBtn) playBtn.disabled = !hasContent();
}

async function startFromText(raw) {
  const tokens = tokenize(raw);
  if (tokens.length === 0) return;
  state.set({ tokens });
  if (onStart) onStart();
}

async function startFromFile(file) {
  const name = (file.name || '').toLowerCase();
  setStatus('Reading file…');
  try {
    let text;
    if (name.endsWith('.pdf')) text = await pdfSrc.extractText(file);
    else if (name.endsWith('.epub')) text = await epubSrc.extractText(file);
    else text = await textSrc.extractText(file);
    textarea.value = '';
    setStatus('Paste text…');
    await startFromText(text);
  } catch (err) {
    console.error(err);
    setStatus(`Could not read file: ${err.message}`);
  }
}

async function startFromUrl(url) {
  setStatus('Fetching article…');
  try {
    const { text } = await urlSrc.extractText(url);
    textarea.value = '';
    setStatus('Paste text…');
    await startFromText(text);
  } catch (err) {
    console.error(err);
    setStatus(`Could not fetch: ${err.message}`);
  }
}

async function go() {
  if (!hasContent()) return;
  const raw = textarea.value;
  if (URL_RE.test(raw)) {
    await startFromUrl(raw.trim());
  } else {
    await startFromText(raw);
  }
}

export function mount(opts) {
  onStart = opts.onStart;

  textarea = document.querySelector('.paste');
  playBtn = document.querySelector('.home-play');
  fileInput = document.querySelector('.file-input');
  const uploadBtn = document.querySelector('[data-action="upload"]');
  const urlBtn = document.querySelector('[data-action="url"]');

  if (!textarea) return;

  textarea.addEventListener('input', updateEnabled);
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
      if (file) startFromFile(file);
      fileInput.value = '';
    });
  }

  if (urlBtn) {
    urlBtn.disabled = false;
    urlBtn.addEventListener('click', () => {
      const url = prompt('Article URL:');
      if (url) startFromUrl(url.trim());
    });
  }
}

export function focus() {
  if (textarea) textarea.focus();
}
