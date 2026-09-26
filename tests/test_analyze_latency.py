"""Performance regression guard for the analyze pipeline (Milestone 5).

``docs/UPGRADE_ROADMAP.md`` Milestone 5 sets a latency gate: keep ``/analyze``
under 500 ms on a standard log.

Measured baseline on the bundled logs (Windows, Python 3.13, 2026-09-26),
median of 3 runs, across two runs of the same tree:

| log               | size    | parse       | features | diagnose   | total       |
| ----------------- | ------- | ----------- | -------- | ---------- | ----------- |
| `sample.bin`      | 0.99 MB | 209-288 ms  | 59-63 ms | 94-165 ms  | 433-445 ms  |
| `test_cascade.BIN`| 2.16 MB | 492-648 ms  | 166-173 ms | 86-101 ms | 767-900 ms  |

`sample.bin` meets the 500 ms gate but with little headroom — a single
untimed run measured 298 ms, the median of 3 was 445 ms, so treat the gate as
barely cleared rather than comfortably met. The 2x larger `test_cascade.BIN`
does not meet it, because parsing dominates (~50-65% of the total) and scales
with log size — so the gate is really a function of log length, not a fixed
constant.

`diagnose` is the least reproducible stage (94 ms vs 165 ms across two runs)
and is not proportional to log size; the cost looks dominated by model
load/warm-up on first call. The `total` column is the stable one, within ~3%
across runs, which is why the assertion below is written against total elapsed
time rather than any single stage.

Two scope notes worth keeping in mind when reading this file:

* This guards the **in-process pipeline** (`parse -> extract -> diagnose`), not
  the HTTP endpoint. Building the full `/api/analyze` response also runs the
  hardware report, health score and visualization builders and takes ~2.3 s
  end-to-end, so the 500 ms gate is not an endpoint-level statement.
* The ceiling is deliberately *generous* rather than the gate itself: it exists
  to catch order-of-magnitude regressions (an accidental O(n^2), a re-parsed
  log, a model reloaded per call), not to re-assert a gate the larger bundled
  log cannot meet. Timing is machine dependent, so the bound is loose enough
  not to flake on a loaded CI box.
"""

import time
from pathlib import Path

from src.diagnosis.hybrid_engine import HybridEngine
from src.features.pipeline import FeaturePipeline
from src.parser.bin_parser import LogParser

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_LOG = REPO_ROOT / "sample.bin"

# ~11x the measured 445 ms median baseline: catches catastrophic regressions only.
BUDGET_SECONDS = 5.0


def test_analyze_pipeline_completes_within_a_generous_budget():
    assert SAMPLE_LOG.exists(), "bundled sample.bin is required for this guard"

    started = time.perf_counter()
    parsed = LogParser(str(SAMPLE_LOG)).parse()
    features = FeaturePipeline().extract(parsed)
    findings = HybridEngine().diagnose(features)
    elapsed = time.perf_counter() - started

    assert findings, "pipeline must still produce findings for sample.bin"
    assert elapsed < BUDGET_SECONDS, (
        f"analyze took {elapsed:.2f}s, over the {BUDGET_SECONDS:.1f}s budget "
        f"(measured median baseline is ~0.45s for sample.bin)"
    )


def test_feature_extraction_is_not_the_bottleneck():
    """Parsing dominates; guard that feature extraction stays the minor cost."""
    parsed = LogParser(str(SAMPLE_LOG)).parse()

    started = time.perf_counter()
    FeaturePipeline().extract(parsed)
    feature_seconds = time.perf_counter() - started

    assert feature_seconds < BUDGET_SECONDS / 2, (
        f"feature extraction took {feature_seconds:.2f}s, unexpectedly dominant"
    )
