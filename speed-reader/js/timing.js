const MIN_DWELL = 50;
const MAX_DWELL = 1500;

export function dwellMs(token, wpm) {
  const base = 60000 / wpm;
  if (token.isBreak) return clamp(base * 3.5);

  const core = token.word.replace(/['\u2019-]/g, '');
  const len = core.length;
  let mult = 1.0;

  if (len > 12) mult = Math.max(mult, 1.8);
  else if (len > 8) mult = Math.max(mult, 1.5);

  if (token.allCaps) mult = Math.max(mult, 1.3);
  if (token.isNumeric) mult = Math.max(mult, 1.4);

  const trailing = token.trailing || '';
  if (/[.!?]/.test(trailing)) mult = Math.max(mult, 2.5);
  else if (/[,;:]/.test(trailing)) mult = Math.max(mult, 1.5);
  else if (/[\u2014\u2013]/.test(trailing)) mult = Math.max(mult, 1.5);

  return clamp(base * mult);
}

function clamp(ms) {
  return Math.max(MIN_DWELL, Math.min(MAX_DWELL, ms));
}
