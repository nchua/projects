import { Readability } from '@mozilla/readability';
import { JSDOM } from 'jsdom';

const FETCH_TIMEOUT_MS = 15000;
const MAX_HTML_BYTES = 2 * 1024 * 1024;
const UA = 'Mozilla/5.0 (compatible; SpeedReaderBot/0.1; +https://github.com/nchua/projects)';

const TWITTER_HOSTS = new Set([
  'twitter.com', 'www.twitter.com', 'mobile.twitter.com', 'm.twitter.com',
  'x.com', 'www.x.com', 'mobile.x.com', 'm.x.com',
  'fxtwitter.com', 'vxtwitter.com', 'fixupx.com',
]);

const TWEET_PATH_RE = /^\/(?:i\/web\/status|[^/]+\/status(?:es)?)\/(\d+)/;

function isTwitterUrl(parsed) {
  return TWITTER_HOSTS.has(parsed.hostname.toLowerCase()) && TWEET_PATH_RE.test(parsed.pathname);
}

function tweetIdFrom(parsed) {
  const m = parsed.pathname.match(TWEET_PATH_RE);
  return m ? m[1] : null;
}

async function extractTweet(parsed) {
  const tweetId = tweetIdFrom(parsed);
  if (!tweetId) return { error: 'invalid tweet url', status: 400 };

  const apiUrl = `https://api.fxtwitter.com/status/${tweetId}`;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  try {
    const upstream = await fetch(apiUrl, {
      headers: { 'User-Agent': UA, 'Accept': 'application/json' },
      signal: controller.signal,
    });
    if (!upstream.ok) {
      return { error: `fxtwitter ${upstream.status}`, status: 502 };
    }
    const json = await upstream.json();
    if (json.code !== 200 || !json.tweet) {
      return { error: json.message || 'tweet not found', status: 502 };
    }

    const t = json.tweet;
    const body = renderTweetText(t);
    const author = t.author || {};
    const handle = author.screen_name ? `@${author.screen_name}` : '';
    const name = author.name || handle || 'Unknown';
    const dateStr = t.created_at ? formatDate(t.created_at) : '';
    const titleSeed = (t.text || '').replace(/\s+/g, ' ').trim().slice(0, 80) || `Tweet ${tweetId}`;
    const title = `${name}${handle ? ` (${handle})` : ''} — ${titleSeed}${titleSeed.length === 80 ? '…' : ''}`;

    return {
      ok: true,
      payload: {
        title,
        text: body,
        byline: handle ? `${name} ${handle}` : name,
        siteName: dateStr ? `X · ${dateStr}` : 'X',
      },
    };
  } catch (err) {
    const msg = err?.name === 'AbortError' ? 'fxtwitter timeout' : (err?.message || 'fxtwitter failed');
    return { error: msg, status: 502 };
  } finally {
    clearTimeout(timeout);
  }
}

function renderTweetText(t) {
  const parts = [];
  const author = t.author || {};
  const handle = author.screen_name ? `@${author.screen_name}` : '';
  const name = author.name || handle || 'Unknown';
  const dateStr = t.created_at ? formatDate(t.created_at) : '';

  parts.push(`${name}${handle ? ` ${handle}` : ''}${dateStr ? ` · ${dateStr}` : ''}`);
  parts.push('');
  parts.push((t.text || '').trim());

  // Quote-tweet: include inline so the summarizer sees the full context.
  const qrt = t.quote;
  if (qrt && qrt.text) {
    const qa = qrt.author || {};
    const qhandle = qa.screen_name ? `@${qa.screen_name}` : '';
    const qname = qa.name || qhandle || 'Quoted user';
    parts.push('');
    parts.push(`Quoting ${qname}${qhandle ? ` ${qhandle}` : ''}:`);
    parts.push(qrt.text.trim());
  }

  // Reply context: if this tweet is itself a reply, show the parent author.
  // (Useful for mid-thread URLs so the summary notes "this is a reply to X".)
  if (t.replying_to && t.replying_to_status) {
    parts.push('');
    parts.push(`(In reply to @${t.replying_to})`);
  }

  // Engagement footer for context, not for the summarizer.
  parts.push('');
  parts.push('---');
  const stats = [
    typeof t.likes === 'number' ? `${formatCount(t.likes)} likes` : null,
    typeof t.retweets === 'number' ? `${formatCount(t.retweets)} reposts` : null,
    typeof t.replies === 'number' ? `${formatCount(t.replies)} replies` : null,
  ].filter(Boolean);
  if (stats.length) parts.push(stats.join(' · '));
  if (t.url) parts.push(t.url);

  // Honest note if this looks like a multi-tweet thread head we couldn't walk.
  // Heuristic: thread head + many replies + not a Note Tweet.
  if (!t.replying_to && !t.is_note_tweet && typeof t.replies === 'number' && t.replies >= 3) {
    parts.push('');
    parts.push('(Note: this tweet may be the head of a thread. Twitter does not expose thread structure to free APIs, so only this single tweet was ingested. To capture the full thread, copy-paste the unrolled text into the reader.)');
  }

  return parts.join('\n').trim();
}

function formatDate(s) {
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return '';
  return d.toISOString().slice(0, 10);
}

function formatCount(n) {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, '') + 'M';
  if (n >= 1_000) return (n / 1_000).toFixed(1).replace(/\.0$/, '') + 'K';
  return String(n);
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'method not allowed' });
    return;
  }

  const body = req.body && typeof req.body === 'object' ? req.body : {};
  const url = typeof body.url === 'string' ? body.url.trim() : '';

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

  if (isTwitterUrl(parsed)) {
    const result = await extractTweet(parsed);
    if (result.ok) {
      res.status(200).json(result.payload);
    } else {
      res.status(result.status || 502).json({ error: result.error });
    }
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
    if (html.length > MAX_HTML_BYTES) {
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
