# Acceptance benchmark harness

benchmarks.acceptance is the acceptance surface for the CITA-Nexus prompt
draft. It measures the code that exists in the checkout and records the
hardware, Python, package, Docker, and source-revision context with every run.

## Run

From the repository root:

~~~powershell
uv run --isolated --no-project --with numpy --with scipy --with pyarrow python -m benchmarks.acceptance --batch-cases 32
~~~

Without --input, the harness creates a deterministic Arrow IPC workload at
or above 50 MiB. The file contains the reflected message families ATT, VIBE,
RCOU, BAT, IMU, GPS, POS, and ERR. It is synthetic and is not evidence that a
real DataFlash .BIN conversion has the same behavior.

Use --input only with an existing Arrow IPC file of at least 50 MiB; a smaller
or incompatible file is reported as unavailable or failed.

To retain the generated workload:

~~~powershell
uv run --isolated --no-project --with numpy --with scipy --with pyarrow python -m benchmarks.acceptance --output-dir .\benchmark-artifacts
~~~

Docker SITL is never started by default. --run-sitl is an explicit opt-in and
requires a working Docker executable and image. If either is absent, SITL
throughput is unavailable, with no estimated or fabricated value.

## Metrics and honest boundaries

| Metric | Target | What is measured |
| --- | ---: | --- |
| Ingestion latency | <= 200 ms | parse_arrow over the verified Arrow workload |
| Diagnostic latency | < 250 ms | Steady-state parse plus diagnosis after exact-module preload and one deterministic warmup; cold-start is reported separately |
| Peak memory | < 200 MiB | Fresh child-process OS peak working set, with baseline and scope recorded |
| Batch throughput | >= 30 logs/s | Deterministic diagnostic cases on the requested worker count; disk/Arrow ingest is excluded and stated in the JSON details |
| SITL throughput | >= 900 logs/h | Completed Docker scenarios only; dry-run output is not throughput evidence |

Targets are copied from the prompt draft and goal objective. A measured
target miss is failed. A missing dependency, telemetry field, Docker runtime,
or platform memory API is unavailable with observed: null and target_met:
null. The CLI exits non-zero for measured failures; add --strict to also fail
on unavailable metrics.

The diagnostic latency target is explicitly a steady-state claim. The timed
interval begins only after the six diagnostic production modules are imported
and one deterministic 8192-sample diagnostic case has completed. The result
also records preload modules, preload/warmup durations, and a fresh-child
cold-start observation. Cold-start includes interpreter and lazy-import cost;
it is process-cold but does not claim to flush the operating-system disk/page
cache. It is never hidden or used to turn a cold failure into a steady-state
pass.

The memory number is a fresh child-process peak upper bound and includes
Python and Arrow parser startup. It is not a claim of an isolated allocator
trace for only the telemetry rows.
The batch number measures the available core diagnostic path, not an
unimplemented full-CLI batch scheduler. These limits are deliberate so the
report cannot imply coverage that the current production code does not
provide.

## Acceptance tests

Run the acceptance tests with:

~~~powershell
uv run --isolated --no-project --with pytest --with numpy --with scipy --with pyarrow pytest tests/acceptance -q
~~~

The tests cover:

- deterministic synthetic input and size gating;
- steady-state versus cold-start diagnostic timing semantics;
- offline MCP request/causal artifact behavior;
- residual-colored 3-D visualization structure and XSS-safe titles;
- causal-chain root selection and impact-boundary suppression;
- bounded .param and MAVLink parameter diffs;
- safe SITL scenario validation and explicit dry-run behavior;
- environment reporting and unavailable-state semantics.

The visualization acceptance test rejects an external Plotly CDN because the
prompt requires zero-cloud operation. A failing result there is an actionable
production integration gap, not permission to mark the offline requirement as
passed.
