# The Look — distilled from Chromagraph

What Chromagraph is trying to do, what it measurably does to a photo compared with the stock iPhone camera, and a recipe (v1) with a scorecard to check it. This is the target our own look starts from. The goal is to land in the same family, not to copy Yedlin's private transform.

## The soul: photograph the light, not a corrected scene

The color numbers further down (cream highlights, olive upper mids, teal skies) are symptoms. They describe what Chromagraph does to *daylight*. The night alley shows the same app producing an entirely different palette, and that's the point: underneath both there's one idea.

> **Commit to one physical rendering, the way a cinematographer's film camera does, and let the light in front of the lens decide how the picture feels.**

The stock iPhone treats every photo as a problem to solve. It lifts the shadows, holds back the sky, neutralizes the white balance, sharpens the edges and brightens the dim room, so that every part of every scene is legible. The result is accurate, and every scene ends up looking alike: evenly lit, neutral, flat. Chromagraph makes the opposite trade. A dim room stays dim, a tungsten alley turns orange, a backlit street keeps its sky and loses its shadows. Nothing is rescued.

That's a cinematographer's job: deciding where the light is, what's allowed to go dark and what color the night is. Rian Johnson didn't ask for a filter that looks like a movie. He asked for "the same image processing we use on our movies". That's a pipeline: the same thing happens to every frame, so where you stand, what you expose for and when you shoot are what make the picture. The app's only controls (color, exposure, grain, halation) are the controls a cinematographer has over a film stock.

### Five principles

| # | Principle | Evidence | What it rules out |
|---|---|---|---|
| 1 | **One fixed curve and palette. The only per-scene decisions are exposure, anchored on the highlights, and (in our build) how far the print is timed.** | One curve for every scene: the top is held (street and office both land at p95 80–81 / p99 88.5–88.8 whatever the stock's top was) and the mids fall where the scene's light puts them (office −4 to −15 L\* through L\* 20–85 at identical exposure, Hong Kong −29, night −13); no local tone mapping (shade stays shade: in a window-lit room, Chromagraph keeps **4.5 stops** between the lit back wall and the shaded side wall, while stock squeezes it to 1.75 and lifts the shaded wall from L\* 11 to 42). White balance apparently isn't neutralized either: tungsten at night comes out far warmer than stock. "Hardware consistency … with confidence": a fixed transform needs a known sensor, the way a film stock is a known emulsion. | Auto-HDR, scene detection, sky/skin masks, per-region white balance, "smart" brightening |
| 2 | **The light's color is the palette.** | Object color is restrained: a soft knee takes ~40 % out of anything above chroma 20 (office wood frame 49 → 31, floor 26 → 16), though reds keep chroma 40–55 where the scene has them (Toronto's billboard, the shopkeeper's sign). The *light's* color is kept and even deepened: cream daylight highlights, tungsten-lit walls going from chroma 24 → 62 and yellow → orange (82° → 46°), skies to teal (225° at L\* 45–55), the alley's back windows from blue to cyan (239° → 188°). Every hue moves with density: warm tones run from ~55° in the shadows to the cream axis (~88°) near paper white, blues from ~260° in the dark to ~200° in the light (see "Density"). The warmth follows the light: in that window-lit room, the sunlit wall and window go cream (b\* +2.7 → +14, +0.6 → +12), while the shaded wall and carpet stay neutral (b\* ≈ 0). A clear sky runs from grey-cyan at the top to cream at the horizon. Each picture gets a single color key set by its light, like a graded film, and nothing pops out digitally against it. | A fixed color scheme applied regardless of light (a stock "teal and orange" grade, a green/cream tint); saturation boosts on objects |
| 3 | **Expose for the light, and let darkness be dark.** | Highlights are protected (p99 L\* 87–91; Hong Kong's sky held just under paper white). Shadows fall to near-black in hard sun, and at night half the frame sits below L\* 10. Those shadows carry the light's warmth (red-brown, hue 32°) instead of being neutralized. Looking out a window, the room and its frame go dark while the view holds (the lake: stock clips 2.3 % of the frame by luminance, Chromagraph 0 %; the 7.9 % quoted earlier counted Display P3 → sRGB gamut clipping of foliage). Darkness is part of the composition: it's where the picture hides things. | Shadow lifting, night mode, brightening driven by noise reduction |
| 4 | **Highlights glow instead of clipping.** | A soft shoulder rolls highlights off into cream, and bright points bloom red. In daylight the halation is faint, because bright edges sit against mid tones. Against a night sky the same effect becomes the main event: the glow around each bulb is amber (G at 75–97 % of R, B at a fifth to a half; stock's is neutral) and tight, half gone by 3–4 px and at background by ~10 px at 2048 px wide. One physical effect whose visibility depends on context. | A halation amount tuned per scene; hard white digital highlights |
| 5 | **Texture, not detail.** | 6 MP from a 48 MP sensor (24 MP default output), no sharpening (2.6× less high-frequency energy than stock; 10–90 % edge rise 2.2–2.9 px with 0.2–0.3 % overshoot, against stock's 1.3–1.4 px and 8–15 %), monochrome grain weighted to the mid tones. The image is meant to be looked at, not zoomed into. | Sharpening, 24 MP output, chroma noise, a uniform grain overlay |

### What this means for our build

- **Build the physics, not the palette.** Model a negative → print chain on scene-linear RAW (toe and shoulder, dye gamut, halation driven by actual light levels, grain that follows density) at a fixed daylight balance, with the print timed part-way toward the light (see v2). Then tune it until daylight lands on the fingerprints below. If the model is right, the night look falls out with no extra rules. That's the test of whether we've captured the soul or just copied a color scheme.
- **White balance like a lab, not auto.** The negative is a fixed daylight stock (all eight scenes fit it), and the print is *timed*: the lab takes about half of the light's colour out, as a Bradford adaptation of the camera's as-shot white halfway to daylight, inside the film model. A daylight scene barely moves; a tungsten room keeps half its warmth instead of turning into a flat lemon wash, which is what a pure daylight print of a scene 3.5 stops off D65 does. The product question is whether the timing strength (or a deliberate tungsten stock) becomes a control, the way a cinematographer picks a stock or a filter.
- **Highlight-priority exposure** by default, with the user's exposure control as the creative dial.
- **Accept on behaviors, not only on numbers:**

  | Scene | What must happen |
  |---|---|
  | Night under warm lamps | Stays orange; blacks go black with a warm tint; bulbs bloom red |
  | Dim interior | As dim as the exposure says, not brightened |
  | Window-lit room | Light falls off across the room (4+ stops from the lit wall to the shade); the lit side warms, the shade stays neutral |
  | Looking out a window | The view holds under paper white; the room and frame go dark |
  | Backlit or hazy sky | Sky held just under paper white; the foreground falls |
  | Mixed light | Daylight through a window comes out neutral-to-cream (b\* +8 to +11), cooler only relative to the warm room; near paper white everything converges on cream |
  | Bright sun | Teal sky, cream highlights, deep shade near black |

## The mechanism: a film negative → print chain, not a generic "cinematic" filter

Rian Johnson's launch thread (2026-10-28): the app "shoots RAW, bypasses the iPhone's look processing and instead uses **the same image processing we use on our movies**." It was built by Steve Yedlin with color-science developer Eric Cameron. It's iPhone-only because "hardware consistency across Apple devices is part of what allows us to do this with confidence", and it's stills-only because video would only be possible on recent Pro iPhones. The user-facing tools are color, exposure, grain and halation.

Yedlin's public position (his "Display Prep" demo and "On Color Science" essays): the film look is a mathematical transform you can apply to digital capture. So the target is **film negative + print-stock emulation applied to scene-linear RAW**. Every trait measured below has a print-film explanation:

| Measured | Film-print explanation |
|---|---|
| Soft toe, shoulder below white | Print-stock density S-curve |
| Cream highlights (b\* +10 to +11.5 in all six daylight scenes) | Warm print highlights |
| Blue → teal sky | Print film's cyan dye renders blues toward cyan |
| Bright saturated colors toned down | Dye-gamut limits |
| Monochrome mid-weighted grain | Film grain |
| **Red** edge glow | Halation: light reflects off the film base back into the red-sensitive layer, which sits deepest in the film |

Implications for our build: model the chain (negative → print → display) and use this doc's measurements as targets, never Chromagraph's private math. Plan on per-device sensor color calibration, or at least the DNG's own color matrices; "iPhone only" suggests they calibrate per sensor. Reference material: Kodak's published 2383 print-film datasheet and Yedlin's essays.

## Reference pair

| | Chromagraph | Stock Camera |
|---|---|---|
| File | `refs/chromagraph_street.heic` | `refs/stock_street.heic` |
| Software | Chromagraph 1.3 | iOS 27.0.1 |
| Camera | iPhone 17 Pro main (24 mm eq.), f/1.78, ISO 80 | same, shot 21 s later |
| Shutter | 1/2445 s | 1/2299 s |
| Output | **2160×2880 (6.2 MP), sRGB, 8-bit HEIC** | 4284×5712 (24 MP), Display P3 |

A second matched pair: `refs/stock_office.heic` / `refs/chromagraph_office.heic` (side by side: `refs/office_stock-chromagraph.jpg`). iPhone 17 Pro, office interior with mixed daylight and indoor light, **identical exposure** (ISO 200, 1/83 s), taken 6 s apart.

An unpaired Chromagraph shot: `refs/chromagraph_livingroom.heic`. iPhone 14 Pro, ISO 80, 1/121 s, backlit living room with a sunlit window blind, also exported at **2880×2160 sRGB**. The output size is fixed regardless of device.

So Chromagraph exports at **6 MP in sRGB**, not 24 MP P3. Downsampling hides sensor noise and makes the added grain read as texture, not as noise. The exposure is the same as stock, which means the whole difference comes from processing.

**Two more pairs from X (added 2026-10-29),** posted by Chromagraph users: Toronto (Yonge–Dundas, sunny afternoon) and Hong Kong (Mid-Levels from a high floor, hazy sun with lens flare). They're saved as `refs/x_*.jpg`. Both are downscaled to 2048 px tall and recompressed, so **grain and fine texture can't be measured; tone and color can**. The stock files are Display P3; the Chromagraph files are sRGB at 3:4, matching the app's export.
- **Toronto** wasn't shot at the same moment: the big billboard changed, so frame-wide chroma and tone aren't comparable. The sky and the neutral casts are.
- **Hong Kong** looks near-simultaneous (same clouds, same flare), with slightly different framing.
- **Lake through a window** (`refs/x_stock_lake.jpg` / `refs/x_chromagraph_lake_edited.jpg`): bright autumn sun outside, a dark window frame inside. The Chromagraph file was posted captioned "edited", and it's Display P3 where the app exports sRGB, so it was re-saved and possibly adjusted after capture. Its fingerprints land inside the range of the other scenes, so any edit was light; still, treat it as the weakest of the daylight samples.
- **Window-lit room** (`refs/x_screenshot_interior_pair.jpg`): a screenshot of two iMessage thumbnails ("straight from the camera in the app" vs "normal iPhone camera"), taken moments apart (the TV frame changed) with slightly different framing. It's too small and processed for global stats, so only matched surfaces (lit wall, shaded wall, window, carpet) are used.
- **Night alley** (`refs/x_stock_alley_night.jpg` / `refs/x_chromagraph_alley_night.jpg`): fairy lights and warm lamps, a few cool windows at the back, same moment, slightly different crop. See "Night" below.

`refs/` is local-only (git-ignored): the photos are personal. Ask Nick for them.

## The look in one sentence

**A film print that records the light it was given:** exposed for the highlights, with shadows allowed to fall to near-black, highlights that glow and roll off instead of clipping, and the color of the light kept (cream daylight, orange tungsten, teal sky) while object colors stay restrained. Nothing is sharpened, monochrome grain sits on top, the corners darken, and bright points bloom red: faintly by day, strongly at night.

## Daylight fingerprints (six scenes)

These numbers hold across the six daylight and mixed-daylight scenes. They're what principles 1–5 do to daylight, so they're the **calibration targets** for the model, not the look itself. The night scene below shows the same model producing very different numbers.

| | Street | Living room | Office | Toronto (X) | Hong Kong (X) | Lake (X) | Stock (street / office / Toronto / HK / lake) |
|---|---|---|---|---|---|---|---|
| p1 L\* (black floor) | 7.1 | 4.0 | 5.7 | **1.2** | **1.6** | **0.5** | 1.1 / 3.9 / 1.1 / 5.1 / 0.8 |
| Below L\* 3 | 0.01% | 0.24% | — | **4.3%** | **4.8%** | 11.9% § | 2.4% / — / 3.5% / 0.3% / 10.1% |
| p99 L\* (paper white) | 88.5 | 91.0 | 88.8 | 87.0 | 89.7 | 86.1 | 95.6 / 91.7 / 95.2 / 94.6 / 98.4 |
| Clipped | 0% | 0% | 0% | 0% | 0% | 0% | 1.1% / 0.5% / 1.6% / 0.5% / **7.9%** |
| **Highlight b\* (L\* 85+)** | **+10.9** | **+10.9** | **+10.6** | **+10.2** | **+10.0** | **+11.5** | +1.1 / +0.5 / +4.9 / +0.8 / −3.5 |
| **Upper-mid a\* (L\* 60–85)** | **−4.6** | **−3.3** | **−4.7** | **−3.1** | **−4.6** | **−5.2** | −0.7 / −1.1 / −2.6 / −1.1 / 0.0 |
| **p90 chroma (ceiling)** | **22.5** | **16.8** | **22.0** | 23.7 ‡ | 13.7 | **20.8** | 25.2 / **37.4** / 45.0 / 20.6 / 34.7 |
| **Sky hue** | **225°** | — | — | **226°** | sky went cream | grey-cyan → cream | 266° / — / 272° / 260° / 278° |
| Median L\* vs stock | −1.4 | — | **−11.1** | −7.7 ‡ | **−28.8** | **−23.8** | |

‡ Toronto's two shots were taken at different moments (a different billboard is up), so these two cells are indicative only.
§ The lake is framed by a dark window frame in both shots, so its near-black share is mostly the scene.

1. **Cream highlights, but the table's +10.0 to +11.5 is a mask ceiling.** Those numbers are measured on near-neutrals (chroma < 12), and that mask caps b\* at ~12 while throwing away 50–94 % of the L\* 85–92 pixels, so it manufactures the stability. Unmasked, near-white (L\* 85–92) sits at b\* **+12 to +15** in every HEIC and X scene (street +12.3, office +14.2, living room +13.9, Toronto +14.7, tower +12.1) except Hong Kong's pale sky (+10.2), falling to ~+11 at L\* 92–94 and to +7 to +10 at the export's ceiling. Target the unmasked numbers: v2 (IMG_2725) is at +11.9 unmasked, 1–3 b\* short.
2. **A slight green in the upper mids (a\* −3.1 to −5.2), in all six daylight scenes.** This corrects an earlier note that called the green street-specific. The *shadow* cast is what varies by scene.
3. **A soft knee, not a ceiling.** The frame-wide p90 ≈ 22 is a statistic of mostly-neutral scenes. Aligned office blocks (stock chroma → Chromagraph median): 12–16 → 15, 20–25 → 15, 30–35 → 20, 40–50 → 26, 50–60 → 37, 60+ → 45: unity below ~15, about ×0.6 above 20, no hard stop. Per hue sector the street's p90/p99 chroma is red 18/39, orange 35/49, yellow 24/47, green 28/45, blue 24/32 (stock 12/26, 34/54, 23/52, 38/61, 35/58): greens −26 %, blues −31 %, warm hues unchanged. Reds stay saturated where the scene has them (Toronto's billboard p90/p99 49/56, the shopkeeper's sign 71/76). Near-neutral surfaces *gain* a little color from the cast (the white wall: 3.0 → 7.2). The result still reads as one warm-olive palette because most of a frame is near-neutral, not because objects are capped.
4. **No brightness normalization.** In the office, at identical exposure, Chromagraph is **11 L\* darker** than stock (white wall 63 → 49, ceiling 67 → 56, floor 77 → 62). In the bright street scene the two match. So stock brightens dim scenes and Chromagraph renders the exposure as it is: indoors looks like indoors. **Hong Kong goes furthest:** with a hazy, backlit sky in frame, Chromagraph puts the sky just under paper white (p95 L\* 87.7) and lets the city fall to median L\* 22, where stock sits at 51. Exposure is set by the brightest large area, not the average. The living room points the same way. (The app has an exposure control, so a shooter pulling it down can't be ruled out for a single shot.) Our pipeline should map exposure to brightness the same way for every scene, with no per-scene auto-brightening.
5. **Hue moves with density, for every family.** Blue hue is a smooth function of L\* in every Chromagraph file, the same curve each time (chroma-weighted, blue family, L\* 15–25 / 25–35 / 35–45 / 45–55 / 55–65 / 65–75): street 234/229/225/224/216/201°, Toronto 253/247/235/227/220/203°, office 260/237/225/213/202/195°, tower 265/258/232/214/202°, Hong Kong 251/238/227/212/205/203°; stock sits flat at 255–278°. "The sky lands at 225°" held only because the street and Toronto skies sit at L\* 45–55: the tower's deep sky at L\* 25 stays navy (258–265°), and Hong Kong's sky at L\* 85–90 goes cream because every hue converges on cream there, not because it was too pale to read as blue. Blue chroma ×0.5–0.75. Warm hues run the other way, from ~55–65° in the shadows to the cream axis (~88°) near white (see "Density"); the office wood goes *redder* by 5–10° (door frame 62 → 52°), so "hue preserved on objects" was a frame-wide family mean, not a behaviour.
6. **Neutrals drift toward yellow-olive.** The white wall's hue goes 67° → 94° and the ceiling's 77° → 86°.
7. **The black floor is a soft toe, not a fixed lift, and deep shade gets close to black.** p1 ranges from L\* 1.2 to 7.1. In both hard-sun X shots, ~4–5% of the frame sits below L\* 3, against 0.01% on the street and 0.24% in the living room. Recompression doesn't move blacks by that much. So the toe is soft, but deep shade reaches the print's maximum density at about L\* 1–2. An earlier version said blacks never crush; that came from the street scene alone.

## Night (the alley): the same model under tungsten

Stock vs Chromagraph, same moment:

| | Stock | **Chromagraph** |
|---|---|---|
| Median L\* | 21.6 | **8.8** (−13) |
| Below L\* 10 | 18% | **52%** |
| Shadow tint (L\* < 10) | neutral (a\* +1.7, b\* +0.4) | **red-brown (a\* +8.2, b\* +5.1, hue 32°)** |
| Lamp-lit walls, L\* 20–60 | hue 82°, chroma 24 | **hue 46°, chroma 62** |
| Lamp-lit walls, L\* 60–90 | hue 88°, chroma 23 | **hue 79°, chroma 65** |
| Cool back windows | hue 239° (blue) | **hue 188° (cyan)** |
| Glow around bulbs (linear lift over the background) | neutral, gone by 4 px | **amber: G 0.75–0.97 of R, B 0.2–0.45 of R; half gone by 3–4 px, at background by ~10 px (2048 px wide)** |
| p90 chroma / clipped | 30.8 / 0.74% | **68.0 / 0.82%** (the bulbs) |

- **The stock camera neutralizes the tungsten; Chromagraph keeps it.** That's what daylight-balanced film does under 2700–3000 K light. The hue also depends on density: darker lamp-lit surfaces go orange-red, and brighter ones yellow-orange. That's dye-layer behavior, not a tint.
- **The chroma ceiling is about objects, not light.** In daylight nothing tops chroma ~22. Here the light itself is saturated, so the image is too.
- **The darkness takes the light's color** instead of going neutral grey.
- **The cool windows go cyan,** the same pull as the daylight skies, which makes the warm/cool contrast of mixed light the image's whole palette.
- **Halation becomes the main feature** once bright points sit against black. Same effect as by day, different context.

Every part of this shot is what the model predicts. That's why it's treated as evidence, not as an outlier. It's one shot posted on X, so it's still worth confirming with a known pair.

## Measured traits from the street pair (CIELAB, both images sRGB at 2160×2880)

### 1. Tone: compressed at both ends, mids untouched

| L* percentile | p1 | p5 | p25 | p50 | p75 | p95 | p99 | clipped | crushed |
|---|---|---|---|---|---|---|---|---|---|
| Stock | 1.1 | 6.3 | 17.4 | 40.5 | 67.1 | 87.9 | 95.6 | 1.13% | 2.39% |
| **Chromagraph** | **7.1** | 10.2 | 19.0 | 39.1 | 60.9 | 80.2 | **88.5** | **0%** | **0.01%** |

- **Black floor near L\* 7 on this scene** (deep shade in other scenes goes to L\* 1–2; see point 7 above). Shadows look like the print's darkest density, not like digital zero. Yet p25 hardly moves, so shadows stay *dense*. Only the very bottom is lifted.
- **White ceiling near L\* 90.** The brightest whites (the white truck, the sky) sit about 7 L\* below display white and roll off smoothly. Nothing clips.
- **No local tone mapping.** The stock camera brightens shaded areas locally (the HDR look). Chromagraph keeps one global curve, so shade stays shade and the light has a direction. This is a big part of why it reads as "cinematic".
- **Exposure protects the highlights; shadows are left to fall** (living room). With a sunlit blind in frame, the room sits at median L\* 32. The window holds (p99 L\* 91, 0% clipped, lamp globes in front of the blind keep their shape), and the sofa and corners drop into murky shadow. A stock iPhone would have lifted the room.
- **The black floor is a soft toe, not a fixed lift.** The living room's p1 is L\* 4, against L\* 7 on the street, so deep scenes go lower. The toe flattens out around L\* 3–4 and almost nothing crushes (0.24%). The hard-sun X shots go lower still (point 7 above).
- **The top of the curve.** p99 sits at L\* 88–91 across scenes, and every app export shares one hard maximum: RGB (243, 236, 218) ≈ L\* 93.5, b\* +9 (two phones, two dates; only 0.03–0.22 % of pixels within 1 L\* of it), slightly less cream than the shoulder below it. v2's curve tops out at L\* 92 with b\* +10.7 and puts its p99.5 at L\* 87.5, so its brightest whites are ~1.7 L\* darker and ~2 b\* yellower than the exports'.

### 2. Color cast: neutral shadows, warm-yellow highlights, slight green throughout

Measured on near-neutral pixels (chroma < 12):

| L* band | Stock a* / b* | **Chromagraph a* / b*** |
|---|---|---|
| 5–30 (shadows) | −0.4 / +3.4 | **−2.4 / +0.0** |
| 30–60 (mids) | +0.1 / +5.1 | **−1.5 / +7.0** |
| 60–85 (upper mids) | −0.7 / +5.4 | **−4.6 / +6.2** |
| 85–100 (highlights) | −1.9 / +1.1 | **−0.2 / +10.9** |

The warmth grows with brightness: shadows come out neutral, highlights cream/yellow. That's the classic print-film split. The stock camera does the opposite and pulls its highlights back to neutral.

The living room (no stock pair) confirms which parts are baked in:

| L* band | Street a* / b* | Living room a* / b* |
|---|---|---|
| 5–30 | −2.4 / +0.0 | +1.2 / +5.2 |
| 30–60 | −1.5 / +7.0 | +0.2 / +7.2 |
| 60–85 | −4.6 / +6.2 | −3.3 / +8.6 |
| 85–100 | −0.2 / **+10.9** | +0.3 / **+10.9** |

- **The cream highlight (b\* ≈ +11) is identical across both scenes**, so it's part of the look's curve. It doesn't come from the white balance.
- Shadow color **varies by scene**, so it follows white balance. (An earlier version also called the upper-mid green scene-specific, but the office pair shows it in all three scenes. See "What holds across all three scenes".)
- **Mixed light isn't corrected per region, but daylight doesn't stay blue either.** In the office pair the daylit patches come out neutral-to-cream (sky through the door: stock a\*/b\* −14.8/−14.4 → −0.5/+10.7 at L\* 93; the daylit room beyond the door b\* −4 → +9); in the interior screenshot the pane sits at b\* +8 against the lit wall's +16.5. The window reads cool only relative to the warm room.

### 3. Hue and chroma: restrained, with two signature shifts

| Family | Stock hue / chroma | **Chromagraph hue / chroma** |
|---|---|---|
| Sky | 266° / 27.0 (blue) | **225° / 18.6 (teal-cyan, −31% chroma)** |
| Foliage | 111° / 27.3 | 112° / 24.5, and much of it pushed into the yellow-ochre band (that band: 8.9% → 16.6% of the frame) |
| Brick | 44° / 27.3 | 41° / 23.6, darker and denser |
| Overall p90 chroma | 25.2 | **22.5** |

- **Blue → teal** is the strongest single fingerprint, landing at ~225° from any starting hue (see point 5 above). The sky also goes paler and loses saturation toward the horizon.
- **Greens → yellow-olive/ochre.** Autumn leaves glow and the green leaves look more muted.
- High-chroma colors are tamed (p90 −11%), but the mids keep their color, so the image doesn't look washed out.

### 4. Texture: no sharpening, fine grain, halation

- **High-frequency energy is 5.4 vs 14.0** (8-bit high-pass std), **2.6× less than stock, even with grain added.** No sharpening halos, no HDR micro-contrast crunch. Edges are soft, like a lens rather than an edge filter.
- **Grain:** added grain, not sensor noise: it's plainly visible at ISO 80. Measured on flat patches in the living room (8-bit std after detrending):

  | Patch | L* | luma grain | chroma grain |
  |---|---|---|---|
  | Ceiling | 53 | 5.7 | 0.5 |
  | Left wall | 29 | 4.7 | 0.8 |
  | Dark corner | 23 | 4.2 | 0.6 |
  | Under sofa | 14 | 3.1 | 0.7 |
  | Blind (highlight) | 84 | 3.1 | 1.3 |

  So the grain is **monochrome** (luma 4–10× chroma), **peaks in the midtones** and tapers into both the shadows and the highlights. At 6 MP it is **fine, close to per-pixel**. Split by scale on flat walls (std of luma at < 1.5 px vs 1.5–4 px): 4.5–5.1 fine against only ~1.0 medium. (An earlier version said it clumps over 2–3 px; the scale split showed that was wrong, and v2's first grain came out visibly blotchy because of it.) Chroma noise is essentially gone, which fits a multi-frame merge that cleans the color before grain goes on. The app exposes this as Amplitude (1.25 in their screenshot), Grain Size (1.00) and "Force Pixel Size Grain".
- **Halation:** a red-brown fringe where bright surfaces meet dark ones (the truck roof edge, the van windshield frame). It's **subtle in daylight**: in the living room, even the lamp globes in front of the sunlit blind show only a faint warm bleed, not a glowing halo. At night, against black, the same effect becomes a strong amber bloom (see Night). Measured on the alley (2048 px wide): half gone by 3–4 px, at background by ~10 px (≈ 14 px at 2880); by day the street's warm fringe is Δb\* +6 at 1–2 px, +2 at 4–7 px, 0 beyond. v2's σ of 17 px at 2880 keeps a point source's glow above 85 % at 7 px where Chromagraph's has fallen to ~15 %: about 2× too wide for point sources (the (1, 0.22, 0) tint itself comes out amber after the print curve, so the colour is right). An earlier "11.6× more red than blue" could not be reproduced. So drive it from actual light levels; don't fix its strength.
- **Vignette: small.** Measured against stock on the tower pair (sky medians by radius), Toronto (a sky column) and the aligned office (residual after the tone transfer), the added darkening is within ±0.1 stop out to r 0.7 and about −0.1 stop at the corners. The living room's dark corners are the room's own light falloff. v1's 18 % and v2's 0.35 stop are ~3× too strong (medium confidence: tone-slope and sky-gradient confounds).

## v1 recipe

`prototype/look.py` applies the recipe to an already-processed sRGB image. That makes it a **proxy for checking the description**, not the real pipeline. Every parameter is a named constant at the top of the file.

| Stage | v1 setting | Why |
|---|---|---|
| Unsharpen | Gaussian σ 0.75 px | Removes the phone's sharpening |
| Tone | Monotone curve through the street pair's percentiles: L\* 0 → 4, 40.5 → 39.1, 87.9 → 80.8, 95.6 → 90.0, 100 → 92. The top three anchors sit 0.6–1.5 L\* above the measured 80.2 / 88.5 / 91 to make up for what the vignette and grain take off p99. | Soft toe, dense mids, paper-white shoulder |
| Hue | Blues above L\* 25–45 pulled to 225° (teal), wherever they start; greens −12° → yellow-olive; everything else held | Skies land at 225–226° from 266° and 272°; dark blues (office, L\* 15–23) and object hues are held |
| Chroma | Those blues ×0.5; soft ceiling: passes below 13, rolls off toward 23 | p90 ≈ 22 in every scene |
| Neutral axis | Low-chroma pixels pulled toward a\*(L) = 0 / −0.7 / **−5.8** / −0.2 and b\*(L) = 1.5 / 7.8 / 8.5 / **12.2** at L\* 15 / 45 / 72 / 92, harder in the highlights. These are set past the three-scene means (a\* −4.2, b\* 10.8) because the pull is partial. Saturated colors also get 30% of this axis as a small tint. | Cross-scene cream highlights and upper-mid green |
| Vignette | Up to 18% linear light loss (~17% at the exact corner), starting at half radius | Rounded dark corners |
| Halation | threshold 0.80, radius 6 px, tint (0.15, 0.05, 0) | Faint red-brown bleed |
| Grain | Monochrome, σ 1.0 px clumps, amplitude 0.018 at the midtone peak, ~55% near L\* 14 / 84, 35% at pure black / white | Matches the living-room grain profile |

### Scorecard (`prototype/score.py`, look applied to stock vs. the Chromagraph twin)

Tolerances (look − target): tone ±2 L\* (median ±3), clipped ±0.1 pp, cast ±2 b\* / ±1.5 a\*, p90 chroma ±2, sky hue ±10°, sky chroma ±3, grain ±0.6, high-pass ±1.0. A metric the target has but the look lost counts as a miss. score.py exits 1 on any miss.

| Metric | Street look / target | Office look / target |
|---|---|---|
| Black floor (p1 L\*) | 6.9 / 7.1 ✓ | 8.4 / 5.7 ✗ † |
| Median L\* | 38.7 / 39.1 ✓ | 50.6 / 44.7 ✗ † |
| Paper white (p99 L\*) | 88.0 / 88.5 ✓ | 82.5 / 88.8 ✗ † |
| Clipped | 0% / 0% ✓ | 0% / 0% ✓ |
| Highlight b\* | +10.9 / +10.9 ✓ | +9.2 / +10.6 ✓ |
| Upper-mid a\* | −4.3 / −4.6 ✓ | −3.8 / −4.7 ✓ |
| Mid b\* | +6.3 / +7.0 ✓ | +6.0 / +6.7 ✓ |
| p90 chroma | 22.1 / 22.5 ✓ | 23.9 / 22.0 ✓ |
| Sky / blue hue | 217° / 225° ✓ | 275° / 266° ✓ (dark blues: stock 260°, so the look drifts +15° where Chromagraph drifts +7°. This drift and the street's 8° undershoot both come from the saturated-color tint; see Caveats.) |
| Sky / blue chroma | 17.1 / 18.6 ✓ | 17.9 / 16.3 ✓ |
| Flat-area grain | 5.4 / 5.2 ✓ | 3.3 / 3.4 ✓ |
| High-pass energy | 5.4 / 5.4 ✓ | 2.5 / 3.9 ✗ † |

**20 of 24 within tolerance.** All four misses (†) are proxy limits, not gaps in the description:
- **Office tone.** Stock brightened this dim scene locally (median +11 L\* at identical exposure). A single curve applied to a stock JPEG can't map both scenes: the street needs 95.6 → 88.5 at the top, the office 91.7 → 88.8. From RAW, exposure maps to brightness the same way in every scene, and this disappears.
- **Office texture.** Stock barely sharpens at ISO 200 (high-pass 4.6 vs 14.0 on the street), so a fixed unsharpen over-softens it. RAW has no phone sharpening to remove.
- **Highlight headroom** (not scored). Stock clips 0.5–1.1% of the frame. Chromagraph's RAW plus bracketed merge keeps that detail; no curve can recover it.

**The X pairs, on the metrics they can support** (same tolerances; tone, grain and texture are excluded for the reasons above):

| Metric | Toronto look / target | Hong Kong look / target |
|---|---|---|
| Paper white (p99 L\*) | 86.7 / 87.0 ✓ | not scored: exposure (see point 4) |
| Clipped | 0% / 0% ✓ | 0% / 0% ✓ |
| Highlight b\* | +11.3 / +10.2 ✓ | +10.9 / +10.0 ✓ |
| Upper-mid a\* | −4.6 / −3.1 ✓ (by 0.02) | −5.5 / −4.6 ✓ |
| Mid b\* | +2.7 / +1.9 ✓ | +2.5 / +1.5 ✓ |
| p90 chroma | not scored: billboard | 12.4 / 13.7 ✓ |
| Sky hue | 220° / 226° ✓ | not scored: sky went cream |
| Sky chroma | 18.8 / 21.7 ✓ (by 0.03) | not scored |

**12 of 12 valid metrics within tolerance**, two of them right at the edge. Before the sky change (fixed −50° above L\* 40–65), Toronto's sky came out at 247° against 226°.

### What carries over to the RAW pipeline

The **targets** carry over: every number in "What holds across all three scenes" and the scorecard's target column. The color stages (hue, chroma ceiling, neutral axis), grain, halation and vignette carry over as starting points. The **tone anchors don't**: they're a stock-JPEG → look transfer, so they also undo Apple's curve. From RAW, the tone stage becomes a scene-linear → print curve, built as a negative → print model per the Intent section, that has a toe reaching L\* ~1–2 in deep shade (p1 1–7 depending on the scene), paper white of ~87–91, exposure placed for the highlights, a fixed daylight decode (the print timed part-way toward the light) and no per-scene brightening. Check it against the behavior table under "The soul" as well as against these numbers.

## Density: how colour moves with luminance (adversarial re-measurement, 2026-10-31)

An independent re-measurement of every reference (registered per-pixel transfers stock → Chromagraph where a pair exists, population statistics elsewhere; the same for Apple's preview → v2 on our own DNGs). Everything in the fingerprint tables reproduces; what changed is what the numbers mean. The rule the earlier sections state only for the night walls holds everywhere: **every hue converges on the cream axis (~88°) toward paper white and diverges in the shadows (warm tones redder, greens bluer, blues stay blue), and dense colours lose chroma while bright ones gain a little.**

**Warm hue by L\*** (hue 20–100°, chroma > 12, chroma-weighted; L\* bands 10–25 / 25–40 / 40–55 / 55–70 / 70–85 / 85+):

| Scene | 10–25 | 25–40 | 40–55 | 55–70 | 70–85 | 85+ |
|---|---|---|---|---|---|---|
| Street | 75 | 82 | 85 | 88 | 89 | 88 |
| Office (stock: 61 / 64 / 68 / 71 / 76 / 81) | 52 | 61 | 78 | 84 | 86 | 87 |
| Living room | 61 | 77 | 83 | 88 | 90 | 87 |
| Hong Kong | 58 | 72 | 78 | 86 | 89 | 89 |
| Tower | 66 | 69 | 78 | 86 | 87 | 88 |
| Pell sky | 54 | 56 | 67 | 74 | 84 | 87 |
| Shopkeeper | 41 | 44 | 50 | 53 | 86 | 89 |
| Alley, night (stock: 71 / 80 / 83 / 85 / 88 / 92) | 39 | 45 | 53 | 67 | 82 | 93 |
| **v2 IMG_2725** (window room) | **75** | **79** | **87** | **94** | **97** | **97** |
| **v2 IMG_2732** (tungsten hallway, timed 50 %) | **54** | **74** | **78** | **82** | **87** | **92** |

Chromagraph's warm tones run from ~55° in the shadows to ~88° near white and never pass ~90°. v2 has the swing but sits 10–25° too yellow through the lower mids (the hallway at L\* 25–55: 74–78° against the alley's 45–53°) and overshoots to 94–97° in the brights (the green upper-mid axis is the suspect). That, not the amount of cast, is why a timed tungsten room still reads lemon rather than orange. Relative to the stock render on the aligned office: orange −10 to −13° below L\* 40 and +10 to +15° at 40–80; yellows −14 / −6° dark, +7 to +9° light; greens −4 to −7° (bright greens also lose ~40 % chroma: the "greens → ochre" impression is mostly bright neutrals crossing the chroma-15 threshold because of the cast, plus ~10° of yellowing).

**Chroma by L\*** (pixels with chroma ≥ 15 in the stock image; ratio Chromagraph / stock on registered blocks; stock L\* bands < 25 / 25–45 / 45–65 / 65–85 / > 85):

| Pair | < 25 | 25–45 | 45–65 | 65–85 | > 85 |
|---|---|---|---|---|---|
| Office → Chromagraph | 0.60 | 0.60 | 0.81 | 1.10 | 1.13 |
| Street → Chromagraph (poorly registered) | 0.66 | 0.69 | 0.70 | 0.93 | 1.05 |
| Hong Kong → Chromagraph | — | 0.63 | 0.67 | 0.56 | 0.79 |
| Tower → Chromagraph (sky) | 0.76 | 0.68 | 0.47 | 0.60 | — |
| Alley → Chromagraph (night; the cast is kept) | 1.71 | 2.14 | 2.08 | 1.48 | — |
| **Apple → v2, IMG_2725** | **0.82** | **0.88** | **0.86** | **0.92** | **0.80** |
| **Apple → v2, IMG_2746** (tungsten, timed 50 %) | **1.60** | **1.51** | **1.51** | **2.10** | — |

Dense colours lose ~40 % of their chroma in daylight and bright ones gain ~10 %; v2 is flat (and because it also darkens the mids, its dark colours end up *more* saturated than Apple's per unit of L\*). Under tungsten v2's cast amplification against Apple's neutralised render (×1.5–2.1) is in the alley's range, so the print timing landed the *amount* of warmth; the hue profile above is what is missing. A prototype of the measured behaviour applied after the print in LCh (chroma ×0.70 below L\* 35 rising to ×1.20 above 75, warm hues −10° dark / +4° bright) is `refs/wb_experiments/density_experiment.jpg` (variant B; local only). It is a palette step; the physical version would be a chroma-with-density stage in the print model, re-exported and parity-tested like the timing was.

**Also measured, not previously in this file:**
- **Deep shade is cool by day.** L\* 5–10, all pixels, a\*/b\*: street −2.0/−3.2, office −0.6/−3.5, Toronto −0.2/−4.7, Hong Kong −2.1/−4.4, tower −0.8/−6.0 (stock Toronto +0.1/−3.0, Hong Kong +0.7/−4.6); the living room 0.0/+1.5; the night alley +4.6 to +8.2 / +5.1. Shadows are neither neutralised nor warmed: they keep the scene's blue. v2's axis is neutral at the bottom, which is right only if the scene supplies the blue (IMG_2725's shade comes out +4.9, an interior lit by bounce; check on a sunlit DNG).
- **Local contrast is lower.** Chromagraph / stock std of L\* over ~40 px neighbourhoods (aligned office): 0.31 at L\* 0–10, 0.67 at 10–20, 0.76–0.82 at 20–70, 0.86 at 80–90: ~20 % less mid-scale contrast than stock and 3× less in deep shadow (the toe swallows shadow texture). A large part of what reads as "softer".
- **Softness.** 10–90 % edge rise 2.2–2.9 px at 6 MP (about a 1 px Gaussian), 0.2–0.3 % overshoot. v2 (IMG_2725, 12 MP source) measures 1.72 px, sharper than any export: the Lanczos switch moved away from the reference.
- **Grain spectrum.** Flat-tile fine grain by L\* (8-bit, living room): 1.5 / 1.9 / 3.9 / 4.3 / 4.9 at L\* 0–8 … 35–45, 4.4 at 65–75, 3.0 at 75–85, 1.1 at 85–95; the office within 0.3 of that. The living room's and office's flat-tile power spectra are identical (energy shares 2 / 6 / 15 / 27 / 29 / 20 % from 0.02–0.06 up to 0.4–0.5 cycles/px); the street's extra medium-scale energy is scene texture, so don't fit grain on it. v2 puts 28–32 % above 0.4 c/px against 20 %: slightly too white (σ ≈ 0.55 px would match; the amplitude already does).
- **Clipping.** "Stock clips 7.9 %" on the lake (and 0.5–1.1 % elsewhere) counted Display P3 → sRGB gamut clipping of saturated foliage; by luminance (L\* ≥ 97) the lake's stock clips 2.3 %, the street 0.6 %, Toronto 1.1 %. Measure clipping on native values or by luminance.
- **Vignette** ~0.1 stop at the corners and **halation** amber and tight: see "Texture" and "Night".
- **Skin** (shopkeeper, the only sample): face in shade L\* 17, hue 47°, chroma 16.5; hand L\* 42, hue 49°, chroma 35.

**What this changes for v2** (targets, not yet applied; the user judges each on real photos first): the warm-hue-by-L\* profile (shadows toward 55–60°, nothing past ~90° in the brights), chroma falling with density, unmasked cream (+12 to +15 at L\* 85–92), the top of the curve (ceiling L\* 93.5 / b\* +9, p99.5 nearer +6 stops), halation σ about half, vignette about a third, grain σ 0.4 → ~0.55 px, and a touch of softening at 6 MP.

## v2: the film model on RAW (`prototype/raw_look.py`)

On the phone: the iPhone app "Print" (`ios/`, spec `APP_SPEC.md`) runs this exact model, with its constants exported from `raw_look.py` by `export_film.py`.

The first version built to the principles instead of matched to colors. It renders an iPhone ProRAW DNG with one fixed chain. Only two things adapt to the scene: exposure, metered for the highlights, and the print timing, which takes a fixed share of the light's colour out:

| Stage | v2 | Principle |
|---|---|---|
| White balance | The negative is decoded at a fixed D65 from the DNG's own daylight color matrix; Apple's brightening (BaselineExposure, +3.5 EV on the first test) is ignored. The print is then **timed**: the as-shot white (AsShotNeutral through the same matrix) is adapted `WHITE_BALANCE` = 50 % of the way to daylight in Bradford cone space, luminance kept, as one 3×3 folded into the dye crosstalk after metering. The window room (as-shot white 0.5 stop R/B off D65) moves ΔE 2; tungsten rooms (3.5–3.7 stops off) keep half their warmth | 1, 2 |
| Exposure | The 99.5th-percentile highlight goes 5 stops above mid grey, on the print's shoulder, but exposure is capped where the scene's log-average luminance sits at mid grey. Highlight metering only ever pulls exposure down (see the tungsten hallway below) | 3 |
| Dye crosstalk | Blue leaks 12% into green (teal skies), then a 15% saturation boost; rows sum to 1, so neutrals are untouched | 2 |
| Vignette, halation | In light, before the film. Halation comes from light more than 3 stops over mid grey, blurred and returned mostly into red, so it scales with how bright the source really is | 4 |
| Grain | Monochrome noise of 0.20 stops in the *negative*, nearly per-pixel (σ 0.4 px). The print curve's slope shapes it, so it peaks in the mids with no weighting rule | 5 |
| Print | One curve (stops → L\*: grey at 42, toe near L\* 1, paper white ~92) applied to each channel separately. Its neutral axis is the measured Chromagraph grey scale. Per-channel curves make color shift with density the way film does | 2, 4 |
| Output | 6 MP, Lanczos-resized in linear light, never sharpened. (A box filter at the non-integer 12 → 6 MP ratio softened fine detail, which the old coarse grain had been hiding.) A 48 MP ProRAW gives a crisper 6 MP than a 12 MP one | 5 |

**Calibration, without per-scene rules:**
- **Grain:** the midtone peak comes from the print curve's slope alone, which is a check that the physical model is right. Size and strength are fit to Chromagraph's flat walls by scale. At L\* 32 / 47, Chromagraph measures fine 4.5 / 5.1 and medium 1.0 / 1.1. 0.20 stops at σ 0.4 px gives fine ~4.6 / 5.0 and medium ~0.9 / 1.0. The first setting (0.23 stops at σ 0.9 px) matched the overall amount but put twice the energy into 2–4 px clumps (medium 2.2 vs 1.0), so it read as much grainier at phone size.
- **Color:** a small grid search over the dye crosstalk, the saturation and the mid warmth. Its targets were the street and Toronto stock skies, which Chromagraph renders at 225° and 226°, plus a skin color that should stay warm. Result: skies at 222° / 225°, skin at hue 51–56° with chroma ~22. The first version had used the full measured mid warmth (b\* +4.5) and some desaturation, which turned skin yellow-grey (hue 61°, chroma 18) and skies grey-cyan (200°, chroma 7). Mid warmth varied with white balance across scenes (b\* −1 to +7), so v2 keeps it light (+3). Only the cream paper white and the upper-mid green held everywhere.

**First DNG** (iPhone 17 Pro Max, ProRAW, ISO 64: a dim room looking out a window at daylight), compared with Apple's own rendering of the same file:

| | Apple | **v2** | Chromagraph range |
|---|---|---|---|
| Median L\* (the room) | 26.9 | **19.7** | — (the view holds, the room falls: behavior ✓) |
| p99 L\* | 96.2 | **86.6** | 86–91 |
| Clipped | 0.39% | **0%** | 0% |
| Highlight b\* | +0.2 | **+11.0** | +10.0 to +11.5 |
| Upper-mid a\* | +0.9 | **−2.7** | −3.1 to −5.2 (slightly weak) |
| p90 chroma | 26.5 | **25.2** | 14–24 (slightly high) |
| High-pass energy | 7.4 | **5.2** | 4.5–5.4 |
| Grain on a flat floor at L\* 32, fine / medium | — | **5.0 / 1.1** | 4.5 / 1.0 (Chromagraph wall, L\* 32) |

**Second DNG: tungsten hallway** (48 MP, warm ceiling lights, AnalogBalance 1.37 / 1 / 3.68). Highlight metering alone failed here: the brightest 0.5 % sat only 2.6 stops above the median (vs 7.1 in the window room), so pinning it to paper white overexposed the whole frame by ~2.4 stops (median L\* 63.6 vs Apple 54.4, black floor lifted to L\* 11). Overexposed tungsten then rode the per-channel shoulder into flat yellow (hue 81°, chroma 65). With the log-average cap: median 41.5 (Apple −13, the same darkening Chromagraph applied to the night alley), black floor 3.2, walls amber at hue ~72°, chroma ~50; the window room renders byte-identically because its highlight meter already sat 1.4 stops under the cap. Still open: Chromagraph's lamp-lit alley walls landed at hue 46° (more orange-red) — that was warm street lamps and fairy lights on brick (the stock render puts them at hue 80–99°, warm-white LED rather than sodium), so it isn't a like-for-like target, and the blue towel goes grey-violet, which is physically what a fixed daylight balance does to blue under warm light.

**Print timing (2026-10-31).** A pure daylight print turned every warm-indoor scene into the same flat lemon wash: this hallway and a lamp-lit living room (IMG_2745/2746: white dog, white sheets, white furniture) sat at chroma 60–70 and hue 80–87°, with the towel grey. The as-shot whites of those scenes are 3.5–3.7 stops (log2 R/B, in linear sRGB) off D65; the window room's is 0.5. With the print timed 50 % toward the as-shot white in Bradford space (luminance kept): hallway walls chroma 68 → 58, living-room whites chroma 64 → 32 (cream, not yellow), the towel blue again, median L\* +0.9; the window room's fingerprints move *into* range (highlight b\* 13.3 → 11.9, upper-mid a\* −5.2 → −4.7, p90 chroma 25.1 → 22.1; ΔE mean 2.2, L\* unchanged). Two other forms were tried first: a camera-space blend of the channel gains (similar at 50 %) and an sRGB-diagonal gain (under-corrects: still lemon at 50 %). Still open: Chromagraph's tungsten goes *orange* (46°) with density, and ours stays yellow in hue (85–89°) even with the chroma halved; 65 % timing is more neutral. A Chromagraph/ProRAW pair of the same tungsten scene would settle both the strength and the hue.

**Not validated yet:** there's no Chromagraph twin of a RAW file, so the scores are against the fingerprint ranges and the behavior table only. Night, mixed light, halation against black and real skin from RAW are all untested. The skin and sky fits used display-referred stock colors as stand-ins for scene light. Running v2 on an already-processed HEIC isn't meaningful: it renders the portrait far too bright (cheek at L\* 75), because Apple has already compressed the scene's range.

## Reproduce

Requires Python ≥ 3.10 with numpy and Pillow, plus macOS `sips`. Run from the repo root.

```bash
cd "Photo App/prototype"
# HEIC → sRGB PNG at 2160×2880. Stock HEICs are Display P3 and stored landscape with an orientation tag,
# which sips drops, so pass "rot" for those. Chromagraph exports are already upright sRGB.
to_srgb() { sips -s format png --matchTo "/System/Library/ColorSync/Profiles/sRGB Profile.icc" "$1" --out "$2" >/dev/null
  python3 -c "import sys; from PIL import Image; s=Image.open(sys.argv[1]); s=s.rotate(-90,expand=True) if sys.argv[2:]==['rot'] else s; s.resize((2160,2880),Image.LANCZOS).save(sys.argv[1])" "$2" ${3:-}; }
to_srgb ../refs/stock_street.heic /tmp/stock_street.png rot;  to_srgb ../refs/chromagraph_street.heic /tmp/cg_street.png
to_srgb ../refs/stock_office.heic /tmp/stock_office.png rot;  to_srgb ../refs/chromagraph_office.heic /tmp/cg_office.png
python3 score.py /tmp/stock_street.png /tmp/cg_street.png /tmp/stock_office.png /tmp/cg_office.png --out /tmp/look_out
# X pairs: the stock files are Display P3, so convert them to sRGB (no resize); the Chromagraph files are already sRGB
for n in toronto hongkong; do sips -s format png --matchTo "/System/Library/ColorSync/Profiles/sRGB Profile.icc" ../refs/x_stock_$n.jpg --out /tmp/x_stock_$n.png >/dev/null; done
python3 score.py /tmp/x_stock_toronto.png ../refs/x_chromagraph_toronto.jpg /tmp/x_stock_hongkong.png ../refs/x_chromagraph_hongkong.jpg
python3 measure.py /tmp/cg_street.png        # stats for any single image (any size ≥ ~70 px)
python3 look.py /tmp/stock_street.png /tmp/look_street.png   # apply the look to any sRGB image

# v2 needs rawpy: one-time setup of a local venv (git-ignored) from the repo root
python3 -m venv ../.venv && ../.venv/bin/pip install rawpy numpy pillow
../.venv/bin/python raw_look.py ~/Downloads/IMG_2725.DNG /tmp/IMG_2725_film.jpg   # any Apple ProRAW DNG
```

The resize to 2160×2880 is for the portrait pairs. Measure the landscape living-room shot (2880×2160) as-is: convert it with `sips` and skip the Python step.

## Caveats / what we still need

- **Two full-resolution pairs (street, office), one unpaired interior, four downscaled X pairs (Toronto, Hong Kong, lake, alley), the interior screenshot and six x2 posts.** The three x2 files first set aside as "a different look" (shopkeeper, pell_street, crosswalk) match the family on every signature (blue hue vs L\*, warm-hue climb, amber glow, cream near-whites, cool deep shadows; edge overshoot +2.5 / +2.3 / −1.0 % against the accepted Toronto +5.0 % and Hong Kong +4.1 %), so they are back in with an unknown-exposure/edits caveat; their L\* 95–96 plateaus are shared by the accepted alley. The shopkeeper is the one skin sample: face in shade L\* 17, hue 47°, chroma 16.5; hand L\* 42, hue 49°, chroma 35 (v2's skin fit of 51–56° / 22 is in range). No verified tungsten interior pair or high ISO yet. A stock shot of the same living room would tell us how much the room was darkened and how far the white balance moved. More Chromagraph/stock pairs would firm all of this up.
- **Two compensations in look.py to revisit when the RAW pipeline is built** (from the 2026-10-29 QA pass):
  1. The shoulder anchors are bumped to offset the vignette. That holds for the street but depends on where the bright pixels sit. Fix: fit the anchors on the centre disc (r < 0.5, where the vignette gain is 1), or apply the vignette in linear light before the tone stage.
  2. The neutral-axis targets are set past the measured means to offset a partial pull. Fix: use the measured means and tune the pull weight instead. That would also be the place to revisit the 30% saturated-color tint. It causes the +15° dark-blue drift and lands skies 6–8° short of the measured 225° (street 217°, Toronto 220°).
- **The print timing's strength (50 %) is a judgement from three indoor scenes against Apple's renders, not a measurement.** The fixed daylight negative itself is a hypothesis from one night shot plus five daylight scenes that fit it. A Chromagraph/stock pair under known indoor tungsten would set the strength and the hue (orange vs yellow). So would one at sunset.
- **The v1 proxy can't express principles 1–3.** It starts from stock JPEGs, which have already been white-balanced, brightened and locally tone-mapped, so it can't un-neutralize a tungsten scene or re-darken a room. Only the night table's directions are usable from it. This is the main argument for building from RAW next.
- Framing differs slightly between the two shots, so the hue-family *shares* are partly affected by what's in frame. The tone, cast and per-family hue/chroma numbers are robust to that.
- **Next step:** iPhone RAW (DNG) files, so the recipe can run on scene-linear data the way the real app would. The best input is a DNG shot alongside a Chromagraph frame of the same scene: score.py can then score the RAW pipeline directly against the target.
