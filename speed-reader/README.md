# Speed Reader

Speed-reading web app using RSVP (rapid serial visual presentation) with an ORP-style bionic highlight — one word on screen at a time, one letter in red at the optimal recognition point.

Vanilla HTML + CSS + JS, no build step. A single Vercel serverless function handles article URL extraction.

## Run locally

```bash
cd speed-reader
python3 -m http.server 8000
# open http://localhost:8000
```

The URL-extraction feature requires the serverless function and won't work from a bare static server. Use `npx vercel dev` for full local parity.

## Controls

- **Space** — play / pause
- **Esc** — close reader
- **←/→** — seek by sentence
- **Shift + ←/→** — seek by word
- **Tap / click** — reveal controls; tap again resumes

## Sources

Paste text, upload `.pdf` / `.epub` / `.txt`, or paste a URL. URLs are fetched and cleaned via `@mozilla/readability` server-side.

## Deploy

Vercel picks up `api/extract.js` automatically. Root project directory is `speed-reader/`.

## Third-party notices

- PDF parsing: [pdf.js](https://github.com/mozilla/pdf.js) (Apache-2.0), loaded from jsDelivr at runtime.
- EPUB parsing: [JSZip](https://github.com/Stuk/jszip) (MIT), loaded from jsDelivr at runtime.
- Server-side extraction: [Mozilla Readability](https://github.com/mozilla/readability) (Apache-2.0) + [jsdom](https://github.com/jsdom/jsdom) (MIT).
