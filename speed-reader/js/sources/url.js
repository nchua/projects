export async function extractText(url) {
  const res = await fetch('/api/extract', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  });
  if (!res.ok) {
    const msg = await res.text().catch(() => '');
    throw new Error(`Extraction failed (${res.status}): ${msg || res.statusText}`);
  }
  const data = await res.json();
  return { title: data.title || '', text: data.text || '' };
}
