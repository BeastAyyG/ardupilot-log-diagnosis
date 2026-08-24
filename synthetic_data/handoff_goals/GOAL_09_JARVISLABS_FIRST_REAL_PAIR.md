# Goal 09 — First Genuine JarvisLabs SITL Pair

## Objective

Execute and collect one matched sham/intervention pair using the qualified
JarvisLabs image, with every provenance and pair-atomicity gate enforced.

## Preconditions

- Goal 08 canary passed on the exact image digest.
- Live parameter inventory captured from the same pinned build.
- Parameter schema binds the same full commit and binary SHA256.
- Results path is under `/home` or `/home/jl_fs` and has enough free space.

## Work

1. Plan one supported scenario with `--runs-per-scenario 1`.
2. Run sham and intervention sequentially in the same worker/container.
3. Do not retry missing manifestation or another scientific failure.
4. Promote neither arm until both execution receipts succeed.
5. Write one `logdiagnosis.pair-commit/v1` pointer binding both exact receipt hashes.
6. Run collection with `commits/` present.
7. In a copied test directory, remove the pointer and separately tamper one
   receipt hash; prove collection rejects both cases.
8. Download and independently hash all artifacts before pausing the VM.

## Acceptance criteria

- Exactly two new DataFlash BIN logs and two execution receipts exist.
- Every receipt binds image digest, commit/tree/submodules, binary, manifest,
  parameter schema, namespace proof, command, parameter file, and stable log.
- Both scenario manifestation and temporal/onset checks pass.
- One pair-commit binds both on-disk receipt SHA256 values.
- Missing/tampered pair commits fail closed.
- Collection marks no surviving half-pair trainable.

## Do not claim

One accepted pair proves the execution chain, not distributional fidelity or
an accuracy gain.

