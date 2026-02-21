import os
import random
import sys
from typing import Dict, List, Optional

import pandas as pd

if __package__ in (None, ""):
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.features.pipeline import FeaturePipeline
from src.parser.bin_parser import LogParser


def generate_synthetic_rows(num_samples: int, seed: int = 42) -> List[Dict[str, float]]:
    """
    Generate synthetic feature rows.
    Targets:
    0 - healthy
    1 - vibration_high
    2 - compass_interference
    3 - battery_sag
    """
    rng = random.Random(seed)
    rows: List[Dict[str, float]] = []

    for idx in range(num_samples):
        prob = rng.random()

        if prob < 0.60:
            # Healthy
            row = {
                "vibe_x_max": rng.uniform(5, 15),
                "vibe_y_max": rng.uniform(5, 15),
                "vibe_z_max": rng.uniform(10, 25),
                "vibe_clip_total": 0.0,
                "mag_field_range": rng.uniform(40, 150),
                "mag_field_std": rng.uniform(10, 60),
                "bat_volt_min": rng.uniform(11.0, 12.6),
                "bat_volt_range": rng.uniform(0.1, 0.6),
                "bat_curr_max": rng.uniform(5.0, 30.0),
                "gps_fix_pct": rng.uniform(98.0, 100.0),
                "gps_hdop_max": rng.uniform(0.5, 2.2),
                "gps_nsats_min": rng.uniform(10.0, 17.0),
                "motor_spread_max": rng.uniform(40.0, 150.0),
                "motor_output_std": rng.uniform(10.0, 60.0),
                "target": 0,
            }
        elif prob < 0.75:
            # High vibration
            row = {
                "vibe_x_max": rng.uniform(20, 45),
                "vibe_y_max": rng.uniform(20, 45),
                "vibe_z_max": rng.uniform(35, 70),
                "vibe_clip_total": rng.uniform(5, 120),
                "mag_field_range": rng.uniform(40, 150),
                "mag_field_std": rng.uniform(10, 60),
                "bat_volt_min": rng.uniform(11.0, 12.6),
                "bat_volt_range": rng.uniform(0.2, 0.8),
                "bat_curr_max": rng.uniform(10.0, 45.0),
                "gps_fix_pct": rng.uniform(95.0, 100.0),
                "gps_hdop_max": rng.uniform(0.8, 2.5),
                "gps_nsats_min": rng.uniform(9.0, 16.0),
                "motor_spread_max": rng.uniform(50.0, 170.0),
                "motor_output_std": rng.uniform(15.0, 80.0),
                "target": 1,
            }
        elif prob < 0.90:
            # Compass interference
            row = {
                "vibe_x_max": rng.uniform(5, 15),
                "vibe_y_max": rng.uniform(5, 15),
                "vibe_z_max": rng.uniform(10, 25),
                "vibe_clip_total": 0.0,
                "mag_field_range": rng.uniform(350, 800),
                "mag_field_std": rng.uniform(120, 240),
                "bat_volt_min": rng.uniform(11.0, 12.6),
                "bat_volt_range": rng.uniform(0.1, 0.6),
                "bat_curr_max": rng.uniform(5.0, 30.0),
                "gps_fix_pct": rng.uniform(95.0, 100.0),
                "gps_hdop_max": rng.uniform(0.8, 2.8),
                "gps_nsats_min": rng.uniform(8.0, 15.0),
                "motor_spread_max": rng.uniform(40.0, 150.0),
                "motor_output_std": rng.uniform(10.0, 60.0),
                "target": 2,
            }
        else:
            # Battery sag
            row = {
                "vibe_x_max": rng.uniform(5, 15),
                "vibe_y_max": rng.uniform(5, 15),
                "vibe_z_max": rng.uniform(10, 25),
                "vibe_clip_total": 0.0,
                "mag_field_range": rng.uniform(40, 150),
                "mag_field_std": rng.uniform(10, 60),
                "bat_volt_min": rng.uniform(8.0, 10.5),
                "bat_volt_range": rng.uniform(1.2, 3.0),
                "bat_curr_max": rng.uniform(35.0, 80.0),
                "gps_fix_pct": rng.uniform(95.0, 100.0),
                "gps_hdop_max": rng.uniform(0.8, 3.0),
                "gps_nsats_min": rng.uniform(8.0, 15.0),
                "motor_spread_max": rng.uniform(50.0, 190.0),
                "motor_output_std": rng.uniform(15.0, 90.0),
                "target": 3,
            }

        row["session_id"] = f"synthetic_{idx:05d}"
        row["source"] = "synthetic"
        rows.append(row)

    return rows


def _resolve_log_path(manifest_path: str, log_path: str) -> str:
    if os.path.isabs(log_path):
        return log_path
    manifest_dir = os.path.dirname(os.path.abspath(manifest_path))
    return os.path.abspath(os.path.join(manifest_dir, log_path))


def extract_rows_from_manifest(manifest_path: str) -> List[Dict[str, float]]:
    """
    Manifest CSV expected columns:
      - log_path (required)
      - target (required, int)
      - session_id (optional)
    """
    if not os.path.exists(manifest_path):
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    manifest = pd.read_csv(manifest_path)
    required = {"log_path", "target"}
    missing = required - set(manifest.columns)
    if missing:
        raise ValueError(f"Manifest missing required columns: {sorted(missing)}")

    rows: List[Dict[str, float]] = []
    pipeline = FeaturePipeline()

    for rec in manifest.to_dict(orient="records"):
        log_path = _resolve_log_path(manifest_path, str(rec["log_path"]))
        target = int(rec["target"])
        session_id = str(rec.get("session_id") or os.path.splitext(os.path.basename(log_path))[0])

        parser = LogParser(log_path)
        parsed = parser.parse()
        features = pipeline.extract_all(parsed["messages"])

        row: Dict[str, float] = dict(features)
        row["target"] = target
        row["session_id"] = session_id
        row["source"] = "real_log"
        rows.append(row)

    return rows


def build_dataset(
    output_file: str,
    synthetic_samples: int = 1000,
    manifest_path: Optional[str] = None,
    seed: int = 42,
) -> pd.DataFrame:
    rows: List[Dict[str, float]] = []

    if manifest_path:
        rows.extend(extract_rows_from_manifest(manifest_path))
    if synthetic_samples > 0:
        rows.extend(generate_synthetic_rows(synthetic_samples, seed=seed))

    if not rows:
        raise ValueError("No dataset rows generated. Provide a manifest or synthetic samples > 0.")

    df = pd.DataFrame(rows)
    df = df.fillna(0.0)
    df["target"] = df["target"].astype(int)

    os.makedirs(os.path.dirname(os.path.abspath(output_file)), exist_ok=True)
    df.to_csv(output_file, index=False)
    return df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build training dataset for ArduPilot diagnosis")
    parser.add_argument("--output", type=str, default="data/synthetic_logs.csv", help="Output CSV path")
    parser.add_argument("--samples", type=int, default=1000, help="Number of synthetic rows to generate")
    parser.add_argument("--manifest", type=str, default=None, help="CSV manifest with labeled real logs")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for synthetic generation")
    args = parser.parse_args()

    dataset = build_dataset(
        output_file=args.output,
        synthetic_samples=args.samples,
        manifest_path=args.manifest,
        seed=args.seed,
    )
    print(f"Dataset written to {args.output}")
    print(f"Rows={len(dataset)} columns={len(dataset.columns)}")
