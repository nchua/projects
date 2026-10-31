# Print — iPhone app spec (v0)

**Status:** M0–M4 built and on device · 2026-10-31 · rev 5 (rev 2 = adversarial review; rev 3 = metering cap; rev 4 = print timing; rev 5 = colour with density, §11) · working name "Print" (placeholder; renaming is a one-line change in `project.yml`)
**Goal:** run the v3 film model (`prototype/raw_look.py`, documented in `LOOK.md` → "v3") on the phone, on ProRAW photos already in the library, with output that matches the Python reference. No server, no network, no Claude/API at runtime.

**Before the execution session, the user shoots (ProRAW, 48 MP):** (1) daylight with blue sky, (2) indoor under warm lamps / tungsten — **done: `~/Downloads/IMG_2732.DNG`** (hallway under warm ceiling lights; the average-capped metering was added because of it), (3) a portrait. AirDrop the DNGs to `~/Downloads`. They are needed for M2's validation (§6) and never enter git.

---

## 1. What v0 is (and isn't)

**v0 does:**
1. Pick one or more photos from the library (system picker; no library permission needed to read).
2. For each ProRAW DNG: decode → film model → 6 MP JPEG, on device.
3. Show the results; tap one for full screen, press-and-hold to see Apple's own rendering (the DNG's embedded preview, SDR).
4. "Save to Photos" writes the renders (add-only permission) with the original's capture date and location.

**v0 does not (deliberately):**
- **No sliders or presets.** LOOK.md principle 1 is "one fixed rendering"; exposure metering and the print timing (a fixed share of the as-shot white, §5.2 step 2) are the only scene-adaptive steps. A Debug-only grain on/off toggle is allowed.
- **No camera capture** (v1). **No share extension** (v1 candidate). **No non-RAW input**: HEIC/JPEG items show "Not ProRAW (or edited in Photos) — skipped" (§9 D3). **No TestFlight, iPad, or App Store work.**
- **No network code and no analytics.** Nothing leaves the phone.

## 2. Ground truth and source of truth

| Thing | Source of truth | How the app gets it |
|---|---|---|
| Film model math | `prototype/raw_look.py` | Ported once to Swift (`FilmCore`); parity-tested against Python fixtures |
| Constants | `raw_look.py` module constants (M0 promotes every literal in `render()` to a named constant) | Exported to `film_params.json` by `prototype/export_film.py`; Swift loads it |
| Print curve (stops → linear RGB, 4096 × 3) | `raw_look.print_lut()` | Exported to `print_lut.bin` (little-endian float32, 4096 rows × 3 channels, row-major); `lut_sha256` in the JSON |
| Reference renders | `raw_look.py` on a DNG | `export_film.py --reference <dng>` writes stage-by-stage fixtures to `Photo App/fixtures/` (git-ignored) |

Tuning keeps happening in Python; a retune is "re-run the export, rebuild". **Swift may contain only these structural literals:** array shapes, the sRGB OETF constants (0.0031308, 12.92, 1.055, 0.055, 2.4), √2 in the vignette radius, 255 for quantisation, the 3×3 identity (print timing without a white), the D65 white (1, 1, 1) in linear sRGB that the timing adapts toward, and the DNG default AnalogBalance (1, 1, 1). Every other number (0.18 mid grey, luma weights, vignette 0.45/1.0/1.5, the halation downsample factor 4, blur truncation 3σ, the 1e-6 / 1e-7 floors, the LUT range, the softening σ, the density tables with their stops axis, the magenta axis and the size cap) comes from `film_params.json`.

`smoothstep(x, e0, e1)`: `t = clip((x − e0)/(e1 − e0), 0, 1); return t²(3 − 2t)`.

## 3. Facts established about the input (IMG_2725.DNG, iPhone 17 Pro Max, iOS 26.6.2)

- IFD0 is an 8-bit JPEG preview (4032×3024, Orientation 6). The raw is in SubIFD @5530: **LinearRaw** (Photometric 34892), 3 samples, **Compression 7 (lossless JPEG)**, 4032×3024, 504×504 tiles. No DefaultCrop.
- SubIFD **LinearizationTable** (1024 entries → 16 bit) is applied by rawpy/LibRaw (raw max 65535 = WhiteLevel; BlackLevel 0).
- **ProfileGainTableMap** (52525) present: Apple's local tone map. Python ignores it; the app disables it.
- **ProfileToneCurve** (50940, 257 points) present in IFD0: maps 0.18 → 0.127 and 0.01 → 0.0017 (−0.5 stop at mid grey, −2.6 stops in deep shadow). Python ignores it. If Core Image applies it even with boost 0, it shows up as a luminance-dependent slope in parity test C — **not** fixable with a matrix.
- **No OpcodeList1/2/3** (lens corrections baked in), **no HueSatMap, LookTable, ForwardMatrix, CameraCalibration.**
- Color: ColorMatrix1 (CalibrationIlluminant 17 = StdA) / ColorMatrix2 (21 = D65), AnalogBalance (2.49, 1, 1.93), AsShotNeutral (1,1,1), BaselineExposure +3.47 (a pure ×2^3.47 in Core Image; irrelevant because we meter). At a forced D65 neutral, DNG matrix interpolation puts all weight on ColorMatrix2, same as Python.
- Python decode (`read_dng`): `cam → XYZ` via `inv(diag(AnalogBalance) · ColorMatrix2)`, then XYZ → linear sRGB (the D65 rescale on line 80 is exactly ×1 for this file). A D65 neutral comes out R=G=B.
- `CIRAWFilter` on this file (measured on macOS 26.6): output extent 3024×4032 (orientation applied by default), unclamped with EDR 0 (max 13.8, 8.9 % of pixels > 1, min −0.22), deterministic across runs, decoder versions 7.dng and 8.dng identical.

## 4. Architecture

```
Photo App/
  APP_SPEC.md                       this file
  prototype/raw_look.py             M0 refactor; output bit-identical
  prototype/export_film.py          NEW: params + LUT export; --reference writes fixtures
  prototype/compare.py              NEW: parity / look metrics between two renders
  fixtures/                         NEW, git-ignored: per-DNG reference + Swift outputs
  ios/
    project.yml                     xcodegen; app target "Print"; local package FilmCore
    scripts/parity.sh               runs `swift test`, then compare.py on what it wrote
    Print/                          SwiftUI app (picker, list, viewer, save)
    FilmCore/                       local Swift package, no UIKit
      Package.swift                 swift-tools-version 6.2; platforms .iOS(.v26), .macOS(.v26);
                                    swiftLanguageModes [.v5]; resources: .copy for both files below
      Sources/FilmCore/
        Resources/film_params.json  generated, committed
        Resources/print_lut.bin     generated, committed (48 KB, not personal data)
        FilmParams.swift            Codable mirror of film_params.json
        DNGProbe.swift              minimal TIFF reader: SubIFD Photometric == 34892
        Decode.swift                DNG URL → upright linear sRGB at 6 MP (Core Image)
        FilmModel.swift             linear 6 MP → display sRGB (Accelerate, CPU, Float32)
        Matrix3.swift               3×3 helpers in Double (as-shot white, print timing)
        Filters.swift               Pillow-exact BOX/BILINEAR resize and Gaussian blur
        Grain.swift                 seeded Gaussian field
        Encode.swift                → JPEG + metadata (ImageIO)
      Tests/FilmCoreTests/          run on the Mac with `swift test`
```

- **Core Image only for decode + resize** (Apple's RAW engine is the point). **The film model on the CPU with Accelerate, planar Float32** — a near line-by-line port, deterministic, testable on the Mac. Float32 throughout is sufficient (review measured a float32 port at 99.999 % exact 8-bit pixels vs numpy's mixed float32/64).
- **FilmCore has no UIKit**, so `swift test` runs on macOS 26 (CIRAWFilter works there on this DNG: decode + 6 MP render in 0.16–0.33 s).
- **xcodegen:** `packages: { FilmCore: { path: FilmCore } }` and `dependencies: [ { package: FilmCore } ]`; resources via `Bundle.module`.
- **Project settings:** iOS 26.0, `TARGETED_DEVICE_FAMILY=1`, portrait only (`INFOPLIST_KEY_UISupportedInterfaceOrientations_iPhone`), `INFOPLIST_KEY_UILaunchScreen_Generation: YES` (or the app runs letterboxed), Swift 5 mode, team `D69T4MH7XQ`, bundle id `com.nickchua.print`, automatic signing, `INFOPLIST_KEY_NSPhotoLibraryAddUsageDescription`.

## 5. Pipeline spec (the contract FilmCore implements)

Buffers: planar Float32, row-major H × W, linear sRGB primaries, D65. Notation follows `raw_look.py`.

### 5.1 Decode (`Decode.swift`)

1. **Gate.** `CGImageSource` type is `com.adobe.raw-image`, Make == `Apple`, **and** `DNGProbe` finds a SubIFD with Photometric 34892 (ImageIO's TIFF dictionary only describes the IFD0 preview, so a Bayer DNG would otherwise pass). Else → "Not ProRAW".
2. **`CIRAWFilter(imageURL:)`, every setting explicit** (several defaults vary per image/OS):
   - `decoderVersion = "8.dng"` (pinned so Mac tests, device and future iOS agree; fail loudly if not in `supportedDecoderVersions`).
   - `neutralChromaticity = (0.3127, 0.3290)` — D65. Do **not** use temperature/tint: 6504 K / tint 0 reads back as (0.3135, 0.3235), not D65.
   - `boostAmount = 0`, `boostShadowAmount = 0`, `localToneMapAmount = 0`, `extendedDynamicRangeAmount = 0`, `isGamutMappingEnabled = false`, `isHighlightRecoveryEnabled = false` (default is on and changes highlights; rawpy does no recovery), `shadowBias = 0`.
   - `sharpnessAmount = 0`, `contrastAmount = 0`, `detailAmount = 0`, `luminanceNoiseReductionAmount = 0`, `colorNoiseReductionAmount = 0`, `moireReductionAmount = 0`, `exposure = 0`, `isDraftModeEnabled = false`, `scaleFactor = 1`. `baselineExposure` untouched.
   - Orientation: the filter's default (applies the file's). Where an `is…Supported` flag exists and is false, log it and record it in §11; boost/EDR/gamut/neutral have no such flag.
3. **Resize** to long side `OUT_LONG_SIDE` with `CILanczosScaleTransform` in the linear working space; target `(round(w·s), round(h·s))` with s = 2880 / max(w, h). **v0 asserts both output dimensions are divisible by 4** (4:3, 3:2, 16:9, 1:1 at 2880 all are) so the halation downsample is an exact 4×4 mean (§5.2 step 4).
4. **Render in horizontal strips** (16 strips per 12 MP of source, so 64 for 48 MP — measured on the Mac, see §11) with one shared `CIContext(options: [.workingColorSpace: extendedLinearSRGB, .workingFormat: CIFormat.RGBAf, .cacheIntermediates: false])` into one RGBAf bitmap (`extendedLinearSRGB`), then de-interleave to planar R, G, B. A single full-frame render of a 12 MP file peaks at ~810 MB footprint; 8 strips peak at ~520 MB with identical values. Negative values are kept (Python keeps them until the crosstalk clamp).
5. **Comparison image:** `filter.previewImage` (embedded Apple JPEG, 4032×3024, **not** rotated: apply the file orientation), scaled to 2880 and encoded as JPEG now — the DNG is deleted after the item.
6. Also return the source metadata (`CGImageSourceCopyPropertiesAtIndex`) for Encode. After the item: drop the filter, `ctx.clearCaches()`.
7. **As-shot white** (`DecodedPhoto.white`, rev 4): `DNGProbe.colorTags` reads IFD0's ColorMatrix2 (50722), AnalogBalance (50727, identity if absent) and AsShotNeutral (50728) as rationals (`Double(num) / Double(den)`, as Pillow gives numpy); `white = XYZ_TO_SRGB · inv(diag(AnalogBalance) · ColorMatrix2) · AsShotNeutral`, normalised to G = 1 (`raw_look.as_shot_white`). nil without AsShotNeutral or with degenerate tags, and the print is then timed for daylight alone. Core Image's own as-shot estimate (the default `neutralChromaticity`) is **not** used: it interpolates ColorMatrix1/2 and sits up to 0.1 stop of blue away from the ColorMatrix2-only white, so the decode stays pinned at D65 and the white is a tag computation identical on both sides.

### 5.2 Film model (`FilmModel.swift`) — port of `render()` after its resize

Inputs: planar linear RGB (H×W), `FilmParams`, LUT, and a seed or an injected noise field (tests).

0. **Soften** (rev 5, `raw_look.soften`). Each plane through Python's `blur(plane, SOFTEN_SIGMA)` — the step 4 Gaussian: radius max(1, int(3σ)) = 1 at σ 0.55, kernel [0.1385, 0.7231, 0.1385] normalised to 1, edge-replicate padding, vertical pass then horizontal, Double between passes, Float out — before anything is metered.
1. **Meter.** `lum = Σ lumaᵢ · cᵢ`. `p = percentile(lum, HIGHLIGHT_PERCENTILE)` with numpy's default *linear* method: with N pixels, rank `q = (N − 1) · P/100`; select order statistics ⌊q⌋ and ⌊q⌋+1 (quickselect on a copy, both needed) and interpolate with t = q − ⌊q⌋. No histogram approximation. `k_highlight = MID_GREY · 2^HIGHLIGHT_STOPS / max(p, 1e-6)`. `k_average = MID_GREY · 2^AVERAGE_STOPS / exp(mean(ln(max(lum, 1e-6))))`: the log terms, their mean (6 M terms), the exp and the division all in Double on both sides, rounded to float32 once like `k_highlight` (rev 4: numpy's float32 log and pairwise sum are not reproducible bit for bit, and a 1-ulp k moves near-cancelling pixels). `k = min(k_highlight, k_average)`; multiply all channels by k. `meta.json` records both k values and which one won.
2. **Print timing and crosstalk** (rev 4). `m = CROSSTALK · print_timing(white)` in Double, where `print_timing` is the identity when `white` is nil and otherwise adapts `white` `WHITE_BALANCE` of the way to the D65 white (1, 1, 1) in Bradford cone space, keeping its luminance: `to_lms = BRADFORD · inv(XYZ_TO_SRGB)`; identity too when `to_lms · white` isn't all positive and finite; `gain = ((to_lms · 1) / (to_lms · white))^WHITE_BALANCE`; `a = (inv(to_lms) · diag(gain)) · to_lms`; `print_timing = a · (luma · white) / (luma · (a · white))`. Swift computes `to_lms`, its inverse and daylight's cone responses once in `FilmModel.init` (a singular bundled matrix throws `invalidParams` at load); 3×3 inverses by cofactors (they differ from numpy's LU inverse by ~1e-16 relative, 3e-11 stop at the worst pixel). `rgb ← m · rgb`, then clamp each channel to `≥ CLAMP_FLOOR` (1e-7).
3. **Vignette.** For **integer** pixel indices x, y (as `np.ogrid`; not pixel centres): `r = hypot((x − W/2)/(W/2), (y − H/2)/(H/2)) / √2`; `gain = 2^(−VIGNETTE_STOPS · smoothstep(r, VIGNETTE_START, VIGNETTE_END)^VIGNETTE_POWER)`. Gain map precomputed per size.
4. **Halation.** `lum` of the vignetted rgb; `excess = max(lum − MID_GREY · 2^HALATION_STOPS, 0)`; `glow = wide_blur(excess, HALATION_SIGMA · max(H, W))`; `rgb += HALATION_STRENGTH · glow · HALATION_TINT`.
   `wide_blur(x, σ)`: (a) **4×4 mean** to (W/4, H/4) (exact for PIL BOX at divisible sizes; PIL BOX is *not* area-weighted otherwise — each output averages the source pixels whose centres fall in [c − s/2, c + s/2) — which v0 avoids via the §5.1 assert); (b) separable Gaussian, σ′ = σ/4, radius `max(1, int(3σ′))` (12 at 2880), kernel normalised to 1, **edge-replicate** padding; (c) bilinear upsample to (W, H) with PIL's convention `src = (dst + 0.5) · (in/out) − 0.5`, clamped to [0, in − 1]. Not align-corners.
5. **Negative.** `stops = log2(rgb / MID_GREY)` per channel and `lum_stops = log2((rgb · luma) / MID_GREY)`, both from the post-halation rgb. **Colour moves with density** (rev 5, `raw_look.density`), in Double (Python's stops are already float64 there; Swift's are float32 `log2` results, so the sides differ by one float32 ulp at most) and back to float32: `d = stops − lum_stops` (the colour's departure from its luminance), `size = min(‖d‖, DENSITY_CHROMA_CAP)` with `‖d‖² = (d₀² + d₁²) + d₂²` (the shift's size law saturates at 4 stops of colour: a channel at the clamp floor, 21 stops down, and a saturated light source both swing as a 4-stop colour), `shift = size · (interp(lum_stops, DENSITY_STOPS, SHIFT_DENSE) + interp(lum_stops, DENSITY_STOPS, SHIFT_SATURATED) · size)`, `gain = interp(lum_stops, DENSITY_STOPS, CHROMA_GAIN)`, `stops ← lum_stops + gain · (d − shift · GREEN_MAGENTA)`, in exactly that order. `interp` is np.interp on a short increasing axis: clamped outside, exact at the knots, `slope · (x − xⱼ) + yⱼ` between. Neutrals (d = 0) never move; the pivot is the luminance, not the channel mean, so a channel at the clamp floor can't drag the pixel's density (it did: dark walls with hard-edged blotches). `stops_pregrain.f32` is this result.
   **Grain.** Noise n (H×W): injected (already normalised by Python), or `Grain.field(seed, H, W)`: i.i.d. N(0,1) from a counter-based hash of (seed, x, y) → two uniforms → Box–Muller; blurred with Python's `blur(…, GRAIN_SIGMA)` kernel (σ 0.55 → radius 1 → [0.1385, 0.7231, 0.1385], edge padding); divided by the analytic std Σkᵢ² = 0.56118 (computed from the kernel, not hard-coded; the test derives the expected lag-1 autocorrelation Σkᵢkᵢ₊₁ / Σkᵢ² = 0.357 from the kernel too). `stops += GRAIN_STOPS · n`, same n on all channels.
   Seed: FNV-1a 64 of (file name + DateTimeOriginal), so re-rendering a photo is deterministic and photos differ.
6. **Print.** Per channel `lin = interp(stops, linspace(LUT_MIN, LUT_MAX, LUT_SIZE), lut[:, c])`, clamped at the ends (np.interp semantics).
7. **Encode transfer.** sRGB OETF with clip to [0, 1] (Python's last line). `render` returns this float image; quantisation `round(x · 255)` happens in Encode. Tests compare the float image.

### 5.3 Encode (`Encode.swift`)

- 8-bit RGB `CGImage` tagged sRGB, upright (Orientation 1). `CGImageDestination` JPEG quality 0.95. No gain map / HDR in v0.
- Copy from the source when present: `DateTimeOriginal`, `SubsecTimeOriginal`, `OffsetTimeOriginal` (present in IMG_2725 and IMG_2732: −07:00), the GPS dictionary including `DateStamp`/`TimeStamp`, Make/Model, lens model, ISO, exposure time, f-number, focal length. Set `Software = "Print <version>"`. Drop thumbnails, MakerNote, orientation and pixel-dimension tags.
- **Also set `creationDate` and `location` on the `PHAssetCreationRequest`** (don't rely on Photos reading EXIF). Capture time = DateTimeOriginal + SubsecTimeOriginal in OffsetTimeOriginal; with no offset, the zone inferred from the GPS UTC stamp (rounded to 15 min), else the device time zone. Not the GPS stamp itself: it is whole seconds and can lag the shutter (IMG_2725: GPS 23:58:00 vs shutter 23:58:01.384). Verified in the simulator: the saved render lands at exactly the original's time and location with add-only access.

## 6. Milestones (in order; each ends green before the next)

### M0 — Python prep (no behaviour change)
- Promote every literal in `render()` to a named module constant (§2 list). Refactor `render()` into `prepare(rgb) → rgb6mp` (resize only), `grain_field(h, w, seed) → normalised noise` and `film(rgb6mp, noise) → float sRGB`, keeping `render()` as a wrapper. **Acceptance:** `np.array_equal` of `render()`'s float output before/after on IMG_2725, and the saved JPEG's sha256 unchanged.
- `export_film.py` default: write `FilmCore/Sources/FilmCore/Resources/{film_params.json, print_lut.bin}`. JSON: `version`, every §5.2 constant (final `CROSSTALK` 3×3, luma weights, mid grey, vignette, halation incl. downsample factor and truncation, grain, floors; from rev 4 `white_balance`, `bradford`, `xyz_to_srgb`; from rev 5 (version 3) `soften_sigma`, `density_stops`, `chroma_gain`, `shift_dense`, `shift_saturated`, `green_magenta`, `density_chroma_cap`), `lut_min/max/size`, `lut_sha256`.
- `export_film.py --reference DNG` → `fixtures/<stem>/`. All `.f32` files are **little-endian float32, planar, channel order R,G,B, row-major**:
  `linear6mp.f32` (after `prepare`, before softening and metering, includes negatives) · `noise.f32` (normalised) · `glow.f32` · `stops_pregrain.f32` (after the density stage) · `out_nograin.f32` and `out.f32` (float sRGB before quantisation) · `out.png` (8-bit) · `meta.json`: H, W, seed, N, percentile rank q, p, k, `white` (the as-shot white, or null), numpy/Pillow/rawpy versions, `lut_sha256`.
- `.gitignore`: add `fixtures/`.
- `compare.py A B [--mask-from A]` — defines the metrics once, used by every gate:
  - **pixel:** max and mean |Δ| on the float sRGB (units of 1/65535) and on 8-bit; % exact / within 1 level.
  - **look:** L* p1/p50/p99 Δ; signed mean Δa*, Δb* over all pixels; ΔE76 mean/p95; neutral-highlight b* over the **reference's** mask (C* < 12, L* ≥ 85) with its pixel count (need ≥ 2000, else "n/a").
  - **grain bands** (LOOK.md's definition, written into code here): luma, fine = std(luma − blur σ1.5), medium = std(blur σ1.5 − blur σ4), reported on the 10th-percentile-flat 64 px tiles, 8-bit units.
  - **linear mode** (`--linear`) for test C (§M2).
  Exit 1 over the thresholds passed on the command line.

### M1 — FilmCore: model port, host parity (no decode)
- `FilmParams` decodes the JSON; test asserts `sha256(print_lut.bin) == lut_sha256` and that every key is used.
- `FilmModel.render` per §5.2. The Swift tests write their outputs (same formats) to `fixtures/<stem>/swift/`; `ios/scripts/parity.sh` runs `swift test` then `compare.py` — the metrics live only in Python.
- **Test A (injected noise, exact path):** vs `out.png`: ≥ 99.99 % of pixels exact, max ≤ 1 level. Stage checks: `glow` and `stops_pregrain` max |Δ| ≤ 1e-4 relative; k within 1e-6 relative.
- **Test B (no grain, float):** Swift float output vs `out_nograin.f32`: max |Δ| ≤ 1/65535. (Review: centre-offset vignette = 4.3 units and align-corners upsample = 485 units, so both loose-port bugs fail here; the old "99.9 % within 1 level" let them pass.)
- **Grain unit test:** app generator on a flat field: |mean| < 0.01, std within 1 % of 1, lag-1 autocorrelation Σkᵢkᵢ₊₁ / Σkᵢ² of the exported kernel ± 0.005 (0.357 at σ 0.55). On IMG_2725 with the app's own noise: fine/medium grain bands within ±10 % of Python's `out.png`.
- Fixture tests `XCTSkip` when fixtures are absent (env `PRINT_FIXTURES_DIR`, default `<repo>/Photo App/fixtures`).

### M2 — Decode parity (host, `swift test` on macOS)
DNGs from env `PRINT_DNG_DIR` (default `~/Downloads`): IMG_2725 plus the three shot for this (§ top). Python fixtures are generated for each.
- **Test C (linear, `compare.py --linear`):**
  - Exposure: ratio of the two metering k values within 0.02 stop (reported separately so a metering difference doesn't masquerade as a tone error).
  - Normalise each side by its own median luminance over midtone pixels (reference luminance within ±2 stops of mid grey), not by k.
  - Mask: both sides > MID_GREY · 2⁻⁶ in every channel after normalising (negatives and deep noise excluded).
  - Geometry: same W×H; sub-pixel registration of luminance (phase correlation) |offset| < 0.1 px in x and y.
  - Colour: on 8× box-downsampled images, **signed** per-channel median log2 ratio within ±0.02 stop; p95 |log2 ratio| ≤ 0.08 stop.
  - Tone: slope of the per-pixel log2 luminance ratio vs reference log2 luminance (least squares, masked) |slope| ≤ 0.01. A real slope here = Core Image applying a tone curve (ProfileToneCurve, §3) → investigate settings; **never** patch with a matrix.
- **Test D (end to end, no grain, float sRGB):** Swift decode + model vs Python `out_nograin.f32`: L* p50 |Δ| ≤ 0.5, p1/p99 ≤ 1.0; signed mean Δa*, Δb* ≤ 0.3; ΔE76 mean ≤ 0.6, p95 ≤ 2.0; neutral-highlight b* within 0.5 (if the mask has ≥ 2000 px).
- **If C/D fail on colour only** (flat signed offsets, no tone slope, geometry fine): the one allowed fix is a constant 3×3 applied after decode, fitted by least squares on blurred, normalised, unclipped midtones of the **daylight** DNGs, then **validated on the tungsten DNG** (an illuminant-dependent error never shows on a second daylight frame). It goes in `film_params.json` as `decode_correction`, with the fit residuals in §11. Python stays the reference. If tone or geometry fails: stop and investigate.
- If the extra DNGs aren't available yet, M2 runs on IMG_2725 alone: a colour failure is recorded as `XCTExpectFailure` with the numbers, and M3 proceeds (M3 doesn't depend on M2's pass).

### M3 — App shell (simulator)
- `xcodegen generate`; builds with zero warnings in our code.
- Picker: `PHPickerConfiguration(photoLibrary: .shared())`, `filter = .images`, `selectionLimit = 0`, **`preferredAssetRepresentationMode = .current`**.
- Loading: if `itemProvider.hasItemConformingToTypeIdentifier(UTType.rawImage.identifier)`, `loadFileRepresentation(forTypeIdentifier: UTType.rawImage.identifier)` and **copy** the file (keep its extension) into the app's tmp dir inside the callback. Else "Not ProRAW (or edited in Photos) — skipped" (an edited ProRAW likely arrives as its edited JPEG/HEIC; confirm in M4).
- Rendering: `actor Renderer` owns the `CIContext` (Sendable), params and LUT; items run **sequentially**, each in `autoreleasepool`, with per-item progress and a Cancel that stops before the next item. Before each decode, check `os_proc_available_memory()` against the expected peak (§7) and skip with a message if short. Temp DNG deleted after each item; render + comparison JPEGs kept in tmp until saved or cleared.
- Viewer: full-screen render; press-and-hold swaps in the comparison JPEG (labelled "Apple (SDR preview)").
- Save: request `.addOnly` on first save; `PHAssetCreationRequest.forAsset()`, `addResource(with: .photo, fileURL:)`, set `creationDate`/`location` (§5.3); per-item result; denied → one message with a Settings link.
- Per-item errors never abort the batch: unreadable, not ProRAW, decode failure, insufficient memory, save failure. (A jetsam kill can't be caught; §7's budget prevents it.)
- Simulator check: `xcrun simctl addmedia booted ~/Downloads/IMG_2725.DNG` to get a ProRAW into the simulator's library and `xcrun simctl privacy booted grant photos-add com.nickchua.print`, then `xcodebuild test -scheme Print -destination 'platform=iOS Simulator,name=iPhone 17 Pro Max'` runs `PrintUITests` (picker → render → viewer → save). The simulator is a UI check only, **never** a parity source.
- System look, dark background, placeholder icon.

### M4 — On device
- Device: iPhone 17 Pro Max, **hardware UDID `00008150-00020C3C2239401C`** (for `xcodebuild -destination id=`; the CoreDevice id `EB47AD6D-…` is for `devicectl`). Developer Mode is already on; at review time the tunnel was unavailable, so: phone unlocked, on cable or the same Wi-Fi; check `xcrun devicectl list devices` first.
- Build: `xcodebuild -scheme Print -destination id=00008150-00020C3C2239401C -allowProvisioningUpdates` (no profile exists yet for `com.nickchua.print`), then `xcrun devicectl device install app --device EB47AD6D-B00C-5BE4-B93D-F0D1C88B8792 <Print.app>`. Or Xcode → Run.
- **Signing expiry:** the only signing certificate (team D69T4MH7XQ) expires **2026-12-31**; the install stops launching then. Renew the cert in Xcode and reinstall in late December.
- Parity on device: pick IMG_2725, render, AirDrop the JPEG back, `compare.py` vs Python `out.png` with test D's L\* and signed mean a\*/b\* / neutral b\* thresholds and grain bands ±10 % (the same gate `parity.sh` applies to `swift/app.jpg`). Not ΔE: the app's grain realisation differs from Python's per pixel.
- Confirm on device: picker returns the DNG for ProRAW; an edited ProRAW's behaviour; `creationDate`/`location` land in Photos with add-only permission.
- Timings and peak footprint (Debug overlay: `task_vm_info.phys_footprint` peak) for 12 MP and 48 MP; compare to §7.
- Eyeball pass on the three new DNGs vs their Python renders.

### M5 — Quality gate and commit
- `/ship` (evaluate → simplify → lint/build), `ruff` on the Python, `parity.sh`, Xcode build with no warnings.
- Commit by pathspec: `Photo App/ios`, `Photo App/prototype/{raw_look,export_film,compare}.py`, `Photo App/.gitignore`, `Photo App/APP_SPEC.md`, `Photo App/LOOK.md` (one line pointing at the app). **Never** `fixtures/`, `refs/`, or any DNG/HEIC/JPEG.
- Update §11 with what changed during the build.

## 7. Performance and memory budgets (iPhone 17 Pro Max)

Memory is **peak physical footprint** (what jetsam uses), not resident size.

| | 12 MP ProRAW | 48 MP ProRAW |
|---|---|---|
| Decode + resize (Core Image, strips) | ≤ 1.0 s | ≤ 2.5 s |
| Film model (CPU, always 6 MP) | ≤ 1.0 s | ≤ 1.0 s |
| Encode + write (render + comparison) | ≤ 0.4 s | ≤ 0.4 s |
| Peak footprint | ≤ 600 MB | ≤ 1.5 GB (measure in M4; raise strip count until met) |

Measured on the Mac (12 MP): a full-frame RGBAf render of the Lanczos'd graph peaks at ~810 MB (Core Image allocates big intermediates even when only 6 MP is requested); 8 strips 683 MB, 16 strips 576 MB, values identical (whole pipeline; §11). On the phone with 16 strips: 590 MB (12 MP), 946 MB (48 MP). Naively scaled, a full-frame 48 MP render would be ~2.5–3 GB, hence strips are mandatory. The film model holds ~6 planar 6 MP Float32 buffers (~150 MB); rev 5's softening adds a transient Double plane (50 MB) plus the Float output (25 MB) per channel, sequentially, while the source plane is still held (≈ 75 MB over the baseline), and the density stage runs inside the print loop. Re-measure on the phone with the next device build. Batches run one at a time; caches cleared between items. If the 48 MP decode budget is missed, `scaleFactor` (decode-time downscale) is allowed only if test C still passes.

## 8. Risks

| # | Risk | Mitigation |
|---|---|---|
| R1 | CIRAWFilter's pipeline ≠ Python's matrix math | Tests C/D. Tone-curve differences (ProfileToneCurve) show as a slope → fix settings, never a matrix. Colour-only offsets → one fitted 3×3, validated on the tungsten DNG. Needs the three DNGs listed at the top. |
| R2 | A setting is silently ignored for ProRAW | Read every property back after setting it; log `is…Supported` flags where they exist; tests C/D decide. |
| R3 | Picker hands over a JPEG/HEIC instead of the DNG (e.g. an edited ProRAW) | `.current` + explicit `UTType.rawImage` load + `DNGProbe` gate; message says "or edited in Photos". |
| R4 | Python conventions (BOX/BILINEAR centres, np.percentile, edge padding, integer-index vignette) ported loosely | Each written out in §5.2; tests A/B are near-exact (≥ 99.99 % exact, float max 1/65535), which catches centre-offset and align-corners bugs that a 1-level tolerance would miss. |
| R5 | Memory spike → jetsam | Strip rendering, sequential batch, `clearCaches`, `os_proc_available_memory()` pre-check, footprint measured in M4. |
| R6 | Personal photos leak into git | `fixtures/` + `refs/` git-ignored; DNGs read from env paths outside the repo; pathspec commits. |
| R7 | Film constants drift between Python and Swift | Only in the exported JSON/LUT; §2 lists the few structural literals Swift may hold; a test checks every JSON key is used. |
| R8 | Phone not reachable at execution time | M0–M3 run entirely on the Mac; M4 starts with `devicectl list devices` and waits for the phone if needed. |
| R9 | Signing cert expires 2026-12-31 | Renew and reinstall in late December (M4 note). |

## 9. Decisions (defaults in bold; the user can override)

- **D1 Name:** **"Print"** placeholder.
- **D2 Output:** **JPEG q0.95, sRGB, 6 MP** (matches Python; HEIC later).
- **D3 Non-RAW photos:** **skipped with a message**. A labelled "approximate (from JPEG)" mode with a fixed manual exposure is a v0.1 candidate — not the real look, so not the default.
- **D4 Saving:** **explicit "Save to Photos"**, so test renders don't pile up.
- **D5 Grain seed:** **per photo** (deterministic per file).

## 10. Order of work for the execution session

1. Check for the three new DNGs in `~/Downloads`; note which exist.
2. M0 → M1 (all host-side; no phone, no new DNGs needed).
3. M2 on whatever DNGs exist (fallback rule above).
4. M3 in the simulator.
5. M4 if the phone is connected; otherwise stop after M3 and record where things stand.
6. M5.

## 11. Review log

Adversarial review, 2026-10-29: two independent reviewers, one on Apple-platform reality (probed the Xcode 26.2 SDK headers and ran CIRAWFilter on IMG_2725 on this Mac), one on numeric fidelity (re-implemented the port in float32 and injected likely bugs). 23 findings, none blocking; all folded into rev 2:

| Finding | Change |
|---|---|
| Full-frame CI render peaks ~810 MB at 12 MP (≈ 2.5–3 GB at 48 MP) | Strip rendering mandatory (§5.1.4); budgets in peak footprint; `clearCaches`, `os_proc_available_memory()` (§7, M3) |
| Press-and-hold re-decoded a deleted DNG; CI defaults ≠ what Photos shows | Comparison from `previewImage` (rotated), encoded during the batch, labelled SDR (§5.1.5) |
| `isHighlightRecoveryEnabled` defaults on; `shadowBias` varies; decoder unpinned | Set false / 0 / `8.dng` (§5.1.2) |
| Temperature/tint 6504/0 ≠ D65 | `neutralChromaticity` only |
| `xcodebuild` needs the hardware UDID; no profile yet; cert expires 2026-12-31 | M4 commands fixed, `-allowProvisioningUpdates`, R9 |
| EXIF key names wrong / absent; Photos-from-EXIF unverifiable | Correct keys; set `creationDate`/`location` on the request (§5.3) |
| Edited ProRAW arrives as JPEG | Message + M4 check |
| ImageIO can't see SubIFD Photometric | `DNGProbe` (§5.1.1) |
| SwiftPM 6.2 / Swift 5 mode / resource declarations / Info.plist gaps | §4 |
| Tests A/B let centre-offset vignette and align-corners upsample through | A: ≥ 99.99 % exact, max 1; B: float max 1/65535 |
| Test C: undefined on negatives; ¼-px offset passes correlation but fails colour; metering leaks into tone | Mask, signed medians on 8× downsample, phase-correlation registration, k reported separately, tone slope |
| Test D passes a 5 % blue error and +0.1 stop | Signed Δa*/Δb* ≤ 0.3, ΔE mean ≤ 0.6, L* p50 ≤ 0.5, reference mask with min count |
| ProfileToneCurve present; 3×3 can't fix tone; daylight-only validation | §3 facts; slope test; fit on daylight, validate on tungsten |
| PIL BOX isn't area-weighted | Exact rule stated; v0 asserts dims divisible by 4 |
| Literals inside `render()`; band split undefined; fixture formats; two-order-statistic percentile | M0 promotes literals; compare.py defines bands; fixture formats + stage dumps; §5.2.1 |
| Milestones can't all finish if parity fails or the phone is absent | §10 order; M3 independent of M2; XCTExpectFailure rule |

Verified correct by review: all §5.1 properties exist and are settable; orientation applied by default; `scaleFactor` semantics; unclamped EDR-0 output; RGBAf honoured; `CIContext` Sendable; `swift test` can run CIRAWFilter; PHPicker needs no permission; grain normalisation (Σk² = 0.84824) and lag-1 autocorrelation; PIL BILINEAR formula; blur radii; np.interp clamping; float32 LUT is lossless enough; M0 bit-identical refactor is achievable.

**Rev 3 (2026-10-29, after the tungsten DNG):** highlight-only metering overexposed an evenly lit hallway by ~2.4 stops (p99.5 only 2.6 stops over the median). `raw_look.py` now caps exposure at a log-average-at-mid-grey exposure (`AVERAGE_STOPS = 0`); §5.2 step 1 updated. IMG_2725 renders byte-identically (its highlight meter is 1.4 stops under the cap), so existing references stand. Parity tests must cover both branches: IMG_2725 (highlight wins) and IMG_2732 (average wins).

**Build log (2026-10-29, M0–M3 executed; M4 not started — phone "unavailable" in `devicectl`):**

| Milestone | Result |
|---|---|
| M0 | `render()` split into `prepare` / `meter` / `grain_field` / `film`; every literal named. `np.array_equal` before/after on IMG_2725 **and** IMG_2732, JPEG sha256 unchanged. One deviation: `film()` takes the raw blurred field and normalises it itself (`GRAIN_STOPS * noise / noise.std()`), because normalising first reassociates the float64 product and flips 1.2 % of output values by 1 ulp. `noise.f32` is still the normalised field. |
| M1 | Test A (injected noise vs `out.png`): 99.9995 % / 99.9991 % exact, max 1 level. Test B: max \|Δ\| 0.0039 / 65535. Stages: glow bit-exact, stops 9e-8 relative, k exact. Grain unit test: mean 0.0002, std 1.0001, lag-1 0.0889; app-grain bands vs Python −0.3 % / −0.5 % (IMG_2725), −0.1 % / +0.2 % (IMG_2732). Film model 0.16–0.22 s on the Mac. |
| M1 fix | k is formed in Float like numpy (`float32 / float32`; the log mean still accumulates in Double). With k in Double, a 1-ulp k difference moved near-black pixels — where the crosstalk matrix cancels almost all the light — by up to 0.05 stop and failed the stage check. The crosstalk and vignette are also evaluated in Double for the same reason. |
| M2 | Only IMG_2725 (highlight metering) and IMG_2732 (average cap) exist, so the fallback rule applied — and both pass outright; no `decode_correction`. Test C: colour medians ≤ 0.0003 / 0.0022 stop, p95 0.0005 / 0.0046, tone slope 3e-5 / 1e-4, registration ≤ 0.0003 px. Test D: ΔE mean 0.006 / 0.016, L\* p50 Δ −0.001 / −0.002. Strips (1 vs 8) give identical values. No setting read back differently; no `is…Supported` flag was false. Decode 0.5–1.9 s on the Mac. |
| M2 exposure | Core Image's decode is a pure gain over rawpy's: 2^BaselineExposure × the largest channel of the camera neutral at D65 (3.472 + 0.268 = 3.739 stops on IMG_2725; 1.065 + 1.199 = 2.264 on IMG_2732, both matching the measured gain to 0.001 stop). Metering cancels any pure gain, so `compare.py --linear` now reports it as `decode_gain_stops` and checks `exposure_stops` as the *metered* difference net of it: −0.0002 / −0.00002 stop. The raw k ratio check as first written would have failed by exactly that gain. |
| M3 | `xcodegen` + simulator build, zero warnings in our code. Simulator: app launches, empty state, system picker opens on a library containing IMG_2725. Picking could not be driven from the host (synthetic clicks don't reach the out-of-process picker grid), so picker → render → viewer → save is **unverified in the UI**; the same FilmCore path (decode → app grain → JPEG with metadata) runs on the Mac (`swift/app.jpg`, gated in `parity.sh`) and passes test D's L\* and signed mean a\*/b\* thresholds vs `out.png` (worst: mean Δb\* −0.26 on IMG_2732, JPEG compression) with grain bands within 7.5 %. Test D's per-pixel ΔE terms do **not** apply here: the app's grain seed differs from Python's, so ΔE mean is 2.6–2.9 by construction. Build derived data must live outside `~/Desktop` (File Provider xattrs fail codesign). |

Post-review fixes (independent /evaluate, B+, 0 errors / 7 warnings): unknown `compare.py` metric names now fail; non-finite decodes and truncated TIFF IFDs fail the item instead of trapping; list thumbnails are 240 px ImageIO thumbnails; save errors shown in the row; Cancel also reaches batches queued behind it; 8-bit quantisation rounds half to even like numpy.

M4 remaining: install on the phone, pick IMG_2725/IMG_2732 there, AirDrop back, `compare.py` vs `out.png`; confirm the picker hands over the DNG, edited-ProRAW behaviour, `creationDate`/`location` with add-only access, timings and peak footprint (Debug rows show them) against §7. Strips: 16 per 12 MP (64 for 48 MP) after the Mac proxy below; the phone's footprint decides.

**Phone-free follow-up (2026-10-30):**

| Item | Result |
|---|---|
| Device compile | `xcodebuild -destination generic/platform=iOS CODE_SIGNING_ALLOWED=NO` builds clean (covers the device-only `os_proc_available_memory` path). Signing/provisioning still waits for the phone. |
| Strip count (Mac proxy for §7) | Peak footprint, decode → film → JPEG. 12 MP: 1 strip 789 MB, 8 → 683 MB (**over the 600 MB budget**), 12 → 583, 16 → 576, 24 → 562. 48 MP: 1 → 1457, 8 → 1651, 16 → 1169, 32 → 1158, 64 → 1115 MB (floor ≈ 1.1 GB: Core Image's full-res raw decode). Timing unchanged by strips (12 MP decode 0.5 s, 48 MP 1.9 s, film 0.2 s, encode 0.05 s). Now 16 strips per 12 MP. The phone's numbers (M4) decide. |
| Debug builds | FilmCore unoptimised ran the film model in **91 s** (vs 0.2 s), so Debug runs — Xcode → Run included — looked hung. `Package.swift` now builds FilmCore with `-O` in Debug too (0.23 s). |
| M3 picker flow | New `PrintUITests` target drives the real PHPicker in the simulator: IMG_2725 + a stock JPEG → DNG renders (12 MP, highlight, decode 1.0 s / film 0.24 s / encode 0.10 s in the simulator), JPEG shows "Not ProRAW (or edited in Photos) — skipped", viewer offers the Apple comparison, Save succeeds with add-only access. Picker elements show in the accessibility dump but queries can't resolve them, so picks are coordinate taps pinned to the iPhone 17 Pro Max simulator (guarded by a dump check). `.current` + `UTType.rawImage` does hand over the DNG. |
| Capture time | The saved render first landed 1 s early (GPS stamp 23:58:00 vs shutter 23:58:01.384). Now from DateTimeOriginal + subsec + offset (§5.3); Photos.sqlite shows the render at 23:58:01.384, the original's exact time, and the same location. Unit tests cover offset / GPS-inferred / device-zone cases. |

Still needs the phone: signing + install, on-device parity (`compare.py` vs `out.png`), edited-ProRAW behaviour, real timings and peak footprint for 12 and 48 MP.

**M4 on device — done (2026-10-30, iPhone 17 Pro Max, Debug build with FilmCore `-O`):**

| Item | Result |
|---|---|
| Signing + install | Blocked first by an unaccepted Program License Agreement ("PLA Update available"); after accepting, `-allowProvisioningUpdates` created the profile, `devicectl device install` + launch fine. Cert still expires 2026-12-31 (R9). |
| Parity (renders saved, AirDropped back, `compare.py` vs `out.png`, the `app.jpg` gate) | **PASS both.** IMG_2725: ΔL\* p1/p50/p99 −0.05 / +0.03 / +0.02, mean Δa\*/Δb\* +0.18 / −0.15, grain fine/medium +7.5 % / +1.1 %. IMG_2732: −0.06 / +0.02 / −0.11, +0.18 / −0.26, −0.5 % / −1.3 %. Neutral mask too small on both (n/a). Against the Mac's `swift/app.jpg`, mean L\*/a\*/b\* agree to < 0.001: the phone's decode and film model match the Mac's; per-pixel differences are the grain realisation only. |
| Timings + peak footprint (§7), each item in a fresh launch | 12 MP (IMG_2725): decode 0.36 s, film 0.19 s, encode 0.08 s, **peak 590 MB** (budget 600: passes, 1.7 % headroom). 48 MP (IMG_2732): decode **2.33 s** (budget 2.5), film 0.17 s, encode 0.08 s, peak 946 MB (budget 1.5 GB). All within budget; 12 MP memory and 48 MP decode are the tight ones. The peak is the process lifetime peak, so a later item in the same launch reports the earlier item's peak if higher. |
| Picker | Hands over the DNG for ProRAW on device (both renders came from the picked DNGs). The grain seed hashes the picker's file name, which probably differs from the Mac test's `IMG_2725.DNG` (not checked), so the phone's grain pattern differs from `swift/app.jpg`'s; it is deterministic per photo on the device. |
| Edited ProRAW | An edited ProRAW (exposure tweak in Photos) shows "Not ProRAW (or edited in Photos) — skipped" — the picker's `.current` representation is the edit, not the DNG. Behaviour as designed in §5.3; no change. |
| Save metadata | Renders carry `Software: Print 0.1`, Make/Model; Photos exports them with the originals' capture time. Location matches the original in Photos (add-only access). |

**Rev 4 — print timing (2026-10-31):** every warm-indoor scene (IMG_2732 hallway, IMG_2745/2746 living room) rendered as a flat lemon wash (walls at chroma 60–70, hue 80–87°; a blue towel went grey), because the print was a pure daylight print of a scene 3.5–3.7 stops (log2 R/B of the as-shot white, in linear sRGB) off D65. The fix keeps the fixed D65 decode (test C unchanged) and *times the print*: `print_timing(white)` (§5.2 step 2), a Bradford adaptation of the as-shot white `WHITE_BALANCE` = 0.5 of the way to daylight, luminance kept, folded into the crosstalk after metering (the lab times the print, not the exposure). Rejected on the way: an sRGB-diagonal gain (under-corrects, still lemon at 50 %) and Core Image's own as-shot neutral (interpolates ColorMatrix1/2, up to 0.1 stop of blue from the ColorMatrix2-only white: would break parity).

| Item | Result |
|---|---|
| As-shot whites (linear sRGB, G = 1) | IMG_2725 (1.037, 1, 0.738), 0.49 stop R/B off D65; IMG_2732 (2.287, 1, 0.200), 3.5 stops; IMG_2746 (2.007, 1, 0.154), 3.7 stops |
| Look, after vs before (Python, seed 0) | IMG_2725: ΔE mean 2.2, mean Δb\* −2.2, median L\* unchanged; highlight b\* 13.3 → 11.9, upper-mid a\* −5.2 → −4.7, p90 chroma 25.1 → 22.1 (all toward the LOOK.md ranges). IMG_2732: bright-wall chroma 68 → 58, mean Δa\*/Δb\* −7.2/−8.3, median L\* +0.9. IMG_2746: bright chroma 64 → 32 (cream whites), mean Δb\* −16.3, towel blue. Sheet: `refs/wb_experiments/print_timing_before_after.jpg` (local only) |
| Contract | `film_params.json` version 2 adds `white_balance`, `bradford`, `xyz_to_srgb`; `meta.json` adds `white`. Swift: `DNGProbe.colorTags` (IFD0 rationals 50722/50727/50728), `Decoder.asShotWhite`, `DecodedPhoto.white`, `FilmModel.printTiming`, `render(white:)`, `Matrix3` (Double; cofactor inverse vs numpy's LU inverse: 8e-16 relative on the composite matrix, 3e-11 stop at the worst pixel). Fixture tests pass Python's `white` from `meta.json`; decode tests check Swift's white against it (agree to 1e-15). |
| Metering fix found by the gate | First run: IMG_2746's `stops_pregrain` stage failed (0.0049 stop at a near-cancelling blue pixel; the image itself was within every compare.py gate). Swift's `k_average` was 3 float32 ulps off numpy's (IMG_2725's was 5 ulps off, hidden because highlight metering wins there). numpy had done the log-average in float32 (its own SIMD log and pairwise sum, not reproducible outside numpy). `meter()` now accumulates and exponentiates in float64 and rounds k to float32 once; Swift does the same. k is bit-identical on all three fixtures; the look changes by rounding only. |
| Parity (`parity.sh`: 15 tests, 3 fixtures, IMG_2746 new) | **PASS.** A: exact 99.9993 / 99.9991 / 99.9986 %, max 1 level; B: max 0.0039/65535; stages: glow bit-exact, stops 9e-8 relative, k exact. C: exposure ≤ 0.0002 stop, colour medians ≤ 0.0022 stop, p95 ≤ 0.0046, tone slope ≤ 1e-4, registration ≤ 0.0003 px. D: ΔE mean 0.006 / 0.025 / 0.016, L\* p50 Δ ≤ 0.002, mean Δa\*/Δb\* ≤ 0.013. App path (decode + app grain + JPEG vs `out.png`): mean Δa\*/Δb\* ≤ 0.19 / 0.18, L\* p50 ≤ 0.07, grain bands ≤ 7.8 %. |
| Open | 50 % vs 65 % strength, judged on the phone (65 % is more neutral; one constant + re-export + rebuild). Hue: Chromagraph's tungsten goes orange (46°), ours stays yellow (85–89°) at half the chroma; needs a real tungsten Chromagraph/ProRAW pair. LOOK.md's "Density" section (2026-10-31 adversarial re-measurement) lists the next targets: the warm-hue-by-L\* profile (shadows toward 55–60°, nothing past ~90° in the brights; v2 runs 75 → 97°), chroma falling with density (×0.6 dark, ×1.1 bright; v2 flat), unmasked cream +12 to +15, ceiling L\* 93.5 / b\* +9, halation σ about half, vignette about a third, grain σ ~0.55 px, a touch of softening. Prototype sheet `refs/wb_experiments/density_experiment.jpg` (variant B, LCh palette step); nothing enters the app before the user judges it on real photos. |

Post-review fixes (independent /evaluate, B+, 0 errors / 2 warnings): the metering loop's per-pixel `log` was still the Float overload (now `log(Double(…))`, as step 1 says; the fixtures' k did not move); "exposure is the only scene-adaptive step" corrected in §1 and LOOK.md; singular bundled matrices now throw `invalidParams` instead of silently printing untimed; the as-shot white must be finite with G > 0 on both sides. /simplify (four reviewers): one IFD walker in `DNGProbe` serves both the gate and the colour tags; the timing's fixed matrices are computed once in `FilmModel.init` (so the failure is at load, like `lutMismatch`) and `printTiming` is pure per-photo; the `WHITE_FLOOR` crash guard (which could only ever yield a garbage matrix) became one predicate on both sides, identity unless the white's cone responses are all positive and finite (bit-identical output for every real white; `white_floor` left the contract); `render(white:)` has no default, so no caller can silently get the pre-rev-4 print; `XYZ_TO_SRGB` is public now that it is exported. Noted for later harnesses: numpy's `rgb @ LUMA` differs by an ulp between a strided view and a contiguous array (`prepare()` always returns contiguous), so feeding `meter()` a view would not reproduce `k_highlight` bit for bit.

**Rev 5 — colour moves with density (2026-10-31):** LOOK.md's "Density" targets, applied after the variant B sheet (`refs/wb_experiments/density_experiment.jpg`) was judged on our own photos. LOOK.md → "v3" has the mechanism, the measurements and what was rejected.

| Item | Result |
|---|---|
| Model (`raw_look.py` v3) | `HIGHLIGHT_STOPS` 5 → 6 (the highlight-metered window room was a stop dark: p95 L\* 72.6 → 81.9, exports 79–83); print curve top 90 / 92.5 / 93.5 at +6 / +8 / +12 stops; grey scale b\* +13 at L\* 88, +10 at the 93.5 ceiling, a\* +0.3 at 88; new `soften()` (σ 0.55 px, before metering); new `density()` (§5.2 step 5): departure from luminance, magenta shift `size · (SHIFT_DENSE + SHIFT_SATURATED · size)`, `CHROMA_GAIN`, all by luminance in stops, neutrals untouched; `HALATION_SIGMA` 0.006 → 0.003; `VIGNETTE_STOPS` 0.35 → 0.12; `GRAIN_SIGMA` 0.4 → 0.55. Window room warm hue by L\* 77 / 80 / 93 / 101 / 102 / 96 → 67 / 74 / 82 / 95 / 93 / 91 (living-room export 72 / 79 / 83 / 89 / 90 / 87); Apple → render chroma 0.82 / 0.88 / 0.86 / 0.92 / 0.80 → 0.59 / 0.70 / 0.83 / 1.06 / 0.99 (office stock → Chromagraph 0.60 / 0.60 / 0.81 / 1.10 / 1.13); the tungsten hallway's mids 80 → 71° (alley 53, shopkeeper 52) |
| Found on the way | Pivoting the stage on the channel mean let a channel at the clamp floor (20–25 % of the hallway's dark pixels) drag the pixel's density down, and the chroma gain then darkened whole walls with a hard edge at the clamp boundary. The pivot is the luminance, which a crushed blue barely moves; the size is capped at 4 stops. Colour sizes are 1.5 stops in the daylight room and 3–5 under tungsten, far more than their Lab chroma suggests, so the shift's size law was measured, not assumed: linear in size for the dense term (the references' darks swing whatever their chroma), squared for the saturated term (their mids swing only when saturated) |
| Contract | `film_params.json` version 3 adds `soften_sigma`, `density_stops`, `chroma_gain`, `shift_dense`, `shift_saturated`, `green_magenta`, `density_chroma_cap`; the LUT sha changes. Swift: `FilmModel.render` step 0 (three `Filters.gaussianBlur` planes), `FilmModel.density` (Double from Float32, numpy's operation order), `FilmModel.interp` (np.interp on a short axis), `init` validates the tables share an increasing axis; `testDensity` (neutrals fixed, dense warm loses green and chroma, light keeps hue and gains, `interp` at and between knots); the grain test derives its lag-1 autocorrelation from the kernel instead of a constant. `Renderer.swift` unchanged |
| Parity (`parity.sh`: 16 tests, 3 fixtures re-exported) | **PASS.** k bit-identical on all three; glow bit-exact; `stops_pregrain` (now after the density stage) 1.1e-7 / 6.7e-8 / 9.6e-8 relative. A: exact 99.999 / 99.9992 / 99.999 %, max 1 level; B: max 0.0078/65535. C: exposure ≤ 0.0002 stop, colour medians ≤ 0.0022 stop, p95 ≤ 0.0046, tone slope ≤ 1.1e-4, registration ≤ 0.0003 px. D: ΔE mean 0.006 / 0.024 / 0.012, L\* p50 Δ ≤ 0.004, mean Δa\*/Δb\* ≤ 0.016. App path (decode + app grain + JPEG vs `out.png`): mean Δa\*/Δb\* ≤ 0.18 / 0.15, L\* p50 ≤ 0.07, grain bands ≤ 5.7 %. Mac film model 0.25 s at 6 MP (was 0.2 s; the softening blur) |
| Open | Peak footprint and film time with the softening blur, to re-measure on the phone (§7); bright foliage and skies under the ×1.4–1.6 bright chroma gain on a sunlit daylight DNG; the 65 % timing question is closed (the lemon was hue, not amount) |
