// M2: Vercel serverless function. Fetches a URL, runs Mozilla Readability,
// returns { title, text }. Dependencies declared in package.json.
export default function handler(_req, res) {
  res.status(501).json({ error: 'not implemented' });
}
