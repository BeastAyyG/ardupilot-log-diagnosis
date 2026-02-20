import argparse
import sys
import os
import json
from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.diagnosis.hybrid_engine import HybridEngine
from src.diagnosis.rule_engine import RuleEngine
from .formatter import DiagnosisFormatter

def cmd_analyze(args):
    parser = LogParser(args.logfile)
    parsed = parser.parse()
    
    pipeline = FeaturePipeline()
    features = pipeline.extract(parsed)
    
    if args.no_ml:
        engine = RuleEngine()
    else:
        engine = HybridEngine()
        
    diagnoses = engine.diagnose(features)
    
    formatter = DiagnosisFormatter()
    metadata = features.get("_metadata", {})
    
    if args.json:
        output = formatter.format_json(diagnoses, metadata, features)
    else:
        output = formatter.format_terminal(diagnoses, metadata)
        
    if args.output:
        with open(args.output, "w") as f:
            f.write(output)
        print(f"Report saved to {args.output}")
    else:
        print(output)

def cmd_features(args):
    parser = LogParser(args.logfile)
    parsed = parser.parse()
    
    pipeline = FeaturePipeline()
    features = pipeline.extract(parsed)
    
    print(json.dumps(features, indent=2))
    
def cmd_benchmark(args):
    from src.benchmark.suite import BenchmarkSuite
    from src.benchmark.reporter import BenchmarkReporter
    
    suite = BenchmarkSuite(engine=args.engine)
    results = suite.run()
    
    reporter = BenchmarkReporter()
    reporter.print_terminal(results)
    reporter.save_markdown(results, "benchmark_results.md")
    reporter.save_json(results, "benchmark_results.json")
    print("\nSaved benchmark_results.md and benchmark_results.json")

def cmd_batch(args):
    directory = args.directory
    if not os.path.exists(directory):
        print(f"Directory {directory} not found.")
        return
        
    print(f"{'File':<25} | {'Status':<15} | {'Top Diagnosis'}")
    print("-" * 65)
    
    pipeline = FeaturePipeline()
    engine = HybridEngine()
    
    for f in os.listdir(directory):
        if not f.upper().endswith(".BIN"):
            continue
            
        filepath = os.path.join(directory, f)
        parser = LogParser(filepath)
        parsed = parser.parse()
        features = pipeline.extract(parsed)
        diagnoses = engine.diagnose(features)
        
        if not diagnoses:
            status = "HEALTHY"
            top = "None"
        else:
            status = "FAIL"
            top = f"{diagnoses[0]['failure_type']} ({int(diagnoses[0]['confidence']*100)}%)"
            
        print(f"{f:<25} | {status:<15} | {top}")

def cmd_label(args):
    logfile = args.logfile
    filename = os.path.basename(logfile)
    
    parser = LogParser(logfile)
    parsed = parser.parse()
    pipeline = FeaturePipeline()
    features = pipeline.extract(parsed)
    
    engine = HybridEngine()
    diagnoses = engine.diagnose(features)
    
    print(f"\n--- Labeling {filename} ---")
    auto_labels = features.get("_metadata", {}).get("auto_labels", [])
    if auto_labels:
        print(f"Auto-suggested labels from ERR/EV: {auto_labels}")
    
    print("\nModel Predictions:")
    if diagnoses:
        for d in diagnoses:
            print(f" - {d['failure_type']} ({int(d['confidence']*100)}%)")
    else:
        print(" - None (Healthy)")
        
    print("\nEnter correct labels (comma-separated). Uses constants.VALID_LABELS.")
    print("Leave blank to skip.")
    try:
        user_input = input("Labels > ").strip()
    except EOFError:
        user_input = ""
        
    if not user_input:
        print("Skipped.")
        return
        
    labels = [l.strip() for l in user_input.split(",")]
    
    gt_path = "ground_truth.json"
    data = {"logs": []}
    if os.path.exists(gt_path):
        with open(gt_path, "r") as f:
            data = json.load(f)
            
    data["logs"] = [l for l in data.get("logs", []) if l["filename"] != filename]
    
    data["logs"].append({
        "filename": filename,
        "labels": labels,
        "source_url": "",
        "source_type": "manual",
        "expert_quote": "",
        "confidence": "high"
    })
    
    with open(gt_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Added {filename} to {gt_path} with labels {labels}")
    
def main():
    parser = argparse.ArgumentParser(description="ArduPilot Log Diagnosis Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    p_analyze = subparsers.add_parser("analyze", help="Analyze a single log file")
    p_analyze.add_argument("logfile", help="Path to .BIN file")
    p_analyze.add_argument("--json", action="store_true", help="Output in JSON format")
    p_analyze.add_argument("-o", "--output", help="Save report to file")
    p_analyze.add_argument("--no-ml", action="store_true", help="Force rule-based only diagnosis")
    
    p_features = subparsers.add_parser("features", help="Extract and print raw features")
    p_features.add_argument("logfile", help="Path to .BIN file")
    
    p_benchmark = subparsers.add_parser("benchmark", help="Run benchmark suite")
    p_benchmark.add_argument("--engine", choices=["rule", "ml", "hybrid"], default="hybrid", help="Engine to benchmark")
    
    p_batch = subparsers.add_parser("batch", help="Batch analyze directory")
    p_batch.add_argument("directory", help="Directory containing .BIN files")
    
    p_label = subparsers.add_parser("label", help="Interactive labeling tool")
    p_label.add_argument("logfile", help="Path to .BIN file")
    
    parsed_args = parser.parse_args()
    
    if parsed_args.command == "analyze":
        cmd_analyze(parsed_args)
    elif parsed_args.command == "features":
        cmd_features(parsed_args)
    elif parsed_args.command == "benchmark":
        cmd_benchmark(parsed_args)
    elif parsed_args.command == "batch":
        cmd_batch(parsed_args)
    elif parsed_args.command == "label":
        cmd_label(parsed_args)

if __name__ == "__main__":
    main()
