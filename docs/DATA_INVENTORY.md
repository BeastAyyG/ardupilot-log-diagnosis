# Data Inventory and Source Links

This document summarizes current log volume and provenance links in this repository.

## Snapshot

- Physical log files currently present under `data/` (`*.BIN` + `*.bin`): **199**
- Canonical labeled training set (`data/final_training_dataset_2026-02-23/ground_truth.json`): **42 logs**
- New extraction batch (`data/background_scrapes_batch`):
  - Manifest rows scanned: **137**
  - Downloaded payloads: **71**
  - Downloaded log-topic URLs (unique): **51**
  - `.bin` scanned by clean import: **41**
  - Parse-valid unique `.bin`: **40**
  - Benchmark-trainable from this batch currently: **0** (all currently unlabeled/manual-review)

## Canonical Labeled Dataset Sources (42 logs, 35 unique URLs)

Source file: `data/final_training_dataset_2026-02-23/ground_truth.json`

- https://discuss.ardupilot.org/t/3d-printed-10-inch-quad-sudden-unrecoverable-yaw/140246
- https://discuss.ardupilot.org/t/3dr-iris-crashed-after-3-successful-waypoints-mission/9269
- https://discuss.ardupilot.org/t/a-problem-about-ekf-variance-and-crash/56863
- https://discuss.ardupilot.org/t/ac-copter-3-7-dev-fell-from-the-sky-crash-log/37800
- https://discuss.ardupilot.org/t/automission-misses-wp2-flyaway-crash/19146
- https://discuss.ardupilot.org/t/copter-3-4-rc5-possible-imu-or-compass-issues/11636
- https://discuss.ardupilot.org/t/copter-crash-althold/60815
- https://discuss.ardupilot.org/t/crash-after-two-motors-suddenly-stopped/132001
- https://discuss.ardupilot.org/t/crash-analysis-strange-flight-behavior/33345
- https://discuss.ardupilot.org/t/crash-help-with-bin-analysis/42329
- https://discuss.ardupilot.org/t/crash-hexacopter-suddenly-crashed-while-auto/83521
- https://discuss.ardupilot.org/t/crash-with-4-0-0-rc3/50267
- https://discuss.ardupilot.org/t/ekf-yaw-reset-crash/107273
- https://discuss.ardupilot.org/t/ekf3-position-still-going-mad-in-beta5-drone-crashed/73859
- https://discuss.ardupilot.org/t/esc-desync-issue-hobbywing-xrotor-pro-60a-tmotor-p60/81059
- https://discuss.ardupilot.org/t/hexacopter-drifting-away-crash-log-video/26675
- https://discuss.ardupilot.org/t/how-to-make-yaw-roll-and-pitch-smoother/64483
- https://discuss.ardupilot.org/t/is-there-a-vibration-issue-here/15264
- https://discuss.ardupilot.org/t/large-10kg-payload-drone-crash-on-take-off-please-help/11083
- https://discuss.ardupilot.org/t/loiter-issue-no-mag-data-bad-motor-balance/18364
- https://discuss.ardupilot.org/t/loiter-mode-climb-drift-and-crash/7594
- https://discuss.ardupilot.org/t/major-ek2-fail-and-big-crash/19650
- https://discuss.ardupilot.org/t/motor-turned-off-in-mid-flight/121845
- https://discuss.ardupilot.org/t/no-rc-receiver-lockup-between-flight-controller-and-receiver/45811
- https://discuss.ardupilot.org/t/pixhawk-1-midair-reboot/17918
- https://discuss.ardupilot.org/t/pixhawk-clone-2-4-8-motors-not-running-in-the-same-speed/93719
- https://discuss.ardupilot.org/t/radio-failsafe-during-operation/101055
- https://discuss.ardupilot.org/t/stil-fw-4-2-0dev-crashes-the-plane-with-ahrs-ekf3-lane-switch-0-message/77702
- https://discuss.ardupilot.org/t/unstable-drone-after-takeoff-crashes/43780
- https://discuss.ardupilot.org/t/yaw-instability-and-crash-in-loiter-mode-high-vibrations-motor-imbalance-issues/130060
- https://drive.google.com/drive/folders/152GnHaxxZVOlLG433Oc9FgpRFOVJPzE3?usp=sharing
- https://github.com/ArduPilot/ardupilot/files/12009217/bug_report_1.zip
- https://github.com/ArduPilot/ardupilot/files/12101758/bin_and_telemetry_logs.zip
- https://github.com/ArduPilot/ardupilot/issues/7119
- https://github.com/ArduPilot/ardupilot/issues/8931

## New Extraction Sources (Downloaded Topic URLs, 51 unique)

Source file: `data/background_scrapes_batch/crawler_manifest.csv` (rows with `status=downloaded`)

- https://discuss.ardupilot.org/t/3-6-7-installed-and-tested-drone-crashed-firmware-issue-or-battery-or-something-else-unable-to-find-out/39722
- https://discuss.ardupilot.org/t/3dr-iris-crashed-after-3-successful-waypoints-mission/9269
- https://discuss.ardupilot.org/t/automission-misses-wp2-flyaway-crash/19146
- https://discuss.ardupilot.org/t/autotune-rc5-concerning-observations/17560
- https://discuss.ardupilot.org/t/copter-3-4-4-rc1-available-for-beta-testing/13645
- https://discuss.ardupilot.org/t/copter-3-4-rc5-possible-imu-or-compass-issues/11636
- https://discuss.ardupilot.org/t/copter-3-5-5-rc1-available-for-beta-testing/25162
- https://discuss.ardupilot.org/t/copter-crash-althold/60815
- https://discuss.ardupilot.org/t/copter-unexpected-rapid-climb-after-arming-eventually-crashed/119799
- https://discuss.ardupilot.org/t/crash-analysis-strange-flight-behavior/33345
- https://discuss.ardupilot.org/t/crash-help-with-bin-analysis/42329
- https://discuss.ardupilot.org/t/crash-hexacopter-suddenly-crashed-while-auto/83521
- https://discuss.ardupilot.org/t/crash-spinning-quad-on-pixracer-r15-arducopter-3-6-6/38666
- https://discuss.ardupilot.org/t/crash-when-switching-from-rtl-to-loiter/103732
- https://discuss.ardupilot.org/t/ekf-error-compass-variance-suddenly-until-i-land/16183
- https://discuss.ardupilot.org/t/engine-failure-bug-mechanical-or-other/77323
- https://discuss.ardupilot.org/t/esc-failure-or-signal-lost-thank-s-for-help/18093
- https://discuss.ardupilot.org/t/f35b-quadplane-test-frame-crash/107532
- https://discuss.ardupilot.org/t/failsafe-sbus-not-working/65942
- https://discuss.ardupilot.org/t/failure-to-launch/80437
- https://discuss.ardupilot.org/t/fixed-wing-dead-reckoning-test-of-the-zealot-h743-aero-applications-edition/101680
- https://discuss.ardupilot.org/t/hexacopter-drifting-away-crash-log-video/26675
- https://discuss.ardupilot.org/t/hexacopter-redundancy/72447
- https://discuss.ardupilot.org/t/how-to-make-yaw-roll-and-pitch-smoother/64483
- https://discuss.ardupilot.org/t/im-new-unable-to-take-off-on-stabilize-or-lotier/9348
- https://discuss.ardupilot.org/t/is-there-a-vibration-issue-here/15264
- https://discuss.ardupilot.org/t/loiter-mode-climb-drift-and-crash/7594
- https://discuss.ardupilot.org/t/maiden-going-perfectly-then-sudden-flip-over/12977
- https://discuss.ardupilot.org/t/major-ek2-fail-and-big-crash/19650
- https://discuss.ardupilot.org/t/motors-maxing-out-when-flight/115319
- https://discuss.ardupilot.org/t/multiple-flyaways-in-guided-do-i-need-to-tune-the-ekf/17438
- https://discuss.ardupilot.org/t/multiple-flyaways-in-loiter-and-auto/17663
- https://discuss.ardupilot.org/t/oscillation-in-roll-and-pitch-resulting-in-crash/93512
- https://discuss.ardupilot.org/t/pixhawk-1-octo-auto-takeoff-into-violent-pitch-roll-yaw-oscillations-and-bad-9k-crash/18298
- https://discuss.ardupilot.org/t/pixhawk-clone-2-4-8-motors-not-running-in-the-same-speed/93719
- https://discuss.ardupilot.org/t/pixhawk-flyaway-in-stabilized-mode-with-complete-loss-of-control/13560
- https://discuss.ardupilot.org/t/pixhawk-motor-balance-warn/33051
- https://discuss.ardupilot.org/t/possibly-a-fly-away-please-take-a-look-at-the-log/41183
- https://discuss.ardupilot.org/t/prearm-battery-1low-voltage-failsafe/80068
- https://discuss.ardupilot.org/t/prearm-crashdump-data-detected-arduplane-4-6-2/140189
- https://discuss.ardupilot.org/t/quad-flyaway-need-analysis/69210
- https://discuss.ardupilot.org/t/quadcopter-crash-log-analysis-request/99897
- https://discuss.ardupilot.org/t/quadcopter-gives-radio-failsafe-and-climbs-to-15-meters-immidiately-after-arming/99762
- https://discuss.ardupilot.org/t/radio-failsafe-during-operation/101055
- https://discuss.ardupilot.org/t/rtl-does-not-return-to-launch-nor-lands-but-kind-of-loiters/6876
- https://discuss.ardupilot.org/t/rtl-flyaway-bad-pos-among-others/53951
- https://discuss.ardupilot.org/t/solo-flyaway-and-crash-during-auto-mission/15265
- https://discuss.ardupilot.org/t/something-is-wrong-with-my-copter-build/46289
- https://discuss.ardupilot.org/t/tricopter-vtol-servos-cooking-vtol-roll-control-inverted/95543
- https://discuss.ardupilot.org/t/tuning-issues-with-plane-successful-auto-t-o-and-land-maiden-now-not-so-much/100608
- https://discuss.ardupilot.org/t/unstable-drone-after-takeoff-crashes/43780

## Notes

- `data/background_scrapes_batch` is an active extraction pool and includes unlabeled logs that are not yet benchmark-trainable.
- `data/clean_imports/background_batch_01` and `data/clean_imports/background_scrapes_01` both currently report 40 parse-valid unique logs and 0 benchmark-trainable labels.
- Counts are expected to change as more extraction and manual review proceed.
