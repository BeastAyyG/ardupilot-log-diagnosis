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
| 15 | 20260854 | [32923335678](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32923335678) | success | `bab06cbb…` (`sitl-pair:880323d29d8722eea819`) | 2 |
| 16 | 20260855 | [32923845412](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32923845412) | success | `ee99466f…` (`sitl-pair:df9c743682d83183fe25`) | 8 |
| 17 | 20260856 | [32924539428](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32924539428) | success | `444b408d…` (`sitl-pair:c1b1cb2a9cd5c6a5a139`) | 4 |
| 18 | 20260857 | [32925103762](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32925103762) | success | `f1d7efa9…` (`sitl-pair:a4e8334c3b654701598c`) | 1 |
| 19 | 20260858 | [32925723546](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32925723546) | success | `ffa8c444…` (`sitl-pair:596bf260f17845588336`) | 4 |
| 20 | 20260859 | [32926395136](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32926395136) | success | `a0ac4c06…` (`sitl-pair:eff4db43fd1e04ff0ae1`) | 8 |
| 21 | 20260860 | [32927001547](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32927001547) | success | `9a50f4cb…` (`sitl-pair:ceb64b4ba7125af6d83a`) | 2 |
| 22 | 20260861 | [32927643409](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32927643409) | success | `fb1cd213…` (`sitl-pair:7e7799d0dffb47993522`) | 4 |
| 23 | 20260862 | [32928341829](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32928341829) | success | `de31842f…` (`sitl-pair:1a81b3aac0f13150b62c`) | 8 |
| 24 | 20260863 | [32932908315](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32932908315) | success | `2b4a9850…` (`sitl-pair:c988677406a08f33cddc`) | 8 |
| 25 | 20260864 | [32933550207](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32933550207) | success | `eb86c33f…` (`sitl-pair:fe156cac524729c3e098`) | 1 |
| 26 | 20260865 | [32934177901](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32934177901) | success | `5c16f442…` (`sitl-pair:e16f3d64d21fb9307be9`) | 1 |
| 27 | 20260866 | [32934983958](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32934983958) | success | `10858470…` (`sitl-pair:c3e97e517a6aa52c6543`) | 8 |
| 28 | 20260867 | [32935586727](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32935586727) | success | `89e93135…` (`sitl-pair:3ddab99db4fd2c056faf`) | 4 |
| 29 | 20260868 | [32936356766](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32936356766) | success | `429338ce…` (`sitl-pair:0bcfc63bbae05eaa485d`) | 1 |
| 30 | 20260869 | [32937065655](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32937065655) | success | `f2638625…` (`sitl-pair:0391aaf4bf2ed93745c7`) | 2 |
| 31 | 20260870 | [32937864402](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32937864402) | success | `91982ff1…` (`sitl-pair:145100a457902d758525`) | 4 |
| 32 | 20260871 | [32938517131](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32938517131) | success | `5519cb01…` (`sitl-pair:e40f0c570372ad1948a6`) | 1 |
| 33 | 20260872 | [32939258245](https://github.com/BeastAyyG/ardupilot-log-diagnosis/actions/runs/32939258245) | success | `d85af4ea…` (`sitl-pair:555df19a67859c17bb65`) | 1 |

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
(tag `overlay-src-tree-fix`).

## Exit criterion: MET (2026-08-26)

Rows 14* through 33 are **20 consecutive qualified pairs** on the pinned
runtime above: every pair completed end to end, produced valid `.BIN`
logs sealed with a `logdiagnosis.pair-commit/v1` commit whose member
receipt hashes were independently re-verified, and required zero manual
intervention. The one intervening event (row "—") was a scientific
rejection that reset the streak before the detector fix; the count of 20
starts at row 14*.

Motor-failure bitmask diversity across the streak: motors 1, 2, 4, 8.
No accuracy claim is made or implied by this ledger. Goal 2 (real-data
cohort definition) is the next goal per the execution order.
