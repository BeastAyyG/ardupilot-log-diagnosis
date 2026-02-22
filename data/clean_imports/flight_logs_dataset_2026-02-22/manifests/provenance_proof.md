# Benchmark Data Provenance

- Source folder: `/home/ayyg/Downloads/flight_logs_dataset_2026-02-22`
- Generated at (UTC): `2026-02-22T12:42:59.082716+00:00`
- Total `.bin` files scanned: **27**
- Parse-valid `.bin` files (pre-dedupe): **19**
- Unique parse-valid files (SHA256 dedupe): **13**
- Rejected non-log `.bin` files: **8**
- Provisional labeled files (not trainable): **2**
- Unlabeled files (manual review): **9**
- Benchmark-trainable files: **2**

## Policy
- No synthetic/SITL logs used for production benchmark training.
- Provisional labels are excluded from trainable benchmark set.
- Only mapped labels are included in benchmark-ready ground truth.

## Verified Labeled Logs
| File | Raw Label | Mapped Label | Thread URL | Download URL | SHA256 |
|---|---|---|---|---|---|
| `log_01_VIBE_HIGH.bin` | VIBE_HIGH | vibration_high | https://discuss.ardupilot.org/t/a-problem-about-ekf-variance-and-crash/56863 | https://drive.google.com/uc?export=download&id=1nNki5GiGJ3-GJOMGMv4MQEwwnopZdgUQ | `c648fe37de19bce0d6985ae04299af192287f9bd3009cbd5c69c56158cebc706` |
| `log_10_MAG_INTERFERENCE_1.bin` | MAG_INTERFERENCE | compass_interference | https://discuss.ardupilot.org/t/ekf-yaw-reset-crash/107273 | https://drive.google.com/uc?export=download&id=1z5wB1v8-RY6pFT-gDKsG_vkxZFF54oi_ | `66bbaf391960e4f5244e723b4aa7c4bd5cabc9b38a3957d781dd1d99192ca5b3` |

## Provisional Labels
| File | Raw Label | Reason | Thread URL | SHA256 |
|---|---|---|---|---|
| `log_05_ESC_DESYNC_1.bin` | ESC_DESYNC | label not in production taxonomy | https://discuss.ardupilot.org/t/cube-orange-motor-6-fails/111390 | `6c5448a716099819e2ce082a570476b1042000850fdb8633d492a453893d2727` |
| `log_11_ESC_DESYNC.bin` | ESC_DESYNC | label not in production taxonomy | https://www.dropbox.com/scl/fi/k7kk0rte8lmfcba8ehw9n/1.bin?rlkey=ul79x33dfrh6ckm32nkjxcdxt&st=p7o79clq&dl=0 | `43bd1475d82ee3a0a719faf501aea0b29645dc8af299190143677735f7b8e6cb` |

## Unlabeled Valid Logs
| File | Source Path | SHA256 |
|---|---|---|
| `log_1000_DISCOVERED_1.bin` | `discovered_downloads_v2/log_1000_DISCOVERED_1.bin` | `de9643c72dd4a59e965de0838dbfe37b1101cf27bc3a88483fbbea2321867023` |
| `log_1001_DISCOVERED_1.bin` | `discovered_downloads_v2/log_1001_DISCOVERED_1.bin` | `65459319cb48adfccc7b0263fcaedd9fa38f013e6a4ced57f7080ea8f72dff77` |
| `log_1002_DISCOVERED_1.bin` | `discovered_downloads_v2/log_1002_DISCOVERED_1.bin` | `6812222a6786acec0427b757a9a036aab23777e2fb969a4e1a3bf6e0a170baec` |
| `log_1003_DISCOVERED_1.bin` | `discovered_downloads_v2/log_1003_DISCOVERED_1.bin` | `1139d40b346f2087a1e6321eeca473486ba32c8b1ae089542ba8be41fe2596e4` |
| `log_1004_DISCOVERED_1.bin` | `discovered_downloads_v2/log_1004_DISCOVERED_1.bin` | `c6ec9e9f0006096351de6338a9384f19d0398fb101f1ebd722d6987b3c2196b6` |
| `log_1005_DISCOVERED_1.bin` | `discovered_downloads_v2/log_1005_DISCOVERED_1.bin` | `0981e19b7dc74b0c6e8c55779b4a339b2c4619c632d585e2f96e29ef5931d1a1` |
| `log_1007_DISCOVERED_1.bin` | `discovered_downloads_v2/log_1007_DISCOVERED_1.bin` | `335e9881ac2934b49da7a13c9d093cf2b2a909957338e66fa9566c4ca179c37d` |
| `log_1009_DISCOVERED_1.bin` | `discovered_downloads_v2/log_1009_DISCOVERED_1.bin` | `c8bfdfdd381ab1db9e3aba0eb966df96a656d32bad97b53e36162e074b20308d` |
| `log_1010_DISCOVERED_1.bin` | `discovered_downloads_v2/log_1010_DISCOVERED_1.bin` | `feba377ace4444b132ca77fb297f31771b8ae336885ed5a64389c048b0d23c2b` |

## Excluded SITL Sources
- https://github.com/ArduPilot/ardupilot/files/12223207/logs_3.zip
- https://github.com/ArduPilot/ardupilot/files/12223288/logs.zip
- https://github.com/ArduPilot/ardupilot/issues/24445

## Generated Artifacts
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/source_inventory.csv`
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/clean_import_manifest.csv`
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/rejected_manifest.csv`
- `data/clean_imports/flight_logs_dataset_2026-02-22/manifests/ground_truth_candidate.json`
- `data/clean_imports/flight_logs_dataset_2026-02-22/benchmark_ready/ground_truth.json`
