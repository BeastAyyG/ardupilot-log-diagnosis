# Goal 10 — JarvisLabs GPU Value Benchmark

## Objective

Determine whether any JarvisLabs GPU reduces training cost or wall time for
this project without weakening the frozen scientific evaluation contract.

## Preconditions

- Frozen real-incident split and source-bound CPU baseline
- Enough accepted data to make training time measurable
- Candidate code exposes an explicit XGBoost CUDA configuration rather than
  silently changing the baseline

## Work

1. Record CPU baseline wall time, total cost, macro-F1, ECE/calibration,
   abstention/FCR, OOD metrics, peak memory, and exact source/data hashes.
2. Implement a separate candidate using supported XGBoost CUDA settings.
3. Start with the cheapest fitting live offer (L4 or A30), not A100/H100.
4. Use the same frozen split, seeds, search budget, lineage weights, and gates.
5. Run at least three timing repetitions after one warm-up; include setup and
   data-transfer time in cost.
6. Retain the GPU path only if it has a measured cost/time advantage and does
   not regress any acceptance gate.

## Acceptance criteria

- Baseline and candidate bind identical data/split/search inputs.
- GPU utilization is measured; an idle GPU is an automatic rejection.
- Results include per-run Jarvis price, minutes, and total cost.
- Candidate is not promoted without the existing independent release authority.

## Expected likely result today

The current `train_model.py` is CPU-bound (`n_jobs=1`, no CUDA device), so a
GPU instance should not be rented until the explicit candidate exists.

