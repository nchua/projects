const PDFJS_CDN = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.7.76/build/pdf.min.mjs';
const PDFJS_WORKER = 'https://cdn.jsdelivr.net/npm/pdfjs-dist@4.7.76/build/pdf.worker.min.mjs';

let pdfjsLib = null;

async function load() {
  if (pdfjsLib) return pdfjsLib;
  pdfjsLib = await import(/* @vite-ignore */ PDFJS_CDN);
  pdfjsLib.GlobalWorkerOptions.workerSrc = PDFJS_WORKER;
  return pdfjsLib;
}

function renderPage(content) {
  const parts = [];
  let lastY = null;
  for (const item of content.items) {
    if (lastY !== null && item.transform[5] !== lastY) parts.push('\n');
    parts.push(item.str);
    lastY = item.transform[5];
  }
  return parts.join('');
}

export async function extract(file) {
  const lib = await load();
  const buf = await file.arrayBuffer();
  const pdf = await lib.getDocument({ data: buf }).promise;
  const pageContents = await Promise.all(
    Array.from({ length: pdf.numPages }, (_, i) =>
      pdf.getPage(i + 1).then(p => p.getTextContent())
    )
  );
  const text = pageContents.map(renderPage).join('\n\n');
  return { title: file.name || '', text };
}
