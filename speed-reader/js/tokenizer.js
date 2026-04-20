const WORD_RE = /[A-Za-z0-9][A-Za-z0-9'\u2019]*(?:-[A-Za-z0-9'\u2019]+)*/g;
const TRAIL_CHARS = `.,;:!?)"\u201D\u2014\u2013`;
const LEADING_TRAIL_RE = new RegExp(`^[${TRAIL_CHARS.replace(/[-\]\\]/g, '\\$&')}]+`);
const NUMERIC_RE = /^[0-9][0-9,.]*$/;
const VOWEL_RE = /[aeiouy]/i;
const MAX_CORE = 13;
const CHUNK_TARGET = 8;
const VOWEL_SEARCH_WINDOW = 3;

function normalize(text) {
  return text.normalize('NFC').replace(/\r\n?/g, '\n').replace(/\f/g, '');
}

function coreOf(word) {
  return word.replace(/['\u2019-]/g, '');
}

function makeToken(word, trailing, opts = {}) {
  const core = coreOf(word);
  return {
    word,
    trailing: trailing || '',
    isBreak: false,
    isNumeric: NUMERIC_RE.test(word),
    allCaps: core.length >= 3 && core === core.toUpperCase() && /[A-Z]/.test(core),
    coreLen: core.length,
    isFragment: !!opts.isFragment,
  };
}

function makeBreak() {
  return { word: '', trailing: '', isBreak: true, isNumeric: false, allCaps: false, coreLen: 0, isFragment: false };
}

function findVowelCut(word, start, target) {
  for (let offset = 0; offset < VOWEL_SEARCH_WINDOW && (target - offset) > start + 1; offset++) {
    const cutIdx = start + target - offset;
    if (VOWEL_RE.test(word[cutIdx - 1])) return cutIdx;
  }
  return start + target;
}

function splitLongWord(word, trailing) {
  const tokens = [];
  let start = 0;
  while (word.length - start > MAX_CORE) {
    const cut = findVowelCut(word, start, CHUNK_TARGET);
    tokens.push(makeToken(word.slice(start, cut) + '-', '', { isFragment: true }));
    start = cut;
  }
  tokens.push(makeToken(word.slice(start), trailing, { isFragment: true }));
  return tokens;
}

function tokenizeParagraph(para) {
  const tokens = [];
  const cleaned = para.replace(/\n/g, ' ');
  const matches = [...cleaned.matchAll(WORD_RE)];

  for (let i = 0; i < matches.length; i++) {
    const m = matches[i];
    const end = m.index + m[0].length;
    const nextStart = i + 1 < matches.length ? matches[i + 1].index : cleaned.length;
    const trailMatch = cleaned.slice(end, nextStart).match(LEADING_TRAIL_RE);
    const trailing = trailMatch ? trailMatch[0] : '';
    const word = m[0];

    if (coreOf(word).length > MAX_CORE) {
      const frags = splitLongWord(word, trailing);
      for (let j = 0; j < frags.length; j++) tokens.push(frags[j]);
    } else {
      tokens.push(makeToken(word, trailing));
    }
  }
  return tokens;
}

export function tokenize(raw) {
  if (!raw || typeof raw !== 'string') return [];
  const text = normalize(raw).trim();
  if (!text) return [];
  const paragraphs = text.split(/\n\s*\n+/);
  const tokens = [];
  for (let i = 0; i < paragraphs.length; i++) {
    const p = paragraphs[i].trim();
    if (!p) continue;
    if (tokens.length > 0) tokens.push(makeBreak());
    const sub = tokenizeParagraph(p);
    for (let j = 0; j < sub.length; j++) tokens.push(sub[j]);
  }
  return tokens;
}
