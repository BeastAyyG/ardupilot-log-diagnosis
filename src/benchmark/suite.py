import os
import json
from .results import BenchmarkResults
from src.parser.bin_parser import LogParser
from src.features.pipeline import FeaturePipeline
from src.diagnosis.rule_engine import RuleEngine
from src.diagnosis.ml_classifier import MLClassifier
from src.diagnosis.hybrid_engine import HybridEngine


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

        with open(self.ground_truth_path, "r") as f:
            data = json.load(f)

        logs = data.get("logs", [])
        pipeline = FeaturePipeline()

        for log_entry in logs:
            if not self.include_non_trainable and log_entry.get("trainable") is False:
                continue

            filename = log_entry["filename"]
            ground_truth = log_entry["labels"]
            filepath = os.path.join(self.dataset_dir, filename)

            if not os.path.exists(filepath):
                results.add_error(filename, "File not found")
                continue

            parser = LogParser(filepath)

            try:
                parsed = parser.parse()
                if not parsed.get("messages"):
                    raise Exception("Parsed empty messages dict")
                features = pipeline.extract(parsed)
            except Exception as e:
                results.add_error(filename, str(e), "EXTRACTION_FAILED")
                continue

            try:
                if self.engine_type == "ml":
                    if isinstance(self.engine, MLClassifier):
                        predictions = self.engine.predict(features)
                    else:
                        predictions = []
                else:
                    if isinstance(self.engine, (RuleEngine, HybridEngine)):
                        predictions = self.engine.diagnose(features)
                    else:
                        predictions = []

                results.add_result(filename, ground_truth, predictions, len(features))
            except Exception as e:
                results.add_error(filename, str(e), "DIAGNOSIS_FAILED")

        return results
