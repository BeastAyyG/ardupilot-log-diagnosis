# SITL Pair Reliability Ledger — Goal 1 Exit Criterion

Updated: 2026-08-26

Exit criterion: 20 consecutive paired sham/fault runs complete end to end,
produce valid `.BIN` logs, are sealed in the lineage tracker (pair-commit
`logdiagnosis.pair-commit/v1`), and require zero manual intervention.

Pinned runtime: `ghcr.io/beastayyg/ardupilot-log-diagnosis@sha256:ced6a0b642a24203a2212208b0f0c3883da5e555af8010a53fb939b1d99add83`
(tag `overlay-parm-echo-fix`, build run `32908296279`, branch head includes
`d01f80c`, `beeddc7`, `7ae12ba`, `ca86840`).

Per-pair verification performed on each downloaded artifact:

- workflow conclusion = success;
- collection receipt: `accepted=2`, `trainable=true`, `rejected=[]`;
- exactly one sealed `logdiagnosis.pair-commit/v1` with two members;
- both member receipt SHA256 hashes independently re-hashed and matched;
- both members `status=completed`, exit code 0, stable log, log hash/size
  bound, loopback-only network namespace;
- fault member carries a `SIM_ENGINE_FAIL` acknowledgement; sham has none;
- DataFlash contains explicit `Disarming motors` events in both logs.

## Ledger

| # | Seed | Run | Conclusion | Pair commit (lineage root) | FAIL mask |
|---|------|-----|-----------|----------------------------|-----------|
| 1 | 20260840 | [32908475774](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32908475774) | success | `b6ffb1ca…` (`sitl-pair:ca79bd167b110398da25`) | 1 |
| 2 | 20260841 | [32910123632](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32910123632) | success | `9f657740…` (`sitl-pair:7e1137a163bdc5cd47f3`) | 4 |
| 3 | 20260842 | [32910911192](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32910911192) | success | `fe108e2b…` (`sitl-pair:358e2fbb94c489aaf9c1`) | 1 |
| 4 | 20260843 | [32911806337](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32911806337) | success | `0498add0…` (`sitl-pair:9f8ce6d644083a8c376e`) | 4 |
| 5 | 20260844 | [32912619979](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32912619979) | success | `c17b383b…` (`sitl-pair:a3c089fba4e23fe1d0d8`) | 4 |
| 6 | 20260845 | [32913376471](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32913376471) | success | `ad47f9f2…` (`sitl-pair:c9845ba58a041aa93d23`) | 4 |
| 7 | 20260846 | [32914178647](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32914178647) | success | `1fd17fc3…` (`sitl-pair:2dae8cd494d78929efe4`) | 8 |
| 8 | 20260847 | [32914895952](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32914895952) | success | `616791ae…` (`sitl-pair:d99a9cd67c4baae32910`) | 1 |
| 9 | 20260848 | [32915606207](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32915606207) | success | `4c28cc0b…` (`sitl-pair:66b93dd358fe8e5cc671`) | 2 |
| 10 | 20260849 | [32916280984](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32916280984) | success | `b49488d2…` (`sitl-pair:200de849af848fe60189`) | 1 |
| 11 | 20260850 | [32916978278](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32916978278) | success | `1b140ac5…` (`sitl-pair:058f00af4ea167ae51b8`) | 4 |
| 12 | 20260851 | [32917715990](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32917715990) | success | `c6ab7c6e…` (`sitl-pair:b9dcd9d863f659ad5c74`) | 1 |
| 13 | 20260852 | [32918319550](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32918319550) | success | `821397ab…` (`sitl-pair:2d201c3cfe3c97e1d702`) | 2 |
| — | 20260853 | [32919011601](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32919011601) | rejected | `657d7f34…` (`sitl-pair:213c6ee76196ff10ae63`) | 4 |
| 14* | 20260853 | [32922568455](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32922568455) | success | `c5fff0a8…` (`sitl-pair:213c6ee76196ff10ae63`) | 4 |

Row "—" is a scientific rejection: the injection was acknowledged but the
gated detector missed the physical response under a turbulent baseline
(streak reset per the exit criterion). The fault DID manifest — the failed
motor's channel mean rose 1538→1845 µs while per-sample extremes stayed
turbulence-dominated. Row 14* re-ran the identical plan after adding the
`motor_mean_spread` evidence rule (channel-mean imbalance, thresholds
unchanged) and median-of-three pre-window baselines; the same-seed flight
then passed collection cleanly. Detector fix commits: `7ae12ba` lineage,
`ca86840`, `b9d2cd6`, plus overlay `src/`-tree fix `fb6b686`
(overlay previously shipped only `synthetic_data`, so `src/` fixes did not
reach the container — regression-tested now).

Current pinned runtime:
`ghcr.io/beastayyg/ardupilot-log-diagnosis@sha256:1c801e2e08d744a08775d1656166d130b002ca84e964281b20f22fd97c56a5f5`
(tag `overlay-src-tree-fix`). Consecutive streak on this image: **1 / 20**
(row 14*).

Interim status: **13 consecutive qualified pairs** on
`sha256:ced6a0b642a24203a2212208b0f0c3883da5e555af8010a53fb939b1d99add83`
before one scientific rejection; zero manual interventions throughout.
Motor-failure bitmask diversity observed: motors 1, 2, 4, 8. No accuracy
claim is made or implied by this ledger.
