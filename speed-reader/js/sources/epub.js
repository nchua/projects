const JSZIP_CDN = 'https://cdn.jsdelivr.net/npm/jszip@3.10.1/+esm';

const FULL_PATH_RE = /full-path="([^"]+)"/;
const BLOCK_SELECTOR = 'p, h1, h2, h3, h4, h5, h6, li, blockquote, div';
const DROP_SELECTOR = 'script, style, nav';

let JSZip = null;

async function loadZip() {
  if (JSZip) return JSZip;
  const mod = await import(/* @vite-ignore */ JSZIP_CDN);
  JSZip = mod.default || mod;
  return JSZip;
}

function htmlToText(html) {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.querySelectorAll(DROP_SELECTOR).forEach(el => el.remove());
  const blocks = [];
  doc.body?.querySelectorAll(BLOCK_SELECTOR).forEach(el => {
    const text = el.textContent?.trim();
    if (text) blocks.push(text);
  });
  if (blocks.length === 0 && doc.body) blocks.push(doc.body.textContent?.trim() || '');
  return blocks.join('\n\n');
}

function parseOpf(opfXml, opfDir) {
  const doc = new DOMParser().parseFromString(opfXml, 'application/xml');

  const manifest = {};
  doc.querySelectorAll('manifest > item').forEach(item => {
    const id = item.getAttribute('id');
    const href = item.getAttribute('href');
    const type = item.getAttribute('media-type') || '';
    if (id && href && /html|xml/.test(type)) manifest[id] = href;
  });

  const titleEl = doc.querySelector('metadata title') || doc.querySelector('title');
  const title = titleEl?.textContent?.trim() || '';

  const spine = [];
  doc.querySelectorAll('spine > itemref').forEach(ref => {
    const idref = ref.getAttribute('idref');
    if (idref && manifest[idref]) spine.push(opfDir + manifest[idref]);
  });

  return { spine, title };
}

export async function extract(file) {
  const JSZipCtor = await loadZip();
  const buf = await file.arrayBuffer();
  const zip = await JSZipCtor.loadAsync(buf);

  const containerXml = await zip.file('META-INF/container.xml')?.async('string');
  if (!containerXml) throw new Error('Invalid EPUB: missing container.xml');
  const opfPath = containerXml.match(FULL_PATH_RE)?.[1];
  if (!opfPath) throw new Error('Invalid EPUB: OPF path not found');

  const opfXml = await zip.file(opfPath).async('string');
  const opfDir = opfPath.includes('/') ? opfPath.slice(0, opfPath.lastIndexOf('/') + 1) : '';
  const { spine, title } = parseOpf(opfXml, opfDir);

  const chapters = await Promise.all(
    spine.map(href => zip.file(href)?.async('string').then(htmlToText) || Promise.resolve(''))
  );
  const text = chapters.filter(Boolean).join('\n\n');
  return { title: title || file.name || '', text };
}
