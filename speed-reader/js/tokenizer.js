const WORD_RE = /[A-Za-z0-9][A-Za-z0-9'\u2019]*(?:-[A-Za-z0-9'\u2019]+)*/g;
const TRAIL_CHARS = `.,;:!?)"\u201D\u2014\u2013`;
const LEADING_TRAIL_RE = new RegExp(`^[${TRAIL_CHARS.replace(/[-\]\\]/g, '\\$&')}]+`);
const NUMERIC_RE = /^[0-9][0-9,.]*$/;
const MAX_CORE = 13;
const CHUNK_TARGET = 8;

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

function splitLongWord(word, trailing) {
  const parts = [];
  let remaining = word;
  while (remaining.length > MAX_CORE) {
    let cut = CHUNK_TARGET;
    for (let i = CHUNK_TARGET; i > CHUNK_TARGET - 3 && i > 1; i--) {
      if (/[aeiouy]/i.test(remaining[i - 1])) { cut = i; break; }
    }
    parts.push(remaining.slice(0, cut) + '-');
    remaining = remaining.slice(cut);
  }
  parts.push(remaining);

  const tokens = [];
  for (let i = 0; i < parts.length; i++) {
    const isLast = i === parts.length - 1;
    const p = parts[i];
    const trail = isLast ? trailing : '';
    tokens.push(makeToken(p, trail, { isFragment: true }));
  }
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
    const between = cleaned.slice(end, nextStart);
    const trailMatch = between.match(LEADING_TRAIL_RE);
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
