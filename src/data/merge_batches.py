import os
import json
import shutil
import hashlib
from pathlib import Path

def get_file_hash(path):
    hash_sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

def merge_datasets(data_root, output_dir):
    data_root = Path(data_root)
    output_dir = Path(output_dir)
    output_dataset = output_dir / "dataset"
    output_dataset.mkdir(parents=True, exist_ok=True)
    
    master_logs = []
    seen_hashes = {} # hash -> filename
    filename_to_path = {}
    
    # Build global index of ALL .bin and .zip files across data/
    print(f"[*] Indexing all .bin/.zip files in {data_root}...")
    for bin_path in data_root.glob("**/*.bin"):
        if "master_pool" in str(bin_path): continue
        # Prefer the one in final_training_dataset (most processed)
        existing = filename_to_path.get(bin_path.name)
        if existing is None or "final_training_dataset" in str(bin_path):
            filename_to_path[bin_path.name] = bin_path
    for zip_path in data_root.glob("**/*.zip"):
        if "master_pool" in str(zip_path): continue
        if zip_path.name not in filename_to_path:
            filename_to_path[zip_path.name] = zip_path

    print(f"[*] Found {len(filename_to_path)} unique filenames in index.")
    print(f"[*] Scanning for ground_truth.json files...")

    # Prioritize the highest-quality ground truth first (final_training_dataset)
    gt_files = sorted(
        data_root.glob("**/ground_truth.json"),
        key=lambda p: (0 if "final_training_dataset" in str(p) else 1)
    )
    
    for gt_path in gt_files:
        if "master_pool" in str(gt_path): continue
        print(f"  -> {gt_path}")
        try:
            with open(gt_path, 'r') as f:
                data = json.load(f)
            
            for log_entry in data.get("logs", []):
                filename = log_entry["filename"]
                source_file = filename_to_path.get(filename)
                
                if not source_file or not source_file.exists():
                    continue  # Silent skip — file just not on disk for this batch
                
                file_hash = get_file_hash(source_file)
                
                if file_hash in seen_hashes:
                    continue  # Silent dedup — same content already added
                
                # Handle filename collisions (same name, different hash)
                target_name = filename
                if (output_dataset / target_name).exists():
                    target_name = f"{file_hash[:8]}_{filename}"
                    log_entry = dict(log_entry)
                    log_entry["filename"] = target_name
                
                shutil.copy2(source_file, output_dataset / target_name)
                master_logs.append(log_entry)
                seen_hashes[file_hash] = target_name
                
        except Exception as e:
            print(f"  [Error] {gt_path}: {e}")

    # Compute label distribution
    label_dist = {}
    for entry in master_logs:
        for lbl in entry.get("labels", []):
            label_dist[lbl] = label_dist.get(lbl, 0) + 1

    master_gt = {
        "metadata": {
            "description": "Master Merged Dataset with hash-based deduplication",
            "total_logs": len(master_logs),
            "label_distribution": label_dist,
            "policy": {"fabricated_labels": False, "sha_deduped": True}
        },
        "logs": master_logs
    }
    
    with open(output_dir / "ground_truth.json", "w") as f:
        json.dump(master_gt, f, indent=2)
        
    print(f"\n✅ Merged {len(master_logs)} unique logs into {output_dir}")
    print(f"   Label distribution: {label_dist}")

if __name__ == "__main__":
    merge_datasets("data", "data/master_pool")
