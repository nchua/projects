const WORD_RE = /[A-Za-z0-9][A-Za-z0-9'\u2019]*(?:-[A-Za-z0-9'\u2019]+)*/g;
const TRAIL_RE = /[.,;:!?)"\u201D\u2014\u2013]+$/;
const NUMERIC_RE = /^[0-9][0-9,.]*$/;

function normalize(text) {
  return text.normalize('NFC').replace(/\r\n?/g, '\n').replace(/\f/g, '');
}

function analyse(word, trailing) {
  const core = word.replace(/['\u2019]/g, '');
  return {
    word,
    trailing: trailing || '',
    isBreak: false,
    isNumeric: NUMERIC_RE.test(word),
    allCaps: core.length >= 3 && core === core.toUpperCase() && /[A-Z]/.test(core),
  };
}

function tokenizeParagraph(para) {
  const tokens = [];
  const cleaned = para.replace(/\n/g, ' ');
  let lastEnd = 0;
  const matches = [...cleaned.matchAll(WORD_RE)];

  for (let i = 0; i < matches.length; i++) {
    const m = matches[i];
    const start = m.index;
    const end = start + m[0].length;
    const nextStart = i + 1 < matches.length ? matches[i + 1].index : cleaned.length;
    const between = cleaned.slice(end, nextStart);
    const trailMatch = between.match(/^[.,;:!?)"\u201D\u2014\u2013]+/);
    const trailing = trailMatch ? trailMatch[0] : '';
    tokens.push(analyse(m[0], trailing));
    lastEnd = end;
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
    if (tokens.length > 0) tokens.push({ word: '', trailing: '', isBreak: true, isNumeric: false, allCaps: false });
    tokens.push(...tokenizeParagraph(p));
  }
  return tokens;
}
