// ui-finish.js — the "Finish reading" flow controller.
//
// Owns the Finish button in the reader controls, the Library link on home,
// the full-screen Finish modal (recall -> loading -> result) and the
// interstitial AI-disclosure modal.
//
// Persists to the knowledge library via `library.js`. Does NOT touch
// `storage.js` (the reader's own source/progress store).
//
// Exports: mount(), reveal(), reset(), open({ title, text, wpm, sourceId }).
// Event handling uses document-level delegation on [data-action] per the
// project mobile-tap-safe policy — no inline onclick.

import * as library from './library.js';

const STEP = Object.freeze({
  RECALL: 'recall',
  LOADING: 'loading',
  RESULT: 'result',
});

const TIMER_MS = 15000;

const ctx = {
  mounted: false,
  revealed: false,
  open: false,
  step: STEP.RECALL,

  // Payload supplied by open(...)
  payload: null,

  // Cached summarize-API response
  result: null,

  // Abort controller for the in-flight summarize request
  inflight: null,

  // Was the disclosure shown for THIS click (gate for proceeding to step 2)
  pendingSummarize: false,

  // DOM refs (resolved in mount)
  el: {
    finishBtn: null,
    modal: null,
    stepRecall: null,
    stepLoading: null,
    stepResult: null,
    recall: null,
    timer: null,
    timerFill: null,
    resultSummary: null,
    resultTags: null,
    resultQuotes: null,
    resultError: null,
    disclosure: null,
  },
};

// --------------------------------------------------------------------------
// Helpers
// --------------------------------------------------------------------------

/**
 * Reconstruct plain text from the reader's token stream. Tokens carry
 * `word`, `trailing`, and `isBreak`. This is good enough for summarization
 * and for hashing — exact whitespace is not load-bearing.
 */
export function reconstructText(tokens) {
  if (!Array.isArray(tokens) || tokens.length === 0) return '';
  let out = '';
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    if (!t) continue;
    if (t.isBreak) {
      out += '\n\n';
      continue;
    }
    if (out.length > 0 && !out.endsWith('\n') && !out.endsWith(' ')) out += ' ';
    out += (t.word || '') + (t.trailing || '');
  }
  return out.trim();
}

function deriveTitle(payload) {
  const t = (payload?.title || '').trim();
  if (t) return t;
  const text = payload?.text || '';
  const first = text.slice(0, 60).replace(/\s+/g, ' ').trim();
  return first || 'Untitled';
}

function setStep(step) {
  ctx.step = step;
  const { stepRecall, stepLoading, stepResult } = ctx.el;
  if (stepRecall) stepRecall.hidden = step !== STEP.RECALL;
  if (stepLoading) stepLoading.hidden = step !== STEP.LOADING;
  if (stepResult) stepResult.hidden = step !== STEP.RESULT;
}

function startTimer() {
  const { timer, timerFill } = ctx.el;
  if (!timer || !timerFill) return;
  // Snap to 0 with no transition.
  timer.classList.remove('is-running');
  timerFill.style.transition = 'none';
  timerFill.style.width = '0%';
  // Force reflow so the zero-width commit lands before we enable the
  // transition and flip to 100%.
  // eslint-disable-next-line no-unused-expressions
  timerFill.offsetWidth;
  requestAnimationFrame(() => {
    timerFill.style.transition = `width ${TIMER_MS}ms linear`;
    timerFill.style.width = '100%';
    timer.classList.add('is-running');
  });
}

function stopTimer() {
  const { timer, timerFill } = ctx.el;
  if (!timer || !timerFill) return;
  timer.classList.remove('is-running');
  // Freeze visually where it is; next start() will snap to 0.
}

function setError(msg) {
  if (ctx.el.resultError) ctx.el.resultError.textContent = msg || '';
}

function renderTags(tags) {
  const host = ctx.el.resultTags;
  if (!host) return;
  host.replaceChildren();
  (tags || []).forEach(tag => {
    const span = document.createElement('span');
    span.className = 'finish-tag';
    span.textContent = String(tag);
    host.appendChild(span);
  });
}

function renderQuotes(quotes) {
  const host = ctx.el.resultQuotes;
  if (!host) return;
  host.replaceChildren();
  (quotes || []).forEach(q => {
    const li = document.createElement('li');
    li.className = 'finish-quote';
    li.textContent = String(q);
    host.appendChild(li);
  });
}

function cancelInflight() {
  if (ctx.inflight) {
    try { ctx.inflight.abort(); } catch { /* noop */ }
    ctx.inflight = null;
  }
}

// --------------------------------------------------------------------------
// Public API
// --------------------------------------------------------------------------

export function reveal() {
  if (!ctx.mounted) return;
  if (ctx.revealed) return;
  ctx.revealed = true;
  if (ctx.el.finishBtn) ctx.el.finishBtn.classList.add('is-revealed');
}

export function reset() {
  // Called when the reader navigates home / reopens. Hides the Finish
  // button for the next source. Does not tear down the modal structure.
  ctx.revealed = false;
  if (ctx.el.finishBtn) ctx.el.finishBtn.classList.remove('is-revealed');
  closeModal();
}

export function isOpen() {
  return ctx.open;
}

export function open(payload) {
  if (!ctx.mounted) return;
  ctx.payload = {
    title: payload?.title || '',
    text: payload?.text || '',
    wpm: payload?.wpm || null,
    sourceId: payload?.sourceId || null,
    url: payload?.url || null,
    sourceType: payload?.sourceType || 'text',
  };
  ctx.result = null;
  ctx.pendingSummarize = false;
  setError('');
  if (ctx.el.recall) ctx.el.recall.value = '';
  if (ctx.el.modal) ctx.el.modal.hidden = false;
  ctx.open = true;
  setStep(STEP.RECALL);
  // Focus textarea + kick off the soft timer
  requestAnimationFrame(() => {
    if (ctx.el.recall) ctx.el.recall.focus();
    startTimer();
  });
  document.body.classList.add('finish-open');
}

function closeModal() {
  cancelInflight();
  stopTimer();
  hideDisclosure();
  if (ctx.el.modal) ctx.el.modal.hidden = true;
  ctx.open = false;
}

// --------------------------------------------------------------------------
// Disclosure interstitial
// --------------------------------------------------------------------------

function showDisclosure() {
  if (ctx.el.disclosure) ctx.el.disclosure.hidden = false;
}

function hideDisclosure() {
  if (ctx.el.disclosure) ctx.el.disclosure.hidden = true;
}

function needsDisclosure() {
  try {
    return library.settings.get().ai_disclosure_seen !== true;
  } catch {
    return false;
  }
}

// --------------------------------------------------------------------------
// Flow actions
// --------------------------------------------------------------------------

async function doSummarize() {
  stopTimer();
  setStep(STEP.LOADING);
  setError('');

  const { text, title } = ctx.payload || {};
  if (!text || !text.trim()) {
    setStep(STEP.RECALL);
    setError('No text available to summarize.');
    return;
  }

  // Build known_tags from existing concepts so Claude reuses vocab.
  let knownTags = [];
  try {
    knownTags = library.concepts().map(c => c.label).slice(0, 50);
  } catch { /* noop */ }

  cancelInflight();
  ctx.inflight = new AbortController();

  try {
    const res = await fetch('/api/summarize', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: text.slice(0, 30000),
        title: title || '',
        known_tags: knownTags,
      }),
      signal: ctx.inflight.signal,
    });

    if (!res.ok) {
      const msg = res.status === 429
        ? 'Too many summaries — try again in a minute.'
        : `Summarizer unavailable (${res.status}).`;
      throw new Error(msg);
    }

    const data = await res.json();
    ctx.inflight = null;
    ctx.result = {
      summary: String(data.summary || ''),
      tags: Array.isArray(data.tags) ? data.tags : [],
      key_quotes: Array.isArray(data.key_quotes) ? data.key_quotes : [],
    };

    if (ctx.el.resultSummary) ctx.el.resultSummary.textContent = ctx.result.summary;
    renderTags(ctx.result.tags);
    renderQuotes(ctx.result.key_quotes);
    setStep(STEP.RESULT);
  } catch (err) {
    if (err && err.name === 'AbortError') return;
    ctx.inflight = null;
    setError(err?.message || 'Summary failed.');
    setStep(STEP.RECALL);
    startTimer();
  }
}

async function doSave(opts = {}) {
  const { includeAi = true } = opts;
  const p = ctx.payload || {};
  const recall = (ctx.el.recall && ctx.el.recall.value || '').trim();
  const title = deriveTitle(p);

  const input = {
    title,
    url: p.url || null,
    source_type: p.sourceType || 'text',
    wpm: p.wpm || null,
    text: p.text || '',
    user_recall: recall,
    summary: '',
    tags: [],
    key_quotes: [],
  };

  if (includeAi && ctx.result) {
    input.summary = ctx.result.summary || '';
    input.tags = ctx.result.tags || [];
    input.key_quotes = ctx.result.key_quotes || [];
  }

  try {
    const saved = await library.save(input);
    closeModal();
    const id = saved && saved.id;
    window.location.href = `/library${id ? `#saved-${id}` : ''}`;
  } catch (err) {
    setError(err?.message || 'Save failed.');
  }
}

// --------------------------------------------------------------------------
// Event delegation
// --------------------------------------------------------------------------

function onDocumentClick(e) {
  const target = e.target && e.target.closest ? e.target.closest('[data-action]') : null;
  if (!target) return;
  const action = target.dataset.action;
  if (!action) return;

  switch (action) {
    case 'finish-close':
    case 'finish-cancel-loading': {
      if (!ctx.open) return;
      e.preventDefault();
      cancelInflight();
      if (ctx.step === STEP.LOADING) {
        // cancel the request, return to recall
        setStep(STEP.RECALL);
        startTimer();
      } else {
        closeModal();
      }
      return;
    }
    case 'finish-summarize': {
      if (!ctx.open || ctx.step !== STEP.RECALL) return;
      e.preventDefault();
      if (needsDisclosure()) {
        ctx.pendingSummarize = true;
        showDisclosure();
        return;
      }
      doSummarize();
      return;
    }
    case 'finish-skip': {
      if (!ctx.open) return;
      e.preventDefault();
      doSave({ includeAi: false });
      return;
    }
    case 'finish-save': {
      if (!ctx.open || ctx.step !== STEP.RESULT) return;
      e.preventDefault();
      doSave({ includeAi: true });
      return;
    }
    case 'finish-discard': {
      if (!ctx.open) return;
      e.preventDefault();
      closeModal();
      return;
    }
    case 'disclosure-cancel': {
      e.preventDefault();
      ctx.pendingSummarize = false;
      hideDisclosure();
      closeModal();
      return;
    }
    case 'disclosure-continue': {
      e.preventDefault();
      const shouldProceed = ctx.pendingSummarize;
      ctx.pendingSummarize = false;
      hideDisclosure();
      if (shouldProceed) doSummarize();
      return;
    }
    case 'disclosure-never': {
      e.preventDefault();
      try { library.settings.update({ ai_disclosure_seen: true }); } catch { /* noop */ }
      const shouldProceed = ctx.pendingSummarize;
      ctx.pendingSummarize = false;
      hideDisclosure();
      if (shouldProceed) doSummarize();
      return;
    }
    default:
      return;
  }
}

// Swallow the global Escape/Space keyboard shortcuts when the modal is open
// so that Esc closes the Finish flow instead of killing the reader.
function onDocumentKeydown(e) {
  if (!ctx.open) return;
  if (e.key === 'Escape') {
    e.preventDefault();
    e.stopPropagation();
    cancelInflight();
    closeModal();
  }
}

// --------------------------------------------------------------------------
// Mount
// --------------------------------------------------------------------------

export function mount() {
  if (ctx.mounted) return;

  ctx.el.finishBtn = document.querySelector('[data-action="finish-open"]');
  ctx.el.modal = document.querySelector('.finish-modal');
  ctx.el.stepRecall = document.querySelector('[data-finish-step="recall"]');
  ctx.el.stepLoading = document.querySelector('[data-finish-step="loading"]');
  ctx.el.stepResult = document.querySelector('[data-finish-step="result"]');
  ctx.el.recall = document.querySelector('.finish-recall');
  ctx.el.timer = document.querySelector('.finish-timer');
  ctx.el.timerFill = document.querySelector('.finish-timer-fill');
  ctx.el.resultSummary = document.querySelector('.finish-summary');
  ctx.el.resultTags = document.querySelector('.finish-tags');
  ctx.el.resultQuotes = document.querySelector('.finish-quotes');
  ctx.el.resultError = document.querySelector('.finish-error');
  ctx.el.disclosure = document.querySelector('.finish-disclosure');

  // Modal is authored with hidden attr already, but be explicit.
  if (ctx.el.modal) ctx.el.modal.hidden = true;
  if (ctx.el.disclosure) ctx.el.disclosure.hidden = true;
  setStep(STEP.RECALL);

  document.addEventListener('click', onDocumentClick);
  document.addEventListener('keydown', onDocumentKeydown, true);

  ctx.mounted = true;
}
