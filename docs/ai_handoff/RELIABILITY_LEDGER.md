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

Interim status: **10 / 20 consecutive qualified pairs**, zero manual
intervention. Motor-failure bitmask diversity observed: motors 1, 2, 4, 8.
No accuracy claim is made or implied by this ledger.
