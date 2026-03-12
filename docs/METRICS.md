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
