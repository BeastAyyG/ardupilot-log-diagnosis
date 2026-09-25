# Datasheet: ArduPilot Real-Failure Log Benchmark v3

This datasheet follows the questions of *Datasheets for Datasets* (Gebru et al., 2021).

## Motivation

- **Purpose.** To measure how well a tool can name the root cause of a real ArduPilot crash from its DataFlash log, using labels that can be traced to a written diagnosis. The benchmark was built after an audit found that earlier scores for this project came from simulated flights, from training logs, or from labels written by its own rule engine (`CORRECTIONS.md`).
- **Creator and funding.** Built by the repository maintainer. There was no external funding.

## Composition

| Property | Value |
|---|---|
| Logs | 34 DataFlash `.bin` logs from real flights |
| Incidents (forum threads) | 32 |
| Classes | 12 root-cause labels (`benchmark_v3_summary.json`) |
| Label certainty | 14 explicit, 20 tentative |
| Vehicles | Mostly multicopters; 5 plane or rover logs |
| Thread years | 2016–2025 |
| Log size | 0.14–52 MB each; 204 MB in total |

**Label distribution.** The largest class is `mechanical_failure`, with 10 logs. Six classes have only 1 or 2 logs. Classes with fewer than 5 examples are flagged as unreliable in every result.

**Each log provides:**
- SHA256;
- source thread;
- download URL;
- label and certainty;
- permalink to the diagnosing post;
- verbatim quote from that post (`thread_annotations*.json`).

**Derived data.** Window-level features are in `derived_v3/`: 111 features per 5 s window with 50% overlap.

**Excluded logs:**
- simulated flights;
- incidents whose threads give conflicting labels;
- logs whose cited source contradicts the label;
- threads with no diagnosis (14 in the pool);
- threads describing no failure (9);
- causes outside the taxonomy (1).

**Confidential or personal data.** Logs can contain GPS tracks of the flight location. Forum usernames appear in the annotations because they identify the cited post. No other personal data is collected.

## Collection

**Where the logs come from.** Public ArduPilot Discourse threads (`discuss.ardupilot.org`) where a user posted a crash log and asked for help. Some attachments are hosted on Dropbox or Google Drive.

**How logs were selected:**
- Logs listed in the sealed cohort manifest (`data/cohorts/cohort_manifest.json`, seal `e68b962a…`).
- Logs from its unlabelled `adaptation_pool` cohort, for which a diagnosis was later found in the thread.

**Time frame.** Threads span 2016–2025. The logs were retrieved in 2025–2026.

## Labelling

1. For each log, an automated LLM annotator read the full source thread.
2. It recorded the post that diagnosed the crash, with author, permalink and verbatim quote, and assigned one label from the taxonomy in `thread_annotations.json` → `labelling_guide`.
3. Every quote is checked against the live thread by `training/verify_thread_annotations.py`. All 83 of 83 quotes verify.
4. Agreement with the pre-audit labels is Cohen's κ = 0.39.

**Human review.** Human review is pending (`SPOT_CHECK.md`). Until it is done, labels must be described as LLM-annotated.

**Label source.** Labels never come from the diagnosis tool under test (`CORRECTIONS.md`, C8).

## Preprocessing

- Logs are parsed with pymavlink.
- Features are computed per window by `training/build_dataset.py`.
- Raw logs are not modified.

## Uses

**Intended uses:**
- benchmarking root-cause classifiers on real crashes;
- studying evaluation leakage.

**Required protocol.** Always group splits by `incident_id`. The pre-registered study shows that random window splits inflate macro-F1 from about 0.06 to 0.97 (`docs/EVIDENCE_LEDGER.md`).

**Not suitable for:**
- certifying a tool as safe;
- estimating per-class accuracy for classes with fewer than 5 logs.

## Distribution

**What is released:** the registry, labels, quotes, derived features and results. The release bundle is built with `training/make_release_bundle.py`.

**Raw logs are not redistributed.** Their licence is unverified (`licence_status = unverified`). Run `training/hydrate_benchmark.py` to download them from their public sources and check each SHA256.

**Availability.** On 2026-09-25, 33 of 34 logs downloaded and verified. The missing one (`335e9881ac`) has a Google Drive link that now returns 404.

**Licences.** Code: MIT. Annotations and derived data: same terms as the repository.

## Maintenance

- **Maintainer.** The repository maintainer. Report issues on GitHub.
- **Corrections.** Every correction is logged in `CORRECTIONS.md`.
- **Next version.** v4 will add new incidents under a separate pre-registration (`docs/PREREGISTRATION_V4.md`).
