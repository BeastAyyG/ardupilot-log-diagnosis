# Human spot-check of LLM thread labels

All labels in `thread_annotations.json` were assigned by an AI language model reading the forum thread. Checking this random sample of 10 (seed 20260925) lets the paper report how often a human agrees. Each check takes about 2 minutes.

**For each row:**
1. Open the link. It jumps to the post that was cited.
2. Read that post and the thread around it.
3. Write `agree`, or `disagree: <your label>`, in the last column.
4. Commit the file.

Label meanings are in `thread_annotations.json` → `labelling_guide`. Do not look at the tool's own diagnosis while checking.

| # | Log | Label (certainty) | Cited post | Your verdict |
|---|---|---|---|---|
| 1 | `0818fe7e5c` | setup_error (tentative) | [spsai](https://discuss.ardupilot.org/t/pixhawk-clone-2-4-8-motors-not-running-in-the-same-speed/93719/7) | |
| 2 | `16c0fe0044` | ekf_failure (tentative) | [priseborough](https://discuss.ardupilot.org/t/major-ek2-fail-and-big-crash/19650/3) | |
| 3 | `1796486e9a` | mechanical_failure (tentative) | [Eosbandi](https://discuss.ardupilot.org/t/3-6-7-installed-and-tested-drone-crashed-firmware-issue-or-battery-or-something-else-unable-to-find-out/39722/2) | |
| 4 | `335e9881ac` | pid_tuning_issue (explicit) | [dkemxr](https://discuss.ardupilot.org/t/esc-desync-issue-hobbywing-xrotor-pro-60a-tmotor-p60/81059/2) | |
| 5 | `66bbaf3919` | compass_interference (tentative) | [Yuri_Rage](https://discuss.ardupilot.org/t/ekf-yaw-reset-crash/107273/3) | |
| 6 | `7065a3cd0f` | mechanical_failure (tentative) | [dkemxr](https://discuss.ardupilot.org/t/crash-hexacopter-suddenly-crashed-while-auto/83521/2) | |
| 7 | `8265f254a7` | mechanical_failure (tentative) | [xfacta](https://discuss.ardupilot.org/t/crash-after-two-motors-suddenly-stopped/132001/2) | |
| 8 | `97845b23ea` | ekf_failure (explicit) | [priseborough](https://discuss.ardupilot.org/t/ekf3-position-still-going-mad-in-beta5-drone-crashed/73859/3) | |
| 9 | `af2836cad8` | setup_error (tentative) | [xfacta](https://discuss.ardupilot.org/t/radio-failsafe-during-operation/101055/2) | |
| 10 | `b9daccd263` | mechanical_failure (tentative) | [iseries](https://discuss.ardupilot.org/t/3dr-iris-crashed-after-3-successful-waypoints-mission/9269/5) | |

When done, set `reviewed_by_human: true` on the checked records and record the agreement rate in `docs/EVIDENCE_LEDGER.md`.
