import { Readability } from '@mozilla/readability';
import { JSDOM } from 'jsdom';

const FETCH_TIMEOUT_MS = 15000;
const MAX_BYTES = 5 * 1024 * 1024;
const UA = 'Mozilla/5.0 (compatible; SpeedReaderBot/0.1; +https://github.com/nchua/projects)';

function readBody(req) {
  return new Promise((resolve, reject) => {
    if (req.body && typeof req.body === 'object') return resolve(req.body);
    let data = '';
    req.on('data', chunk => { data += chunk; if (data.length > MAX_BYTES) req.destroy(); });
    req.on('end', () => {
      try { resolve(data ? JSON.parse(data) : {}); } catch (e) { reject(e); }
    });
    req.on('error', reject);
  });
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'method not allowed' });
    return;
  }

  let body;
  try {
    body = await readBody(req);
  } catch {
    res.status(400).json({ error: 'invalid JSON body' });
    return;
  }

  const url = body && typeof body.url === 'string' ? body.url.trim() : '';
  let parsed;
  try {
    parsed = new URL(url);
  } catch {
    res.status(400).json({ error: 'invalid url' });
    return;
  }
  if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
    res.status(400).json({ error: 'only http(s) urls allowed' });
    return;
  }

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  try {
    const upstream = await fetch(parsed.toString(), {
      headers: { 'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml' },
      signal: controller.signal,
      redirect: 'follow',
    });
    if (!upstream.ok) {
      res.status(502).json({ error: `upstream ${upstream.status}` });
      return;
    }
    const html = await upstream.text();
    if (html.length > MAX_BYTES) {
      res.status(413).json({ error: 'document too large' });
      return;
    }

    const dom = new JSDOM(html, { url: parsed.toString() });
    const article = new Readability(dom.window.document).parse();
    if (!article || !article.textContent) {
      res.status(422).json({ error: 'could not extract article' });
      return;
    }

    res.status(200).json({
      title: article.title || '',
      text: article.textContent.trim(),
      byline: article.byline || '',
      siteName: article.siteName || parsed.hostname,
    });
  } catch (err) {
    const msg = err?.name === 'AbortError' ? 'upstream timeout' : (err?.message || 'extraction failed');
    res.status(500).json({ error: msg });
  } finally {
    clearTimeout(timeout);
  }
}
