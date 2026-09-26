# Benchmark Metrics

This project uses three different accuracy-style metrics. They are not the same.

## Any-Match Accuracy

Fraction of logs where at least one predicted label matches at least one ground-truth label.

Use this when evaluating whether the engine surfaced the right failure family anywhere in the ranked output.

## Top-1 Accuracy

Fraction of logs where the highest-confidence prediction matches at least one ground-truth label.

Use this when evaluating the engine as a single-best-guess triage tool.

## Exact-Match Accuracy

Fraction of logs where the set of predicted labels exactly matches the set of ground-truth labels.

This is the strictest metric and is expected to be lower than the others.

## Macro F1

Unweighted mean F1 across active labels.

Use this to understand per-label balance rather than just top-line hit rate.

## Analyze Latency

Wall-clock time for the in-process analyze pipeline
(`LogParser.parse` -> `FeaturePipeline.extract` -> `HybridEngine.diagnose`),
which is what the `/api/analyze` endpoint wraps.

Milestone 5 of the roadmap sets a gate of **under 500 ms on a standard log**.
Median of 3 runs, measured on the bundled logs (Windows, Python 3.13,
2026-09-26):

| Log | Size | Parse | Features | Diagnose | Total | Gate |
| --- | --- | --- | --- | --- | --- | --- |
| `sample.bin` | 0.99 MB | 209–288 ms | 59–63 ms | 94–165 ms | **433–445 ms** | pass (low margin) |
| `test_cascade.BIN` | 2.16 MB | 492–648 ms | 166–173 ms | 86–101 ms | **767–900 ms** | fail |

Parsing dominates at roughly 50–65% of the total and scales with log length, so
the 500 ms gate is really a function of log size rather than a fixed constant:
it holds for a ~1 MB log (`sample.bin` clears it with only ~55–67 ms of
headroom) and is exceeded at ~2 MB.

Three caveats on these numbers:

- **Single measurement is not enough.** A single untimed run of `sample.bin`
  came in at 298 ms — comfortably under the gate — while the median of 3 was
  445 ms. One-shot timings on a loaded machine fluctuate by 50% or more, so
  quote the median and treat the gate as having *little* margin on `sample.bin`,
  not a comfortable one.
- **`diagnose` is the least reproducible stage.** Two separate median-of-3 runs
  on the same tree gave 94 ms and 165 ms for `sample.bin` — a 75% spread, and
  wider than the spread on parse or features. The ML inference cost appears to
  be dominated by model load/warm-up on first call rather than by the number of
  rows scored, which is also why it is not proportional to log size (94–165 ms
  on `sample.bin` vs 86–101 ms on the 2x larger `test_cascade.BIN`). Treat the
  `diagnose` column as indicative only; the *total* is the figure with a gate
  attached to it, and it is stable to within ~3% across runs.
- **The in-process pipeline is not the whole endpoint.** `_analyze_temp_log`
  additionally builds the hardware report, health score, `time_series` and
  `timeline_events`. End-to-end construction of the full response object takes
  **~2.3 s** — about 5x the pipeline figure above — so the 500 ms gate as
  currently phrased (a bare `/api/analyze` latency target) is met by the
  *diagnostic pipeline* but **not** by the endpoint as a whole. The response
  payload for `sample.bin` is **0.42 MB**, of which `hardware_report` is 71%.
  Any future work on the Milestone 5 gate has to address response construction,
  not just parsing. The pipeline numbers above are retained because they are
  what `tests/test_analyze_latency.py` guards.

Guarded by `tests/test_analyze_latency.py`, which asserts a deliberately
generous 5 s ceiling to catch order-of-magnitude regressions (an accidental
O(n^2), a re-parsed log, a model reloaded per call) without flaking on a
loaded CI box. It deliberately does **not** enforce the 500 ms gate, because
`test_cascade.BIN` cannot currently meet it, and it measures the in-process
pipeline rather than the HTTP endpoint.

## Response Payload Size

`sample.bin` (0.99 MB on disk) produces a **0.42 MB** `/api/analyze` JSON
response. The breakdown matters, because the response is roughly half the size
of the input and the growth is not uniform:

| Component | Size | Share |
| --- | --- | --- |
| `hardware_report` | 0.30 MB | 71% |
| `time_series` | 0.08 MB | 19% |
| `features` | 0.01 MB | 3% |
| everything else | 0.03 MB | 7% |

A DataFlash log expands substantially when materialised as Python lists: the
parsed structure for `sample.bin` serialises to **~3.9 MB**, 4x the input file.
Echoing even one full message stream into the response would swamp it, so
`raw_message_explorer` caps samples at 3 rows per stream
(`src/analysis/context_metrics.py`). `IMU` (1820 rows, 564 KB serialised) is the
largest single stream and is *not* fully emitted anywhere in the response.

`hardware_report` dominates because it aggregates ~40 sub-reports (tuning
metrics, FFT/spectrogram, system identification, notch proposal, phase replay,
mission review). Any response-size reduction should start there.
