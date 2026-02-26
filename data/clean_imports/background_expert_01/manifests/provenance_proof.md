# Benchmark Data Provenance

- Source folder: `/home/srma/Desktop/ardupilot-log-diagnosis/data/background_scrapes_batch`
- Generated at (UTC): `2026-02-26T01:14:55.078545+00:00`
- Total `.bin` files scanned: **41**
- Parse-valid `.bin` files (pre-dedupe): **40**
- Unique parse-valid files (SHA256 dedupe): **40**
- Rejected non-log `.bin` files: **0**
- Provisional labeled files (not trainable): **0**
- Unlabeled files (manual review): **30**
- Benchmark-trainable files: **10**

## Policy
- No synthetic/SITL logs used for production benchmark training.
- Provisional labels are excluded from trainable benchmark set.
- Only mapped labels are included in benchmark-ready ground truth.

## Verified Labeled Logs
| File | Raw Label | Mapped Label | Thread URL | Download URL | SHA256 |
|---|---|---|---|---|---|
| `log_0036_mechanical_failure.bin` | MECHANICAL_FAILURE | mechanical_failure | https://discuss.ardupilot.org/t/copter-3-4-4-rc1-available-for-beta-testing/13645 | https://discuss.ardupilot.org/uploads/default/original/2X/4/4410a788d8c043cf704a45ee850a6a0071d9909a.BIN | `d9464b12aaed79a5ea7f7c626bd96d83037db37018deff5c2399d078a9d155fe` |
| `log_0037_mechanical_failure.bin` | MECHANICAL_FAILURE | mechanical_failure | https://discuss.ardupilot.org/t/hexacopter-redundancy/72447 | https://www.dropbox.com/s/vf00f1dkj495oar/log_27_2021-5-1-15-46-46.bin?dl=1 | `d3ecd87205ba32a8effd9f2e78443bee25ffd0baa8be333c78bd404f641cf81f` |
| `log_0038_mechanical_failure.bin` | MECHANICAL_FAILURE | mechanical_failure | https://discuss.ardupilot.org/t/esc-failure-or-signal-lost-thank-s-for-help/18093 | https://discuss.ardupilot.org/uploads/default/original/2X/d/d69429de5eed1d724bd8643db7173e07453ee55c.BIN | `cf337b4dde9a1f203b7ceb588c591241e2acac577124e89d88f2b8783efef043` |
| `log_0039_mechanical_failure.bin` | MECHANICAL_FAILURE | mechanical_failure | https://discuss.ardupilot.org/t/esc-failure-or-signal-lost-thank-s-for-help/18093 | https://discuss.ardupilot.org/uploads/default/original/2X/0/03b63344fa64dee0ec39072ca06b47f34203c23b.BIN | `1de0bcaf777b20c7f69c2948472c1ad5e87eb34dfe40c5bbce29d77f969acdf8` |
| `log_0040_mechanical_failure.bin` | MECHANICAL_FAILURE | mechanical_failure | https://discuss.ardupilot.org/t/engine-failure-bug-mechanical-or-other/77323 | https://www.dropbox.com/s/wllzkuniarpydez/00000035.bin?dl=1 | `58f3f3b631233a6dc4c20f6d42ed47252d0c05788bd45fd57fc87074bad68778` |
| `log_0041_mechanical_failure.bin` | MECHANICAL_FAILURE | mechanical_failure | https://discuss.ardupilot.org/t/3-6-7-installed-and-tested-drone-crashed-firmware-issue-or-battery-or-something-else-unable-to-find-out/39722 | https://discuss.ardupilot.org/uploads/default/original/3X/4/2/42f32ae9f1ce3c0c09b8fb9102d210f581f4618d.bin | `1796486e9ac43407765587df16a6d0fb6577cd7bee4c76b8c82ce0196075413a` |
| `log_0042_mechanical_failure.bin` | MECHANICAL_FAILURE | mechanical_failure | https://discuss.ardupilot.org/t/fixed-wing-dead-reckoning-test-of-the-zealot-h743-aero-applications-edition/101680 | https://www.dropbox.com/s/jj3j5zdgpeqh5v0/log_56_UnknownDate.bin?dl=1 | `e3c66d3ea3e373cb384166ef0f70ed27a2aad71ded3404d56f0681ef2f9cd962` |
| `log_0043_mechanical_failure.bin` | MECHANICAL_FAILURE | mechanical_failure | https://discuss.ardupilot.org/t/fixed-wing-dead-reckoning-test-of-the-zealot-h743-aero-applications-edition/101680 | https://www.dropbox.com/s/zfv5a8i0rx6ce3w/log_57_UnknownDate.bin?dl=1 | `aac514db54f5aedc3af338ba5a94d3a5369ae4ecf33f96d0f4692b83f93fa253` |
| `log_0044_mechanical_failure.bin` | MECHANICAL_FAILURE | mechanical_failure | https://discuss.ardupilot.org/t/fixed-wing-dead-reckoning-test-of-the-zealot-h743-aero-applications-edition/101680 | https://www.dropbox.com/s/k3wwb456zmd4454/log_69_UnknownDate.bin?dl=1 | `405c8b855f571cfb58f800bb46723ff38732305f8c0e81a7d2d713feeade27bf` |
| `log_0045_mechanical_failure.bin` | MECHANICAL_FAILURE | mechanical_failure | https://discuss.ardupilot.org/t/fixed-wing-dead-reckoning-test-of-the-zealot-h743-aero-applications-edition/101680 | https://www.dropbox.com/s/0wye5b2luz6uxys/log_70_UnknownDate.bin?dl=1 | `75a2881bbec319096c2ee9bd40881910f70fcfed759995dc39f8147656602699` |

## Provisional Labels
| File | Raw Label | Reason | Thread URL | SHA256 |
|---|---|---|---|---|

## Unlabeled Valid Logs
| File | Source Path | SHA256 |
|---|---|---|
| `log_0028_battery_failsafe.bin` | `downloads/log_0028_battery_failsafe.bin` | `8edac767be66c882f4374171331c5f6d90114d82757fb59bb15abb171918df9a` |
| `log_0029_battery_failsafe.bin` | `downloads/log_0029_battery_failsafe.bin` | `0818fe7e5ce3cda47fdf3fef42cb2d02963f354b8b18750fa59edb3d0e035719` |
| `log_0030_battery_failsafe.bin` | `downloads/log_0030_battery_failsafe.bin` | `200022930ad7a751ae5777cda44b984019978f4847616c6fd1b19ee1872b0c93` |
| `log_0032_hardware_failure.bin` | `downloads/log_0032_hardware_failure.bin` | `476a5e4c28ef03599353736a46d832d0a14193e5ea3b28246aea6bc945c529ef` |
| `log_0033_hardware_failure.bin` | `downloads/log_0033_hardware_failure.bin` | `15deab36497ed66aba1b18194547f8b39e9b40d2cab58524a3654c4cee916521` |
| `log_0046_thrust_loss.bin` | `downloads/log_0046_thrust_loss.bin` | `d5095b90be9440b7ef0528d2ddbdf945f3f3f774d3517335464974cdf37fcba8` |
| `log_0047_thrust_loss.bin` | `downloads/log_0047_thrust_loss.bin` | `c55006bd101fd1d9f634eb61a56add2b9f644e29e767fbd0d5af5e0051827ad6` |
| `log_0048_oscillation_crash.bin` | `downloads/log_0048_oscillation_crash.bin` | `f7d7a771d1b12dda9e1b19c21d6e6941822d5c319beb930b89920f6bde54181e` |
| `log_0049_oscillation_crash.bin` | `downloads/log_0049_oscillation_crash.bin` | `bffc80e1da7d30ad042d9b8a0cdb06e01b0f1dbccae3589f415b1874502cb256` |
| `log_0050_oscillation_crash.bin` | `downloads/log_0050_oscillation_crash.bin` | `fa2f67b19dcbb58b7b7ac1797f44d59957fafa1f932aa06218555e3f465df0ce` |
| `log_0052_oscillation_crash.bin` | `downloads/log_0052_oscillation_crash.bin` | `b8d168d2f71525654f6737a6b2b1ec719de7655ba70415bca7c0ca921d0940e4` |
| `log_0053_oscillation_crash.bin` | `downloads/log_0053_oscillation_crash.bin` | `fb32889d51090b69f75118e7a543457993575a0a7d38e299e0e647cc3ec77040` |
| `log_0054_oscillation_crash.bin` | `downloads/log_0054_oscillation_crash.bin` | `5429897d5ff19a109ff8a5ae95a09e63a21d97b976cb36d35cfd31d114ddf55d` |
| `log_0055_oscillation_crash.bin` | `downloads/log_0055_oscillation_crash.bin` | `744e1d163202c8578dae7aca509430972ddd8e0f6ce402d9d2a94ed5e329a339` |
| `log_0056_oscillation_crash.bin` | `downloads/log_0056_oscillation_crash.bin` | `96fb229fb404f57bc4d1c4ed4b41da69a6d442a618fdae1d3208b5d9fe425b69` |
| `log_0057_oscillation_crash.bin` | `downloads/log_0057_oscillation_crash.bin` | `ca2e821c6686411f14997b427dc7ebe286aa3fa41f6262d9ddd51a0f9f3cb65e` |
| `log_0058_flyaway.bin` | `downloads/log_0058_flyaway.bin` | `396bc7ab6056c96abab9d93d615115f58c30e36a6a373565bd26e30b34cc057e` |
| `log_0059_flyaway.bin` | `downloads/log_0059_flyaway.bin` | `9ae5224970cc1340f99205a1ef807742470924352a68e606e13d0c249f6bef51` |
| `log_0060_flyaway.bin` | `downloads/log_0060_flyaway.bin` | `a4d4a24d39c3a028704f0cee08899d60c46ba43ed237662b2352fdf8d02fe0a4` |
| `log_0061_flyaway.bin` | `downloads/log_0061_flyaway.bin` | `20fe2a41c6ded85bcc36efd3337de6bf53a5c0e0a8178d481f1ecc52bb38b18e` |
| `log_0062_flyaway.bin` | `downloads/log_0062_flyaway.bin` | `c6d4e2f2539fc101acdfce3216d5cea54b9efa5e92303f7417d7f8aaa133865e` |
| `log_0063_flyaway.bin` | `downloads/log_0063_flyaway.bin` | `4be9cde3ea55c3cdabf84251ec2064591d051c71b6a4c973760ca65202e1ce40` |
| `log_0064_flyaway.bin` | `downloads/log_0064_flyaway.bin` | `01803ce998a260eb56293a2e805ce3350a9b3d1fe00fb0a90bedc149849e611e` |
| `log_0065_flyaway.bin` | `downloads/log_0065_flyaway.bin` | `b89fc87fea657312f90ca28f92e6108f42bc97cb5c27267df8fc82bdfae690c0` |
| `log_0066_flyaway.bin` | `downloads/log_0066_flyaway.bin` | `af2836cad8f18ca67758f6e45730a2756a37938dfc2f2e2dc6fbb27dca7e5641` |
| `log_0067_flyaway.bin` | `downloads/log_0067_flyaway.bin` | `b729efbac030e6071c1725cc8a06d7dbf37b7728f6f2f20c9cb805e1b893eacc` |
| `log_0068_uncontrolled_descent.bin` | `downloads/log_0068_uncontrolled_descent.bin` | `e37a094bd36b9572806acfd0701214927028bffce22d8ab38877549ba95e87a5` |
| `log_0069_radio_failsafe.bin` | `downloads/log_0069_radio_failsafe.bin` | `cdb6b1a5546b7f01c91fd16786e2cbda4d60a5f408ab1f3f7582628aa878498b` |
| `log_0070_radio_failsafe.bin` | `downloads/log_0070_radio_failsafe.bin` | `c35318e6ce5ed8bc79c3173b15fe88b912c4a6bb4c288b64c6fe18243df729bd` |
| `log_0071_radio_failsafe.bin` | `downloads/log_0071_radio_failsafe.bin` | `7b4e98a4d20fd3ec5325b0b6a964112b7a4cc8f5b3e6e1d6a4cd36a5f441a942` |

## Excluded SITL Sources
- https://github.com/ArduPilot/ardupilot/files/12223207/logs_3.zip
- https://github.com/ArduPilot/ardupilot/files/12223288/logs.zip
- https://github.com/ArduPilot/ardupilot/issues/24445

## Generated Artifacts
- `data/clean_imports/background_expert_01/manifests/source_inventory.csv`
- `data/clean_imports/background_expert_01/manifests/clean_import_manifest.csv`
- `data/clean_imports/background_expert_01/manifests/rejected_manifest.csv`
- `data/clean_imports/background_expert_01/manifests/ground_truth_candidate.json`
- `data/clean_imports/background_expert_01/benchmark_ready/ground_truth.json`
