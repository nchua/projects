export function pivotIndex(word) {
  const n = word.length;
  if (n <= 1) return 0;
  if (n <= 5) return 1;
  if (n <= 9) return 2;
  if (n <= 13) return 3;
  return 4;
}

export function splitWord(token) {
  if (token.isBreak) return { pre: '', piv: '\u00B6', post: '' };
  const word = token.word;
  const idx = pivotIndex(word);
  return {
    pre: word.slice(0, idx),
    piv: word[idx] || '',
    post: word.slice(idx + 1) + (token.trailing || ''),
  };
}

let measureCtx = null;
export function measurePivotHalf(ch, fontSpec) {
  if (!ch) return 0;
  if (!measureCtx) {
    const canvas = document.createElement('canvas');
    measureCtx = canvas.getContext('2d');
  }
  measureCtx.font = fontSpec;
  const metrics = measureCtx.measureText(ch);
  return metrics.width / 2;
}
