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
| 1 | **One fixed rendering. No scene gets its own treatment.** | One curve for every scene: no per-scene brightening (office −11 L\* at identical exposure, Hong Kong −29, night −13), no local tone mapping (shade stays shade: in a window-lit room, Chromagraph keeps **4.5 stops** between the lit back wall and the shaded side wall, while stock squeezes it to 1.75 and lifts the shaded wall from L\* 11 to 42). White balance apparently isn't neutralized either: tungsten at night comes out far warmer than stock. "Hardware consistency … with confidence": a fixed transform needs a known sensor, the way a film stock is a known emulsion. | Auto-HDR, scene detection, sky/skin masks, per-region white balance, "smart" brightening |
| 2 | **The light's color is the palette.** | Object color is restrained: daylight saturation tops out near chroma 22, and the office wood drops from 42 to 35. The *light's* color is kept and even deepened: cream daylight highlights, tungsten-lit walls going from chroma 24 → 62 and yellow → orange (82° → 46°), skies to teal (225°), the alley's back windows from blue to cyan (239° → 188°). The warmth follows the light: in that window-lit room, the sunlit wall and window go cream (b\* +2.7 → +14, +0.6 → +12), while the shaded wall and carpet stay neutral (b\* ≈ 0). A clear sky runs from grey-cyan at the top to cream at the horizon. Each picture gets a single color key set by its light, like a graded film, and nothing pops out digitally against it. | A fixed color scheme applied regardless of light (a stock "teal and orange" grade, a green/cream tint); saturation boosts on objects |
| 3 | **Expose for the light, and let darkness be dark.** | Highlights are protected (p99 L\* 87–91; Hong Kong's sky held just under paper white). Shadows fall to near-black in hard sun, and at night half the frame sits below L\* 10. Those shadows carry the light's warmth (red-brown, hue 32°) instead of being neutralized. Looking out a window, the room and its frame go dark while the view holds (the lake: stock clips 7.9% of the frame, Chromagraph 0%). Darkness is part of the composition: it's where the picture hides things. | Shadow lifting, night mode, brightening driven by noise reduction |
| 4 | **Highlights glow instead of clipping.** | A soft shoulder rolls highlights off into cream, and bright points bloom red. In daylight the halation is faint, because bright edges sit against mid tones. Against a night sky the same effect becomes the main event: the ring around each bulb gains 11.6× more red than blue (stock: 1.9×). One physical effect whose visibility depends on context. | A halation amount tuned per scene; hard white digital highlights |
| 5 | **Texture, not detail.** | 6 MP out of a 24 MP sensor, no sharpening (2.6× less high-frequency energy than stock), monochrome grain weighted to the mid tones. The image is meant to be looked at, not zoomed into. | Sharpening, 24 MP output, chroma noise, a uniform grain overlay |

### What this means for our build

- **Build the physics, not the palette.** Model a negative → print chain on scene-linear RAW (toe and shoulder, dye gamut, halation driven by actual light levels, grain that follows density) at a fixed white balance. Then tune it until daylight lands on the fingerprints below. If the model is right, the night look falls out with no extra rules. That's the test of whether we've captured the soul or just copied a color scheme.
- **White balance like film stock, not auto.** Our leading hypothesis is a fixed, near-daylight balance, which all eight scenes fit. The product question is whether to offer a deliberate tungsten choice, the way a cinematographer picks a stock or a filter.
- **Highlight-priority exposure** by default, with the user's exposure control as the creative dial.
- **Accept on behaviors, not only on numbers:**

  | Scene | What must happen |
  |---|---|
  | Night under warm lamps | Stays orange; blacks go black with a warm tint; bulbs bloom red |
  | Dim interior | As dim as the exposure says, not brightened |
  | Window-lit room | Light falls off across the room (4+ stops from the lit wall to the shade); the lit side warms, the shade stays neutral |
  | Looking out a window | The view holds under paper white; the room and frame go dark |
  | Backlit or hazy sky | Sky held just under paper white; the foreground falls |
  | Mixed light | The window stays cool against a warm room |
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

1. **Cream highlights (b\* +10.0 to +11.5), in all six daylight scenes.** This is the most stable number we have, so build it into the curve.
2. **A slight green in the upper mids (a\* −3.1 to −5.2), in all six daylight scenes.** This corrects an earlier note that called the green street-specific. The *shadow* cast is what varies by scene.
3. **Saturation tops out around chroma 22.** Saturated colors are compressed hard (the office wood frames: chroma 41.6 → 34.9, and the frame's p90 drops from 37.4 to 22). Near-neutral surfaces actually *gain* a little color from the cast (the white wall: 3.0 → 7.2). The result: everything shares one warm-olive palette, and nothing pops out digitally.
4. **No brightness normalization.** In the office, at identical exposure, Chromagraph is **11 L\* darker** than stock (white wall 63 → 49, ceiling 67 → 56, floor 77 → 62). In the bright street scene the two match. So stock brightens dim scenes and Chromagraph renders the exposure as it is: indoors looks like indoors. **Hong Kong goes furthest:** with a hazy, backlit sky in frame, Chromagraph puts the sky just under paper white (p95 L\* 87.7) and lets the city fall to median L\* 22, where stock sits at 51. Exposure is set by the brightest large area, not the average. The living room points the same way. (The app has an exposure control, so a shooter pulling it down can't be ruled out for a single shot.) Our pipeline should map exposure to brightness the same way for every scene, with no per-scene auto-brightening.
5. **Hue is preserved on saturated objects.** Wood stays at hue 68.6° in both. The look changes chroma and tone, not object hue. The exception is the bright-sky blue → teal shift, and that looks luminance-dependent: the dark blue chairs and cabinets in the office stayed at hue ~260–266°, in a small sample. Print film does the same. **The sky lands at ~225° wherever it starts** (street 266° → 225°, Toronto 272° → 226°), so it behaves as a target hue, not a fixed rotation. That fits a print-dye gamut more than a hue-shift knob. Toronto's deep-blue sky at L\* ~54 moves all the way, so the shift starts in the mid tones, not only in bright blues. A *pale, hazy* sky goes cream instead (Hong Kong): it has too little chroma to read as blue, so the cream highlight axis takes it.
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
| Glow ring around bulbs, red vs blue lift | 1.9× | **11.6×** |
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
- **Paper white ≈ L\* 91 in both shots.** It's consistent across scenes, so it's a property of the curve.

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
- **Mixed light isn't neutralized.** The daylit window frame stays cool grey-cyan against the warm interior. White balance is set gently, not corrected per region, and that mismatch adds to the mood.

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
- **Halation:** a red-brown fringe where bright surfaces meet dark ones (the truck roof edge, the van windshield frame). It's **subtle in daylight**: in the living room, even the lamp globes in front of the sunlit blind show only a faint warm bleed, not a glowing halo. At night, against black, the same effect becomes a strong red bloom (see Night). So drive it from actual light levels; don't fix its strength.
- **Vignette (likely):** both shots have darker, rounded corners. It's strongest in the living room's top-left and bottom corners and in the street's top-left. It could be deliberately added or lens shading left uncorrected from RAW; either way it belongs in the look. (The room's own lighting falls off too, so this is a visual call, not a measured one.)

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

The **targets** carry over: every number in "What holds across all three scenes" and the scorecard's target column. The color stages (hue, chroma ceiling, neutral axis), grain, halation and vignette carry over as starting points. The **tone anchors don't**: they're a stock-JPEG → look transfer, so they also undo Apple's curve. From RAW, the tone stage becomes a scene-linear → print curve, built as a negative → print model per the Intent section, that has a toe reaching L\* ~1–2 in deep shade (p1 1–7 depending on the scene), paper white of ~87–91, exposure placed for the highlights, a fixed white balance and no per-scene brightening. Check it against the behavior table under "The soul" as well as against these numbers.

## v2: the film model on RAW (`prototype/raw_look.py`)

The first version built to the principles instead of matched to colors. It renders an iPhone ProRAW DNG with one fixed chain. The only thing that adapts to the scene is exposure, which is metered for the highlights:

| Stage | v2 | Principle |
|---|---|---|
| White balance | Fixed D65 from the DNG's own daylight color matrix. Apple's auto white balance (stored in AnalogBalance) and its brightening (BaselineExposure, +3.5 EV on the first test) are ignored | 1 |
| Exposure | The 99.5th-percentile highlight goes 5 stops above mid grey, on the print's shoulder | 3 |
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

**Not validated yet:** there's no Chromagraph twin of a RAW file, so the scores are against the fingerprint ranges and the behavior table only. Night, tungsten, mixed light, halation against black and real skin from RAW are all untested. The skin and sky fits used display-referred stock colors as stand-ins for scene light. Running v2 on an already-processed HEIC isn't meaningful: it renders the portrait far too bright (cheek at L\* 75), because Apple has already compressed the scene's range.

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

- **Two full-resolution pairs (street, office), one unpaired interior and two downscaled X pairs (Toronto, Hong Kong)**, all daylight or mixed daylight. No skin tones, verified night or tungsten, or high ISO yet. A stock shot of the same living room would tell us how much the room was darkened and how far the white balance moved. More Chromagraph/stock pairs would firm all of this up.
- **Two compensations in look.py to revisit when the RAW pipeline is built** (from the 2026-10-29 QA pass):
  1. The shoulder anchors are bumped to offset the vignette. That holds for the street but depends on where the bright pixels sit. Fix: fit the anchors on the centre disc (r < 0.5, where the vignette gain is 1), or apply the vignette in linear light before the tone stage.
  2. The neutral-axis targets are set past the measured means to offset a partial pull. Fix: use the measured means and tune the pull weight instead. That would also be the place to revisit the 30% saturated-color tint. It causes the +15° dark-blue drift and lands skies 6–8° short of the measured 225° (street 217°, Toronto 220°).
- **Fixed white balance is a hypothesis from one night shot** (plus five daylight scenes that fit it). A Chromagraph/stock pair under known indoor tungsten would confirm it. So would one at sunset.
- **The v1 proxy can't express principles 1–3.** It starts from stock JPEGs, which have already been white-balanced, brightened and locally tone-mapped, so it can't un-neutralize a tungsten scene or re-darken a room. Only the night table's directions are usable from it. This is the main argument for building from RAW next.
- Framing differs slightly between the two shots, so the hue-family *shares* are partly affected by what's in frame. The tone, cast and per-family hue/chroma numbers are robust to that.
- **Next step:** iPhone RAW (DNG) files, so the recipe can run on scene-linear data the way the real app would. The best input is a DNG shot alongside a Chromagraph frame of the same scene: score.py can then score the RAW pipeline directly against the target.
