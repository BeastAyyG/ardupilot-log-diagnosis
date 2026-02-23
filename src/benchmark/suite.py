import os
import json
import argparse
from .results import BenchmarkResults
from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.diagnosis.rule_engine import RuleEngine
from src.diagnosis.ml_classifier import MLClassifier
from src.diagnosis.hybrid_engine import HybridEngine
import subprocess
import sys
import shlex


def _diagnose_file(dataset_dir: str, filename: str, engine_type: str) -> list:
    """Helper used by subprocess to diagnose a single log and return predictions.

    This function is intentionally lightweight so it can be executed in a fresh
    Python interpreter; large objects will be freed when the process exits.
    """
    filepath = os.path.join(dataset_dir, filename)
    pipeline = FeaturePipeline()

    parser = LogParser(filepath)
    parsed = parser.parse()
    features = pipeline.extract(parsed)

    if engine_type == "ml":
        engine = MLClassifier()
        if not engine.available:
            return []
        return engine.predict(features)
    elif engine_type == "rule":
        engine = RuleEngine()
        return engine.diagnose(features)
    else:
        engine = HybridEngine()
        return engine.diagnose(features)


if __name__ == "__main__":
    # support a lightweight CLI for processing a single log via subprocess
    parser = argparse.ArgumentParser(description="BenchmarkSuite single-log helper")
    parser.add_argument("--dataset-dir", required=True)
    parser.add_argument("--filename", required=True)
    parser.add_argument("--engine", choices=["ml", "rule", "hybrid"], default="hybrid")
    args = parser.parse_args()
    preds = _diagnose_file(args.dataset_dir, args.filename, args.engine)
    sys.stdout.write(json.dumps(preds))
    sys.exit(0)

class BenchmarkSuite:
    """Runs diagnosis engine against labeled dataset and produces accuracy metrics."""
    
    def __init__(
        self,
        dataset_dir: str = "dataset/",
        ground_truth_path: str = "ground_truth.json",
        engine: str = "hybrid",
        include_non_trainable: bool = False,
    ):
        self.dataset_dir = dataset_dir
        self.ground_truth_path = ground_truth_path
        self.engine_type = engine
        self.include_non_trainable = include_non_trainable
        
        if self.engine_type == "rule":
            self.engine = RuleEngine()
        elif self.engine_type == "ml":
            self.engine = MLClassifier()
        else:
            self.engine = HybridEngine()
            
    def run(self) -> BenchmarkResults:
        results = BenchmarkResults()
        
        if not os.path.exists(self.ground_truth_path):
            print(f"Error: {self.ground_truth_path} not found.")
            return results
            
        with open(self.ground_truth_path, 'r') as f:
            data = json.load(f)
            
        logs = data.get("logs", [])

        # use external process for each log to avoid transient spikes
        for log_entry in logs:
            if not self.include_non_trainable and log_entry.get("trainable") is False:
                continue

            filename = log_entry["filename"]
            ground_truth = log_entry["labels"]
            filepath = os.path.join(self.dataset_dir, filename)

            if not os.path.exists(filepath):
                results.add_error(filename, "File not found")
                continue

            # indicate progress so the user knows we're still working
            print(f"Processing log {filename} ({self.engine_type})...")

            # run diagnosis in a separate interpreter to isolate memory
            cmd = [
                sys.executable,
                "-m",
                "src.benchmark.suite",
                "--dataset-dir",
                str(self.dataset_dir),
                "--filename",
                filename,
                "--engine",
                self.engine_type,
            ]
            try:
                completed = subprocess.run(cmd, capture_output=True, text=True, check=True)
                predictions = json.loads(completed.stdout)
                results.add_result(filename, ground_truth, predictions, None)
            except subprocess.CalledProcessError as e:
                results.add_error(filename, e.stderr or str(e), "SUBPROCESS_FAILED")
            except Exception as e:
                results.add_error(filename, str(e), "DIAGNOSIS_FAILED")

        return results
