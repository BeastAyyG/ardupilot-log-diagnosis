# Professor Brief: ArduPilot Flight-Log Diagnosis with Verified Synthetic Data

## One-sentence description

This project builds an evidence-first assistant that reads ArduPilot `.BIN`
flight logs, extracts engineering signals, and ranks plausible root causes of
a failure using transparent rules plus a machine-learning candidate that may
abstain when evidence is weak.

## The problem

Drone failure analysis is slow and expert-intensive. A crash log can contain
vibration, motor output, power, GPS, compass, attitude, and EKF symptoms at the
same time. Many are downstream effects rather than the initiating fault. A
naive classifier can therefore learn shortcuts, confuse symptoms with causes,
or report high confidence on an unfamiliar aircraft or flight condition.

## What the system does

- parses ArduPilot DataFlash logs into a normalized record;
- extracts interpretable vibration, motor, power, GPS, compass, attitude, and
  estimator features;
- applies deterministic safety/quality checks and causal ordering;
- combines those checks with an ML candidate for root-cause ranking;
- reports evidence, limitations, and an explicit uncertain/abstain state; and
- produces hash-bound receipts so every result can be traced to exact data,
  code, model, simulator build, and evaluation split.

It is a post-flight diagnostic aid. It does not control an aircraft, change
parameters, or replace physical inspection and an independent safety review.

## Why synthetic data

Real crash logs are scarce, imbalanced, inconsistently labeled, and often do
not isolate a single cause. ArduPilot SITL can create controlled counterfactual
experiments: keep vehicle, frame, wind, mission, and timing fixed, then compare
a sham flight with a flight containing one planned intervention. This provides
known intervention time and mechanism while avoiding risk to a real aircraft.

Synthetic data is not treated as automatically correct. A run is quarantined
unless the exact simulator revision and binary are pinned, the parameter
change is acknowledged and visible in DataFlash, the expected physical effect
appears, the log is complete, and both arms of the matched pair succeed.

## Why cloud/cluster access

The immediate need is reliable Linux compute, not a supercomputer. Genuine
SITL runs require Linux process and network namespaces that this Windows laptop
does not currently provide. A cloud VM supplies that execution environment and
lets independent matched pairs run in parallel.

GPU access becomes useful only later, if a measured GPU-enabled training
candidate is faster or enables larger experiments. The current trainer is
CPU-bound, so renting an H100 today would be wasteful. JarvisLabs is useful
because it offers inexpensive CPU VMs, optional GPUs, persistent storage,
per-minute billing, pause/resume, SSH, and reproducible custom-container tasks.

## Scientific evaluation

The project does not claim that more synthetic data automatically improves
accuracy. The preregistered question is:

> Does adding verified matched SITL data improve diagnosis on untouched,
> grouped real-flight incidents without worsening calibration, false-confident
> error, abstention behavior, or out-of-distribution safety?

The evaluation separates real incidents by lineage/source so windows from the
same flight cannot leak across training and testing. A synthetic-data candidate
must beat a real-only baseline on the frozen real lockbox, pass fidelity and
OOD checks, and finally be confirmed on a blinded physical-flight cohort by an
independent authority.

## Honest current status

The repository contains the parser, diagnosis pipeline, verified synthetic
planning/execution/collection contracts, cluster scheduling contracts,
pair-atomic protection, OOD and evidence gates, container build, and automated
tests. The JarvisLabs x86_64 publish and canary path is prepared.

Still outstanding are the first genuine live SITL sham/intervention pair on a
qualified Linux host, a real JarvisLabs deployment canary, the blinded physical
confirmation cohort, and an independently authorized release decision.
Therefore, no real-world accuracy gain is currently claimed.

