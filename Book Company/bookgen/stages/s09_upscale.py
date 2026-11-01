"""S9 Upscale (SPEC §3.3 S9).

In:   chosen images.
Out:  `epNN/print/sNN.png` at trim plus bleed (8.5 x 8.5 in, 0.125 in bleed: a spread is
      17.25 x 8.75 in, 5175 x 2625 px at 300 DPI [VERIFY-3]). Real-ESRGAN locally or the
      provider's upscaler.
Gate: sharpness check and a vision diff against the source to catch invented detail.
"""

from __future__ import annotations

from bookgen.models import StageId
from bookgen.stages.base import StageContext

STAGE_ID = StageId.S9


def run(ctx: StageContext) -> None:
    """Run S9. Not implemented yet (Phase 0 session plan, SPEC §10.1)."""
    raise NotImplementedError(f"not implemented (SPEC §3.3 {STAGE_ID})")
