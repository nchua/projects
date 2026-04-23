// library-page.js — controller for /library.html.
// Renders List + Atlas tabs, handles card clicks, detail panel,
// export-to-PNG, and atlas gate. Uses event delegation only
// (no inline onclick) per mobile-safe guidelines.

import * as library from './library.js';
import { render as renderAtlas } from './atlas.js';

const TAB_STORAGE_KEY = 'speedreader.library.tab';

/* ------------------------------ utilities ------------------------------ */

/**
 * Escape HTML-dangerous characters.
 * @param {unknown} s
 * @returns {string}
 */
function esc(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, ch => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[ch]));
}

/**
 * Format an ISO datetime as a short human date.
 * @param {string | null | undefined} iso
 * @returns {string}
 */
function shortDate(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    return d.toISOString().slice(0, 10); // YYYY-MM-DD
  } catch {
    return '';
  }
}

/**
 * URL-safe slug from a title.
 * @param {string} title
 * @returns {string}
 */
function slugify(title) {
  return String(title || 'untitled')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'untitled';
}

/* ------------------------------ state ---------------------------------- */

const state = {
  tab: /** @type {'list' | 'atlas'} */ ('list'),
  panelOpen: false,
  panelKind: /** @type {'source' | 'concept' | null} */ (null),
  panelId: /** @type {string | null} */ (null),
  deleteArmedFor: /** @type {string | null} */ (null),
  deleteArmTimer: /** @type {number | null} */ (null),
};

/* ------------------------------ DOM refs ------------------------------- */

const refs = {
  /** @type {HTMLElement} */ counter: null,
  /** @type {NodeListOf<HTMLButtonElement>} */ tabButtons: null,
  /** @type {HTMLElement} */ listPanel: null,
  /** @type {HTMLElement} */ atlasPanel: null,
  /** @type {HTMLElement} */ detailPanel: null,
  /** @type {HTMLElement} */ scrim: null,
  /** @type {HTMLElement} */ panelKicker: null,
  /** @type {HTMLElement} */ panelTitle: null,
  /** @type {HTMLElement} */ panelSub: null,
  /** @type {HTMLElement} */ panelBody: null,
};

/* ------------------------------ tabs ----------------------------------- */

/**
 * @param {'list' | 'atlas'} tab
 */
function setTab(tab) {
  state.tab = tab;
  try {
    sessionStorage.setItem(TAB_STORAGE_KEY, tab);
  } catch {
    /* ignore */
  }
  refs.tabButtons.forEach(btn => {
    const active = btn.dataset.tab === tab;
    btn.setAttribute('aria-pressed', active ? 'true' : 'false');
  });
  refs.listPanel.hidden = tab !== 'list';
  refs.atlasPanel.hidden = tab !== 'atlas';
  if (tab === 'list') renderList();
  else renderAtlasTab();
}

/**
 * Restore tab from sessionStorage, default to 'list'.
 * If the URL has a #saved-{id} hash, always land on List so the new card
 * is visible for the pulse highlight (otherwise the redirect from the
 * Finish flow silently no-ops when the user's last tab was Atlas).
 */
function restoreTab() {
  let tab = 'list';
  try {
    const stored = sessionStorage.getItem(TAB_STORAGE_KEY);
    if (stored === 'list' || stored === 'atlas') tab = stored;
  } catch {
    /* ignore */
  }
  if (/^#saved-/.test(window.location.hash || '')) tab = 'list';
  setTab(/** @type {'list' | 'atlas'} */ (tab));
}

/* ------------------------------ list tab ------------------------------- */

function renderList() {
  const sources = library.all();
  refs.counter.textContent = `${sources.length} source${sources.length === 1 ? '' : 's'}`;

  if (sources.length === 0) {
    refs.listPanel.innerHTML = `
      <div class="empty-state">
        <blockquote>Nothing saved yet. Finish a read to begin your atlas.</blockquote>
        <div class="rule"></div>
        <a class="back-to-reader" href="/">← back to reader</a>
      </div>
    `;
    return;
  }

  const cardsHtml = sources.map(src => renderCardHtml(src)).join('');
  refs.listPanel.innerHTML = `<div class="card-grid">${cardsHtml}</div>`;

  handleDeepLink();
}

/**
 * @param {*} src
 * @returns {string}
 */
function renderCardHtml(src) {
  const date = shortDate(src.finished_at || src.last_read_at || src.ingested_at);
  const sourceType = esc(src.source_type || 'text');
  const title = esc(src.title || 'Untitled');
  const summary = esc(src.summary || '');
  const quotes = Array.isArray(src.key_quotes) ? src.key_quotes.slice(0, 2) : [];
  const tags = Array.isArray(src.tags) ? src.tags : [];
  const wpm = src.wpm ? `${src.wpm} wpm` : '';
  const charCount = src.char_count ? `${src.char_count.toLocaleString()} chars` : '';
  const footerMeta = [charCount, wpm].filter(Boolean).join(' · ');

  const quotesHtml = quotes.length
    ? `<ul class="quotes">${quotes.map(q => `<li>${esc(q)}</li>`).join('')}</ul>`
    : '';
  const tagsHtml = tags.length
    ? `<div class="tags">${tags.map(t => `<span class="mini-chip">${esc(t)}</span>`).join('')}</div>`
    : '';

  return `
    <article class="reading-card" data-action="open-source" data-source-id="${esc(src.id)}" id="card-${esc(src.id)}">
      <div class="kicker">
        <span>SOURCE</span>
        <span class="dot">·</span>
        <span>${sourceType}</span>
        ${date ? `<span class="dot">·</span><span>${esc(date)}</span>` : ''}
      </div>
      <h3 class="title">${title}</h3>
      <div class="hairline"></div>
      ${summary ? `<p class="summary">${summary}</p>` : ''}
      ${quotesHtml}
      ${tagsHtml}
      <div class="footer">
        <span>${esc(footerMeta)}</span>
        <button class="export-btn" data-action="export" data-source-id="${esc(src.id)}" aria-label="Export card as PNG">
          <svg viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.2" aria-hidden="true">
            <path d="M6 1.5 V 8" stroke-linecap="round"/>
            <path d="M3 5.5 L 6 8.5 L 9 5.5" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M2 10.5 H 10" stroke-linecap="round"/>
          </svg>
          <span>export</span>
        </button>
      </div>
    </article>
  `;
}

/**
 * Honor URL hash #saved-{id} by scrolling the card into view
 * and adding a brass pulse class, then removing the hash.
 */
function handleDeepLink() {
  const hash = window.location.hash || '';
  const m = hash.match(/^#saved-(.+)$/);
  if (!m) return;
  const id = m[1];
  const card = document.getElementById(`card-${id}`);
  if (!card) return;
  card.scrollIntoView({ behavior: 'smooth', block: 'center' });
  card.classList.add('just-saved');
  window.setTimeout(() => {
    card.classList.remove('just-saved');
  }, 2500);
  // clear the hash without triggering a reload
  history.replaceState(null, '', window.location.pathname + window.location.search);
}

/* ------------------------------ export PNG ----------------------------- */

/**
 * @param {string} sourceId
 * @param {HTMLButtonElement} triggerBtn
 */
async function exportCardAsPng(sourceId, triggerBtn) {
  if (typeof window.html2canvas !== 'function') {
    console.warn('html2canvas not loaded');
    return;
  }
  const card = document.getElementById(`card-${sourceId}`);
  if (!card) return;
  const src = library.get(sourceId);
  if (!src) return;

  triggerBtn.dataset.busy = 'true';
  try {
    const canvas = await window.html2canvas(card, {
      backgroundColor: '#0a0906',
      scale: 2,
      logging: false,
      useCORS: true,
    });
    const blob = await new Promise(resolve => canvas.toBlob(resolve, 'image/png'));
    if (!blob) return;
    const date = shortDate(src.finished_at || src.last_read_at) || shortDate(new Date().toISOString());
    const filename = `speedreader-${slugify(src.title)}-${date}.png`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    console.warn('export failed:', err);
  } finally {
    delete triggerBtn.dataset.busy;
  }
}

/* ------------------------------ atlas tab ------------------------------ */

function renderAtlasTab() {
  const size = library.size();
  const GATE = 15;

  if (size < GATE) {
    const remaining = GATE - size;
    const progress = size / GATE;
    const circumference = 2 * Math.PI * 85; // r=85
    const dashOffset = circumference * (1 - progress);

    refs.atlasPanel.innerHTML = `
      <div class="atlas-gate">
        <div class="kicker">ATLAS · LOCKED</div>
        <div class="ring-wrap">
          <svg viewBox="0 0 180 180" aria-hidden="true">
            <circle class="ring-track" cx="90" cy="90" r="85"></circle>
            <circle class="ring-fill" cx="90" cy="90" r="85"
                    stroke-dasharray="${circumference.toFixed(2)}"
                    stroke-dashoffset="${dashOffset.toFixed(2)}"></circle>
          </svg>
          <div class="ring-center">
            <span class="big">${size}</span>
            <span class="slash">/ ${GATE}</span>
          </div>
        </div>
        <p class="sub">The mind-map renders when you've read enough for the graph to be worth rendering.</p>
        <div class="help">${remaining} more to unlock</div>
      </div>
    `;
    return;
  }

  // unlocked: render the radial
  const topConceptsCount = library.conceptCounts().length;
  refs.atlasPanel.innerHTML = `
    <div class="atlas-wrap">
      <div class="atlas-corner tl">
        <div>Orbit · 01</div>
        <div>concepts</div>
      </div>
      <div class="atlas-corner br">
        <div>${topConceptsCount} concept${topConceptsCount === 1 ? '' : 's'}</div>
        <div>tap any node</div>
      </div>
      <svg id="atlas-svg" aria-label="Knowledge atlas — radial concept map"></svg>
    </div>
  `;

  // Give the DOM a tick to lay out so the SVG has dimensions.
  requestAnimationFrame(() => {
    renderAtlas('#atlas-svg', {
      concepts: library.conceptCounts(), // already sorted by count
      sources: library.all(),
      onConceptClick: (cid) => openConceptPanel(cid),
    });
  });
}

/* ------------------------------ detail panel --------------------------- */

function openPanel() {
  state.panelOpen = true;
  refs.detailPanel.dataset.open = 'true';
  refs.detailPanel.setAttribute('aria-hidden', 'false');
  refs.scrim.dataset.show = 'true';
}
function closePanel() {
  state.panelOpen = false;
  state.panelKind = null;
  state.panelId = null;
  state.deleteArmedFor = null;
  if (state.deleteArmTimer) {
    window.clearTimeout(state.deleteArmTimer);
    state.deleteArmTimer = null;
  }
  refs.detailPanel.dataset.open = 'false';
  refs.detailPanel.setAttribute('aria-hidden', 'true');
  refs.scrim.dataset.show = 'false';
}

/**
 * @param {string} sourceId
 */
function openSourcePanel(sourceId) {
  const src = library.get(sourceId);
  if (!src) return;
  state.panelKind = 'source';
  state.panelId = sourceId;

  const sourceType = esc(src.source_type || 'text');
  const date = shortDate(src.finished_at || src.last_read_at);
  const wpm = src.wpm ? `${src.wpm} wpm` : '';
  const subParts = [sourceType, date, wpm].filter(Boolean);

  refs.panelKicker.textContent = 'Source';
  refs.panelTitle.textContent = src.title || 'Untitled';
  refs.panelSub.textContent = subParts.join(' · ');

  const tags = Array.isArray(src.tags) ? src.tags : [];
  const quotes = Array.isArray(src.key_quotes) ? src.key_quotes : [];

  let body = '';
  if (src.url) {
    body += `<div class="section-rule"><span class="kicker">Source</span><span class="line"></span></div>`;
    body += `<p class="panel-source"><a href="${esc(src.url)}" target="_blank" rel="noreferrer noopener">${esc(src.url)}</a></p>`;
    if (src.source_type === 'twitter') {
      const m = src.url.match(/\/status(?:es)?\/(\d+)/);
      if (m) {
        const unroll = `https://threadreaderapp.com/thread/${m[1]}.html`;
        body += `<p class="panel-source"><a href="${esc(unroll)}" target="_blank" rel="noreferrer noopener">View unrolled thread →</a></p>`;
      }
    }
  }
  if (src.summary) {
    body += `<div class="section-rule"><span class="kicker">Summary</span><span class="line"></span></div>`;
    body += `<p class="panel-summary">${esc(src.summary)}</p>`;
  }
  if (quotes.length) {
    body += `<div class="section-rule"><span class="kicker">Quotes</span><span class="line"></span></div>`;
    body += `<ul class="panel-quotes">${quotes.map(q => `<li>${esc(q)}</li>`).join('')}</ul>`;
  }
  if (tags.length) {
    body += `<div class="section-rule"><span class="kicker">Tags</span><span class="line"></span></div>`;
    body += `<div class="mini-chips">${tags.map(t => `<span class="mini-chip">${esc(t)}</span>`).join('')}</div>`;
  }
  if (src.user_recall) {
    body += `<div class="section-rule"><span class="kicker">Recall-note</span><span class="line"></span></div>`;
    body += `<p class="panel-summary">${esc(src.user_recall)}</p>`;
  }
  body += `
    <div class="panel-actions">
      <button class="replay-btn" data-action="replay" data-source-id="${esc(sourceId)}">
        Speed-read again <span class="arrow"></span>
      </button>
      <button class="delete-btn" data-action="delete" data-source-id="${esc(sourceId)}">Delete</button>
    </div>
  `;

  refs.panelBody.innerHTML = body;
  openPanel();
}

/**
 * @param {string} conceptId
 */
function openConceptPanel(conceptId) {
  const conceptList = library.concepts();
  const concept = conceptList.find(c => c.id === conceptId);
  if (!concept) return;
  state.panelKind = 'concept';
  state.panelId = conceptId;

  const sourceIds = Array.isArray(concept.source_ids) ? concept.source_ids : [];
  const idSet = new Set(sourceIds);
  const resolved = library.all()
    .filter(s => idSet.has(s.id))
    .sort((a, b) => (b.finished_at || '').localeCompare(a.finished_at || ''));

  refs.panelKicker.textContent = 'Concept';
  refs.panelTitle.textContent = concept.label;
  refs.panelSub.textContent = `${resolved.length} source${resolved.length === 1 ? '' : 's'} · referenced across the atlas`;

  let body = `<div class="section-rule"><span class="kicker">Sources</span><span class="line"></span></div>`;
  if (!resolved.length) {
    body += `<p style="color:var(--ink-mute);font-style:italic">No sources reference this concept yet.</p>`;
  } else {
    body += `<div class="concept-source-list">`;
    resolved.forEach((s, i) => {
      const date = shortDate(s.finished_at || s.last_read_at);
      const wpm = s.wpm ? `${s.wpm} wpm` : '';
      const sourceType = esc(s.source_type || 'text');
      body += `
        <button class="concept-source-row" data-action="open-source" data-source-id="${esc(s.id)}">
          <span class="idx">${String(i + 1).padStart(2, '0')}</span>
          <span class="nt">${esc(s.title || 'Untitled')}</span>
          <span class="nm">${esc([date, wpm, sourceType].filter(Boolean).join(' · '))}</span>
        </button>
      `;
    });
    body += `</div>`;
  }

  refs.panelBody.innerHTML = body;
  openPanel();
}

/**
 * Handle delete: first click arms, second click (within 2s) confirms.
 * @param {string} sourceId
 * @param {HTMLButtonElement} btn
 */
function handleDelete(sourceId, btn) {
  if (state.deleteArmedFor === sourceId) {
    // confirmed — actually delete
    library.remove(sourceId);
    if (state.deleteArmTimer) {
      window.clearTimeout(state.deleteArmTimer);
      state.deleteArmTimer = null;
    }
    state.deleteArmedFor = null;
    closePanel();
    // re-render whichever tab is active
    if (state.tab === 'list') renderList();
    else renderAtlasTab();
    return;
  }
  // arm
  state.deleteArmedFor = sourceId;
  btn.dataset.armed = 'true';
  btn.textContent = 'Tap again to confirm';
  if (state.deleteArmTimer) window.clearTimeout(state.deleteArmTimer);
  state.deleteArmTimer = window.setTimeout(() => {
    state.deleteArmedFor = null;
    state.deleteArmTimer = null;
    if (btn.isConnected) {
      delete btn.dataset.armed;
      btn.textContent = 'Delete';
    }
  }, 2000);
}

/* ------------------------------ events --------------------------------- */

function initEvents() {
  document.addEventListener('click', (e) => {
    const target = /** @type {HTMLElement} */ (e.target);

    // tab buttons
    const tabBtn = target.closest('button[data-tab]');
    if (tabBtn) {
      const tab = /** @type {'list' | 'atlas'} */ (tabBtn.dataset.tab);
      setTab(tab);
      return;
    }

    // export button — MUST be checked before the card click so we don't open the panel
    const exportBtn = target.closest('[data-action="export"]');
    if (exportBtn) {
      e.stopPropagation();
      const sid = exportBtn.dataset.sourceId;
      if (sid) exportCardAsPng(sid, /** @type {HTMLButtonElement} */ (exportBtn));
      return;
    }

    // close panel
    if (target.closest('[data-action="close"]')) {
      closePanel();
      return;
    }

    // replay (no-op for v1)
    const replayBtn = target.closest('[data-action="replay"]');
    if (replayBtn) {
      e.stopPropagation();
      const sid = replayBtn.dataset.sourceId;
      console.log('replay:', sid);
      return;
    }

    // delete
    const deleteBtn = target.closest('[data-action="delete"]');
    if (deleteBtn) {
      e.stopPropagation();
      const sid = deleteBtn.dataset.sourceId;
      if (sid) handleDelete(sid, /** @type {HTMLButtonElement} */ (deleteBtn));
      return;
    }

    // open-source (reading card OR concept source row)
    const openSrc = target.closest('[data-action="open-source"]');
    if (openSrc) {
      const sid = openSrc.dataset.sourceId;
      if (sid) openSourcePanel(sid);
      return;
    }

    // outside-click dismiss
    if (state.panelOpen && !target.closest('.detail-panel')) {
      closePanel();
    }
  });

  // ESC closes panel
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && state.panelOpen) {
      closePanel();
      return;
    }
    // tab arrow-key navigation when focus is on a tab
    if (document.activeElement && document.activeElement.matches('button[data-tab]')) {
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        e.preventDefault();
        const buttons = Array.from(refs.tabButtons);
        const idx = buttons.indexOf(/** @type {HTMLButtonElement} */ (document.activeElement));
        const next = e.key === 'ArrowLeft'
          ? (idx - 1 + buttons.length) % buttons.length
          : (idx + 1) % buttons.length;
        buttons[next].focus();
        const tab = /** @type {'list' | 'atlas'} */ (buttons[next].dataset.tab);
        setTab(tab);
      }
    }
  });

  // re-render atlas on window resize (debounced)
  let resizeTimer = null;
  window.addEventListener('resize', () => {
    if (state.tab !== 'atlas') return;
    if (library.size() < 15) return;
    if (resizeTimer) window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => {
      renderAtlasTab();
    }, 180);
  });
}

/* ------------------------------ boot ----------------------------------- */

function boot() {
  refs.counter = document.querySelector('[data-counter]');
  refs.tabButtons = document.querySelectorAll('button[data-tab]');
  refs.listPanel = document.querySelector('[data-panel="list"]');
  refs.atlasPanel = document.querySelector('[data-panel="atlas"]');
  refs.detailPanel = document.querySelector('.detail-panel');
  refs.scrim = document.querySelector('.scrim');
  refs.panelKicker = document.querySelector('[data-panel-kicker]');
  refs.panelTitle = document.querySelector('[data-panel-title]');
  refs.panelSub = document.querySelector('[data-panel-sub]');
  refs.panelBody = document.querySelector('[data-panel-body]');

  initEvents();
  restoreTab();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', boot);
} else {
  boot();
}
