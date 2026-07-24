# Production Acceptance Criteria & Labeling Policy

## 1. Target Release Gates (Final Acceptance Criteria)
The following metrics must be met or exceeded on the primary unseen holdout set (N >= 50 logs) for production sign-off:

The current 22-flight saved holdout does not satisfy the minimum production
sample-size requirement, and its top-label ECE is 0.1268. Production sign-off
is therefore not granted; see `TRUSTWORTHINESS_AUDIT_2026-07-24.md`.

| Metric | Target | Rationale |
|---|---|---|
| **Top-1 Diagnosis Accuracy** | >= 85% | Ensure the most likely cause is correct for the user. |
| **Macro F1 Score** | >= 0.70 | Ensure balanced performance across all failure types (not just vibration). |
| **ECE (Expected Calibration Error)** | <= 0.08 | Confidence levels must meet the same calibration gate used by the model card and release report. |
| **False-Critical Rate (FCR)** | <= 5% | Avoid "crying wolf" on healthy vehicles with high-vibration warn levels. |

## 2. Authoritative Labeling Policy
To handle cascading failures (e.g., vibration leading to EKF failure), we adopt the **Root-Cause Precedence** policy:

1. **Earliest Onset Wins**: The diagnosis is labeled based on the earliest anomaly detected in the telemetry (`tanomaly`).
2. **Sequential Causal Chains**: If A causes B, label A. (Example: `vibration_high` causing `ekf_failure` -> Label: `vibration_high`).
3. **Temporal Tie-Breaking**: If onsets are within 5 seconds, the label supported by the clearest physical evidence (highest rule confidence) or ML probability takes precedence.
4. **Relabeling Decision**: All "Expert" labels in the training pool will be audited against this policy. If a maintainer labeled "EKF Failure" but the vibration data shows 80m/s² peaks starting 30 seconds prior, the record will be relabeled as `vibration_high`.

## 3. Unseen Holdout Strategy
- **Isolation**: Holdout logs are strictly SHA-deduped against training data.
- **Diversity**: The set must contain at least 2 examples of every `VALID_LABEL`.
- **Independent Review**: Production holdout ground truth must be verified by two independent human reviewers with ArduPilot log-analysis experience. Forum quotes are provenance evidence, not a substitute for two-reviewer verification.

## 4. Production Bar for Sign-Off
- All "Level P0" and "Level P1" tasks in `PLAN-gsoc-architecture.md` are complete.
- "Hybrid" engine logic outperforms "Rule-only" baseline by at least 15% Macro F1.
- CLI output passes user-readability audit.
