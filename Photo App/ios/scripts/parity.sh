#!/bin/bash
# FilmCore parity (APP_SPEC.md M1/M2): `swift test` writes Swift renders next to the Python fixtures,
# then prototype/compare.py applies the gates. Metrics live only in compare.py.
# Env: PRINT_FIXTURES_DIR (default "Photo App/fixtures"), PRINT_DNG_DIR (default ~/Downloads).
set -uo pipefail
APP="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$APP/.venv/bin/python"
FIX="${PRINT_FIXTURES_DIR:-$APP/fixtures}"
compare() { "$PY" "$APP/prototype/compare.py" "$@"; }
fail=0

(cd "$APP/ios/FilmCore" && swift test -c release) || fail=1

for dir in "$FIX"/*/; do
  stem="$(basename "$dir")"; s="$dir/swift"
  [ -f "$s/out.f32" ] || continue
  echo "== $stem: test A (injected noise) vs out.png"
  compare "$dir/out.png" "$s/out.f32" --min pct_exact=99.99 --max max_d8=1 || fail=1
  echo "== $stem: test B (no grain, float)"
  compare "$dir/out_nograin.f32" "$s/out_nograin.f32" --max max_d16=1 || fail=1
  echo "== $stem: app grain vs Python grain (bands ±10 %)"
  compare "$dir/out.png" "$s/out_appgrain.f32" --max grain_fine_ratio=0.10 --max grain_medium_ratio=0.10 || fail=1
  if [ -f "$s/decoded6mp.f32" ]; then
    echo "== $stem: test C (decode, linear)"
    compare --linear "$dir/linear6mp.f32" "$s/decoded6mp.f32" --max exposure_stops=0.02 --max dx=0.1 --max dy=0.1 \
      --max median_log2_r=0.02 --max median_log2_g=0.02 --max median_log2_b=0.02 --max p95_abs_log2=0.08 \
      --max tone_slope=0.01 || fail=1
    echo "== $stem: test D (decode + model, no grain)"
    compare "$dir/out_nograin.f32" "$s/decoded_out_nograin.f32" --max dL_p50=0.5 --max dL_p1=1.0 --max dL_p99=1.0 \
      --max mean_da=0.3 --max mean_db=0.3 --max de_mean=0.6 --max de_p95=2.0 --max neutral_db=0.5 || fail=1
  fi
  if [ -f "$s/app.jpg" ]; then
    echo "== $stem: app path (decode + app grain + JPEG) vs out.png: look means and grain bands"
    compare "$dir/out.png" "$s/app.jpg" --max dL_p50=0.5 --max dL_p1=1.0 --max dL_p99=1.0 --max mean_da=0.3 \
      --max mean_db=0.3 --max neutral_db=0.5 --max grain_fine_ratio=0.10 --max grain_medium_ratio=0.10 || fail=1
  fi
done
[ $fail -eq 0 ] && echo "PARITY: PASS" || echo "PARITY: FAIL"
exit $fail
