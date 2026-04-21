# Speed Reader

Speed-reading web app using RSVP (rapid serial visual presentation) with an ORP-style bionic highlight — one word on screen at a time, one letter in red at the optimal recognition point.

Vanilla HTML + CSS + JS, no build step. A single Vercel serverless function handles article URL extraction.

## Run locally

```bash
cd speed-reader
python3 -m http.server 8000
# open http://localhost:8000
```

URL article extraction requires the serverless function and will not work from a plain static server. For full local parity, use `npx vercel dev`.

## Controls

| Key | Action |
|---|---|
| Space | Play / pause |
| Esc | Close reader |
| ← / → | Seek by sentence |
| Shift + ← / → | Seek by word |
| Tap / click | Reveal controls; tap again resumes |

## Sources

- Paste text and press the play button (or ⌘/Ctrl+Enter in the textarea).
- Upload `.pdf`, `.epub`, `.txt`, or `.md` from the upload icon.
- Paste an `https://` URL — the article is fetched and cleaned server-side via Mozilla Readability.

## Library

Everything you read is saved locally to `localStorage`. Open the library from the dot in the bottom-left of the home screen to resume. Progress is auto-saved every 50 tokens.

## Privacy

No account. No analytics. No server-side storage — the only server-side code is a stateless URL-fetching proxy that never caches. Your reading history lives in your browser and nowhere else. On iOS Safari, localStorage is wiped after 7 days of inactivity (Intelligent Tracking Prevention); on desktop it persists until you clear site data.

## Deploy

Vercel picks up `api/extract.js` automatically. Point Vercel at the `speed-reader/` subdirectory.

## Third-party notices

- [pdf.js](https://github.com/mozilla/pdf.js) — Apache-2.0. Loaded from jsDelivr at runtime.
- [JSZip](https://github.com/Stuk/jszip) — MIT. Loaded from jsDelivr at runtime (EPUB parsing).
- [Mozilla Readability](https://github.com/mozilla/readability) — Apache-2.0. Server-side via `@mozilla/readability`.
- [jsdom](https://github.com/jsdom/jsdom) — MIT. Server-side.

## Milestones

- **M0** scaffold, black canvas, localStorage schema.
- **M1** RSVP reader with paste, WPM slider, tap-to-reveal controls.
- **M2** PDF / EPUB / URL ingestion, sentence/word seek, long-word splitter, progress bar.
- **M3** library with resume, auto-save, quota handling, onboarding sample, this README.
