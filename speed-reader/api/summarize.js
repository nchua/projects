// Serverless summarizer: takes article text, returns a 3-5 sentence summary, concept tags, and verbatim key quotes via Claude tool-use.
import Anthropic from '@anthropic-ai/sdk';

const MAX_CHARS = 30000;
const MAX_TITLE_CHARS = 300;
const RATE_WINDOW_MS = 60 * 1000;
const RATE_MAX = 20;
const MODEL_ID = 'claude-sonnet-4-6';

const SYSTEM_PROMPT = `You help users consolidate articles they just finished in a speed-reading session.

Always respond by invoking the emit_summary tool. Never reply in prose.

Fields:
- summary: 3-5 sentences capturing the source's ARGUMENT (its thesis and how it's supported), not merely its topic.
- tags: 3-7 short concept phrases, lowercase, 1-3 words each, preferring nouns. If the request supplies preferred vocabulary (known_tags), reuse those labels when they fit rather than inventing synonyms.
- key_quotes: 2-5 short verbatim spans copied letter-for-letter from the source. These are retention artifacts, so copy precisely — same punctuation, capitalization, and spacing as the source. Do not paraphrase.`;

// Rate limit state is module-scope and therefore per-instance; Vercel cold starts reset it. Good enough as a solo-dev v1 guard.
const rateBuckets = new Map();

function clientIp(req) {
  const xff = req.headers['x-forwarded-for'];
  if (typeof xff === 'string' && xff.length > 0) {
    return xff.split(',')[0].trim();
  }
  return req.socket?.remoteAddress || 'unknown';
}

function checkRate(ip) {
  const now = Date.now();
  const cutoff = now - RATE_WINDOW_MS;
  const hits = (rateBuckets.get(ip) || []).filter((t) => t > cutoff);
  if (hits.length >= RATE_MAX) {
    rateBuckets.set(ip, hits);
    return false;
  }
  hits.push(now);
  rateBuckets.set(ip, hits);
  return true;
}

const SUMMARY_TOOL = {
  name: 'emit_summary',
  description: 'Return the structured summary of the source article.',
  input_schema: {
    type: 'object',
    properties: {
      summary: {
        type: 'string',
        description: '3-5 sentence dense summary of the source.',
      },
      tags: {
        type: 'array',
        items: { type: 'string' },
        minItems: 3,
        maxItems: 7,
        description: '3-7 short concept tags (lowercase, 1-3 words each).',
      },
      key_quotes: {
        type: 'array',
        items: { type: 'string' },
        minItems: 2,
        maxItems: 5,
        description: '2-5 verbatim quotes from the source. Copy letter-for-letter.',
      },
    },
    required: ['summary', 'tags', 'key_quotes'],
  },
};

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'method not allowed' });
    return;
  }

  const ip = clientIp(req);
  if (!checkRate(ip)) {
    res.status(429).json({ error: 'rate limit' });
    return;
  }

  const body = req.body && typeof req.body === 'object' ? req.body : {};
  const text = typeof body.text === 'string' ? body.text : '';
  if (!text || text.trim().length === 0) {
    res.status(400).json({ error: 'text is required' });
    return;
  }
  if (text.length > MAX_CHARS) {
    res.status(413).json({ error: 'text too large' });
    return;
  }

  let title = typeof body.title === 'string' ? body.title.trim() : '';
  if (title.length > MAX_TITLE_CHARS) {
    title = title.slice(0, MAX_TITLE_CHARS);
  }

  const knownTags = Array.isArray(body.known_tags)
    ? body.known_tags.filter((t) => typeof t === 'string' && t.trim().length > 0).slice(0, 50)
    : [];

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    res.status(500).json({ error: 'service unavailable' });
    return;
  }

  const userParts = [];
  if (title) {
    userParts.push(`Title: ${title}`);
  }
  if (knownTags.length > 0) {
    userParts.push(`Preferred vocabulary (reuse when they fit): ${knownTags.join(', ')}`);
  }
  userParts.push('Source text:');
  userParts.push(text);
  const userMessage = userParts.join('\n\n');

  try {
    const client = new Anthropic({ apiKey });
    const response = await client.messages.create({
      model: MODEL_ID,
      max_tokens: 1024,
      system: [
        {
          type: 'text',
          text: SYSTEM_PROMPT,
          cache_control: { type: 'ephemeral' },
        },
      ],
      tools: [SUMMARY_TOOL],
      tool_choice: { type: 'tool', name: 'emit_summary' },
      messages: [{ role: 'user', content: userMessage }],
    });

    const toolBlock = (response.content || []).find((b) => b.type === 'tool_use' && b.name === 'emit_summary');
    if (!toolBlock || !toolBlock.input) {
      console.error('summarize: model did not return emit_summary tool_use');
      res.status(502).json({ error: 'model output invalid' });
      return;
    }

    const raw = toolBlock.input;
    const summary = typeof raw.summary === 'string' ? raw.summary.trim() : '';
    const tags = Array.isArray(raw.tags)
      ? raw.tags.filter((t) => typeof t === 'string' && t.trim().length > 0).map((t) => t.trim())
      : [];
    const quotesIn = Array.isArray(raw.key_quotes)
      ? raw.key_quotes.filter((q) => typeof q === 'string' && q.length > 0)
      : [];

    const quotes = quotesIn.filter((q) => text.includes(q));
    const dropped = quotesIn.length - quotes.length;
    if (dropped > 0) {
      console.log(`summarize: dropped ${dropped} non-verbatim quote(s)`);
    }

    const usage = response.usage || {};
    console.log(`summarize: tokens in=${usage.input_tokens ?? 0} out=${usage.output_tokens ?? 0}`);

    res.status(200).json({ summary, tags, key_quotes: quotes });
  } catch (err) {
    const msg = err?.message || 'summarization failed';
    console.error(`summarize: ${msg}`);
    res.status(500).json({ error: 'summarization failed' });
  }
}
