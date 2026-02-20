"""
Build training dataset from labeled .BIN logs.
Usage: python training/build_dataset.py
"""
import os
import json
import csv
from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.constants import FEATURE_NAMES, VALID_LABELS

def build():
    ground_truth_path = "ground_truth.json"
    output_features = "training/features.csv"
    output_labels = "training/labels.csv"
    dataset_dir = "dataset/"
    
    if not os.path.exists(ground_truth_path):
        print(f"File not found: {ground_truth_path}")
        return
        
    with open(ground_truth_path, 'r') as f:
        data = json.load(f)
        
    logs = data.get("logs", [])
    if not logs:
        print("No logs found in ground truth.")
        return
        
    pipeline = FeaturePipeline()
    feature_rows = []
    label_rows = []
    
    total = 0
    failed = 0
    
    for log_entry in logs:
        filename = log_entry.get("filename")
        labels = log_entry.get("labels", [])
        
        filepath = os.path.join(dataset_dir, filename)
        if not os.path.exists(filepath):
            print(f"Skipping {filename}: File not found in {dataset_dir}")
            continue
            
        parser = LogParser(filepath)
        parsed = parser.parse()
        if not parsed["messages"]:
            print(f"Skipping {filename}: Failed to parse or empty.")
            failed += 1
            continue
            
        features = pipeline.extract(parsed)
        
        feat_row = [features.get(name, 0.0) for name in FEATURE_NAMES]
        label_row = [1 if label in labels else 0 for label in VALID_LABELS]
        
        feature_rows.append(feat_row)
        label_rows.append(label_row)
        total += 1
        
    os.makedirs(os.path.dirname(output_features), exist_ok=True)
    
    with open(output_features, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(FEATURE_NAMES)
        writer.writerows(feature_rows)
        
    with open(output_labels, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(VALID_LABELS)
        writer.writerows(label_rows)
        
    print(f"Dataset Built Successfully!")
    print(f"Total Logs Processed: {total}")
    print(f"Failed Extractions: {failed}")
    print(f"Features saved to: {output_features}")
    print(f"Labels saved to: {output_labels}")

if __name__ == "__main__":
    build()
