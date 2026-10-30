# Print — iPhone app spec (v0)

**Status:** reviewed, ready to execute · 2026-10-29 · rev 3 (rev 2 = adversarial review; rev 3 = metering cap, §11) · working name "Print" (placeholder; renaming is a one-line change in `project.yml`)
**Goal:** run the v2 film model (`prototype/raw_look.py`, documented in `LOOK.md` → "v2") on the phone, on ProRAW photos already in the library, with output that matches the Python reference. No server, no network, no Claude/API at runtime.

**Before the execution session, the user shoots (ProRAW, 48 MP):** (1) daylight with blue sky, (2) indoor under warm lamps / tungsten — **done: `~/Downloads/IMG_2732.DNG`** (hallway under warm ceiling lights; the average-capped metering was added because of it), (3) a portrait. AirDrop the DNGs to `~/Downloads`. They are needed for M2's validation (§6) and never enter git.

---

## 1. What v0 is (and isn't)

**v0 does:**
1. Pick one or more photos from the library (system picker; no library permission needed to read).
2. For each ProRAW DNG: decode → film model → 6 MP JPEG, on device.
3. Show the results; tap one for full screen, press-and-hold to see Apple's own rendering (the DNG's embedded preview, SDR).
4. "Save to Photos" writes the renders (add-only permission) with the original's capture date and location.

**v0 does not (deliberately):**
- **No sliders or presets.** LOOK.md principle 1 is "one fixed rendering"; exposure metering is the only scene-adaptive step. A Debug-only grain on/off toggle is allowed.
- **No camera capture** (v1). **No share extension** (v1 candidate). **No non-RAW input**: HEIC/JPEG items show "Not ProRAW (or edited in Photos) — skipped" (§9 D3). **No TestFlight, iPad, or App Store work.**
- **No network code and no analytics.** Nothing leaves the phone.

## 2. Ground truth and source of truth

| Thing | Source of truth | How the app gets it |
|---|---|---|
| Film model math | `prototype/raw_look.py` | Ported once to Swift (`FilmCore`); parity-tested against Python fixtures |
| Constants | `raw_look.py` module constants (M0 promotes every literal in `render()` to a named constant) | Exported to `film_params.json` by `prototype/export_film.py`; Swift loads it |
| Print curve (stops → linear RGB, 4096 × 3) | `raw_look.print_lut()` | Exported to `print_lut.bin` (little-endian float32, 4096 rows × 3 channels, row-major); `lut_sha256` in the JSON |
| Reference renders | `raw_look.py` on a DNG | `export_film.py --reference <dng>` writes stage-by-stage fixtures to `Photo App/fixtures/` (git-ignored) |

Tuning keeps happening in Python; a retune is "re-run the export, rebuild". **Swift may contain only these structural literals:** array shapes, the sRGB OETF constants (0.0031308, 12.92, 1.055, 0.055, 2.4), √2 in the vignette radius, and 255 for quantisation. Every other number (0.18 mid grey, luma weights, vignette 0.45/1.0/1.5, the halation downsample factor 4, blur truncation 3σ, the 1e-6 / 1e-7 floors, the LUT range) comes from `film_params.json`.

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
4. **Render in horizontal strips** (8 strips, or more for 48 MP) with one shared `CIContext(options: [.workingColorSpace: extendedLinearSRGB, .workingFormat: CIFormat.RGBAf, .cacheIntermediates: false])` into one RGBAf bitmap (`extendedLinearSRGB`), then de-interleave to planar R, G, B. A single full-frame render of a 12 MP file peaks at ~810 MB footprint; 8 strips peak at ~520 MB with identical values. Negative values are kept (Python keeps them until the crosstalk clamp).
5. **Comparison image:** `filter.previewImage` (embedded Apple JPEG, 4032×3024, **not** rotated: apply the file orientation), scaled to 2880 and encoded as JPEG now — the DNG is deleted after the item.
6. Also return the source metadata (`CGImageSourceCopyPropertiesAtIndex`) for Encode. After the item: drop the filter, `ctx.clearCaches()`.

### 5.2 Film model (`FilmModel.swift`) — port of `render()` after its resize

Inputs: planar linear RGB (H×W), `FilmParams`, LUT, and a seed or an injected noise field (tests).

1. **Meter.** `lum = Σ lumaᵢ · cᵢ`. `p = percentile(lum, HIGHLIGHT_PERCENTILE)` with numpy's default *linear* method: with N pixels, rank `q = (N − 1) · P/100`; select order statistics ⌊q⌋ and ⌊q⌋+1 (quickselect on a copy, both needed) and interpolate with t = q − ⌊q⌋. No histogram approximation. `k_highlight = MID_GREY · 2^HIGHLIGHT_STOPS / max(p, 1e-6)`. `k_average = MID_GREY · 2^AVERAGE_STOPS / exp(mean(ln(max(lum, 1e-6))))` (accumulate the mean in Double: 6 M terms). `k = min(k_highlight, k_average)`; multiply all channels by k. `meta.json` records both k values and which one won.
2. **Crosstalk.** `rgb ← CROSSTALK · rgb` (the final 3×3 from the JSON), then clamp each channel to `≥ CLAMP_FLOOR` (1e-7).
3. **Vignette.** For **integer** pixel indices x, y (as `np.ogrid`; not pixel centres): `r = hypot((x − W/2)/(W/2), (y − H/2)/(H/2)) / √2`; `gain = 2^(−VIGNETTE_STOPS · smoothstep(r, VIGNETTE_START, VIGNETTE_END)^VIGNETTE_POWER)`. Gain map precomputed per size.
4. **Halation.** `lum` of the vignetted rgb; `excess = max(lum − MID_GREY · 2^HALATION_STOPS, 0)`; `glow = wide_blur(excess, HALATION_SIGMA · max(H, W))`; `rgb += HALATION_STRENGTH · glow · HALATION_TINT`.
   `wide_blur(x, σ)`: (a) **4×4 mean** to (W/4, H/4) (exact for PIL BOX at divisible sizes; PIL BOX is *not* area-weighted otherwise — each output averages the source pixels whose centres fall in [c − s/2, c + s/2) — which v0 avoids via the §5.1 assert); (b) separable Gaussian, σ′ = σ/4, radius `max(1, int(3σ′))` (12 at 2880), kernel normalised to 1, **edge-replicate** padding; (c) bilinear upsample to (W, H) with PIL's convention `src = (dst + 0.5) · (in/out) − 0.5`, clamped to [0, in − 1]. Not align-corners.
5. **Grain.** `stops = log2(rgb / MID_GREY)` per channel. Noise n (H×W): injected (already normalised by Python), or `Grain.field(seed, H, W)`: i.i.d. N(0,1) from a counter-based hash of (seed, x, y) → two uniforms → Box–Muller; blurred with Python's `blur(…, GRAIN_SIGMA)` kernel (σ 0.4 → radius 1 → [0.0404, 0.9192, 0.0404], edge padding); divided by the analytic std Σkᵢ² = 0.84824 (computed from the kernel, not hard-coded; verified empirical/analytic = 0.9999). `stops += GRAIN_STOPS · n`, same n on all channels.
   Seed: FNV-1a 64 of (file name + DateTimeOriginal), so re-rendering a photo is deterministic and photos differ.
6. **Print.** Per channel `lin = interp(stops, linspace(LUT_MIN, LUT_MAX, LUT_SIZE), lut[:, c])`, clamped at the ends (np.interp semantics).
7. **Encode transfer.** sRGB OETF with clip to [0, 1] (Python's last line). `render` returns this float image; quantisation `round(x · 255)` happens in Encode. Tests compare the float image.

### 5.3 Encode (`Encode.swift`)

- 8-bit RGB `CGImage` tagged sRGB, upright (Orientation 1). `CGImageDestination` JPEG quality 0.95. No gain map / HDR in v0.
- Copy from the source when present: `DateTimeOriginal`, `SubsecTimeOriginal`, `OffsetTimeOriginal` (absent in IMG_2725), the GPS dictionary including `DateStamp`/`TimeStamp`, Make/Model, lens model, ISO, exposure time, f-number, focal length. Set `Software = "Print <version>"`. Drop thumbnails, MakerNote, orientation and pixel-dimension tags.
- **Also set `creationDate` and `location` on the `PHAssetCreationRequest`** (don't rely on Photos reading EXIF). Capture time = GPS UTC stamp if present, else DateTimeOriginal (+ OffsetTimeOriginal if present, else the device time zone). M4 confirms both setters work with add-only permission.

## 6. Milestones (in order; each ends green before the next)

### M0 — Python prep (no behaviour change)
- Promote every literal in `render()` to a named module constant (§2 list). Refactor `render()` into `prepare(rgb) → rgb6mp` (resize only), `grain_field(h, w, seed) → normalised noise` and `film(rgb6mp, noise) → float sRGB`, keeping `render()` as a wrapper. **Acceptance:** `np.array_equal` of `render()`'s float output before/after on IMG_2725, and the saved JPEG's sha256 unchanged.
- `export_film.py` default: write `FilmCore/Sources/FilmCore/Resources/{film_params.json, print_lut.bin}`. JSON: `version`, every §5.2 constant (final `CROSSTALK` 3×3, luma weights, mid grey, vignette, halation incl. downsample factor and truncation, grain, floors), `lut_min/max/size`, `lut_sha256`.
- `export_film.py --reference DNG` → `fixtures/<stem>/`. All `.f32` files are **little-endian float32, planar, channel order R,G,B, row-major**:
  `linear6mp.f32` (after `prepare`, before metering, includes negatives) · `noise.f32` (normalised) · `glow.f32` · `stops_pregrain.f32` · `out_nograin.f32` and `out.f32` (float sRGB before quantisation) · `out.png` (8-bit) · `meta.json`: H, W, seed, N, percentile rank q, p, k, numpy/Pillow/rawpy versions, `lut_sha256`.
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
- **Grain unit test:** app generator on a flat field: |mean| < 0.01, std within 1 % of 1, lag-1 autocorrelation 0.0875 ± 0.005. On IMG_2725 with the app's own noise: fine/medium grain bands within ±10 % of Python's `out.png`.
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
- Simulator check: `xcrun simctl addmedia booted ~/Downloads/IMG_2725.DNG` to get a ProRAW into the simulator's library; the simulator is a UI check only, **never** a parity source.
- System look, dark background, placeholder icon.

### M4 — On device
- Device: iPhone 17 Pro Max, **hardware UDID `00008150-00020C3C2239401C`** (for `xcodebuild -destination id=`; the CoreDevice id `EB47AD6D-…` is for `devicectl`). Developer Mode is already on; at review time the tunnel was unavailable, so: phone unlocked, on cable or the same Wi-Fi; check `xcrun devicectl list devices` first.
- Build: `xcodebuild -scheme Print -destination id=00008150-00020C3C2239401C -allowProvisioningUpdates` (no profile exists yet for `com.nickchua.print`), then `xcrun devicectl device install app --device EB47AD6D-B00C-5BE4-B93D-F0D1C88B8792 <Print.app>`. Or Xcode → Run.
- **Signing expiry:** the only signing certificate (team D69T4MH7XQ) expires **2026-12-31**; the install stops launching then. Renew the cert in Xcode and reinstall in late December.
- Parity on device: pick IMG_2725, render, AirDrop the JPEG back, `compare.py` vs Python `out.png` with test D's look thresholds and grain bands ±10 %.
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

Measured on the Mac (12 MP): a full-frame RGBAf render of the Lanczos'd graph peaks at ~810 MB (Core Image allocates big intermediates even when only 6 MP is requested); 8 strips peak at ~520 MB, values identical. Naively scaled, a full-frame 48 MP render would be ~2.5–3 GB, hence strips are mandatory. The film model holds ~6 planar 6 MP Float32 buffers (~150 MB). Batches run one at a time; caches cleared between items. If the 48 MP decode budget is missed, `scaleFactor` (decode-time downscale) is allowed only if test C still passes.

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
