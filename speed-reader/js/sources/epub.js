const JSZIP_CDN = 'https://cdn.jsdelivr.net/npm/jszip@3.10.1/+esm';

let JSZip = null;

async function loadZip() {
  if (JSZip) return JSZip;
  const mod = await import(/* @vite-ignore */ JSZIP_CDN);
  JSZip = mod.default || mod;
  return JSZip;
}

function htmlToText(html) {
  const doc = new DOMParser().parseFromString(html, 'text/html');
  doc.querySelectorAll('script, style, nav').forEach(el => el.remove());
  const blocks = [];
  doc.body?.querySelectorAll('p, h1, h2, h3, h4, h5, h6, li, blockquote, div').forEach(el => {
    const text = el.textContent?.trim();
    if (text) blocks.push(text);
  });
  if (blocks.length === 0 && doc.body) blocks.push(doc.body.textContent?.trim() || '');
  return blocks.join('\n\n');
}

export async function extractText(file) {
  const JSZipCtor = await loadZip();
  const buf = await file.arrayBuffer();
  const zip = await JSZipCtor.loadAsync(buf);

  const containerXml = await zip.file('META-INF/container.xml')?.async('string');
  if (!containerXml) throw new Error('Invalid EPUB: missing container.xml');
  const opfPath = containerXml.match(/full-path="([^"]+)"/)?.[1];
  if (!opfPath) throw new Error('Invalid EPUB: OPF path not found');

  const opfXml = await zip.file(opfPath).async('string');
  const opfDir = opfPath.includes('/') ? opfPath.slice(0, opfPath.lastIndexOf('/') + 1) : '';

  const manifest = {};
  for (const m of opfXml.matchAll(/<item\s+([^>]+)\/?>/g)) {
    const attrs = m[1];
    const id = attrs.match(/id="([^"]+)"/)?.[1];
    const href = attrs.match(/href="([^"]+)"/)?.[1];
    const type = attrs.match(/media-type="([^"]+)"/)?.[1];
    if (id && href && type && /html|xml/.test(type)) manifest[id] = href;
  }

  const spine = [];
  for (const m of opfXml.matchAll(/<itemref\s+[^>]*idref="([^"]+)"/g)) {
    if (manifest[m[1]]) spine.push(opfDir + manifest[m[1]]);
  }

  const parts = [];
  for (const href of spine) {
    const entry = zip.file(href);
    if (!entry) continue;
    const html = await entry.async('string');
    const text = htmlToText(html);
    if (text) parts.push(text);
  }
  return parts.join('\n\n');
}
