import os
import hashlib
import json

def sha256_hash(fname):
    h = hashlib.sha256()
    with open(fname, "rb") as f:
        for chunk in iter(lambda: f.read(40496), b""):
            h.update(chunk)
    return h.hexdigest()

train_dir = "data/kaggle_backups/ardupilot-master-log-pool-v2"
holdout_dir = "data/holdouts/production_holdout_clean/dataset"

train_hashes = set()
for root, _, files in os.walk(train_dir):
    for f in files:
        if f.endswith(".bin"):
            train_hashes.add(sha256_hash(os.path.join(root, f)))

holdout_hashes = set()
for root, _, files in os.walk(holdout_dir):
    for f in files:
        if f.endswith(".bin"):
            h = sha256_hash(os.path.join(root, f))
            if h in train_hashes:
                print(f"CRITICAL LEAKAGE FOUND: {f} is in both train and holdout!")
                exit(1)
            holdout_hashes.add(h)

print(f"CHECK 1 PASSED: 0 Overlapping SHAs. \n  Train unique logs: {len(train_hashes)}\n  Holdout unique logs: {len(holdout_hashes)}")

with open("training/dataset_build_report.json") as f:
    report = json.load(f)
    print(f"Extraction Report: Processed={report.get('processed_logs')}, Failed={report.get('failed_extractions')}")
