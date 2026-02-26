import os
import subprocess
import sys
import glob
import shutil

def run_cmd(cmd, shell=False):
    print(f"Running: {cmd}")
    result = subprocess.run(cmd, shell=shell, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
    else:
        print(result.stdout)
    return result

print("--- Starting ArduPilot Log Benchmark Phase 3 (v3 - Git Hybrid) ---")

# 1. Setup working directory
working_dir = "/kaggle/working"
os.chdir(working_dir)

# 2. Clone the latest code
repo_url = "https://github.com/BeastAyyG/ardupilot-log-diagnosis.git"
if os.path.exists("ardupilot-log-diagnosis"):
    shutil.rmtree("ardupilot-log-diagnosis")
run_cmd(f"git clone {repo_url}")
os.chdir("ardupilot-log-diagnosis")

# 3. Determine data paths from Kaggle input
# Based on subagent and previously seen logs
input_root = "/kaggle/input/colab-data"
# Search for ground_truth.json in input
gt_matches = glob.glob(f"{input_root}/**/ground_truth.json", recursive=True)
if not gt_matches:
    print(f"FAILED to find ground_truth.json in {input_root}. Exploring:")
    run_cmd(f"ls -R {input_root}", shell=True)
    sys.exit(1)

ground_truth = gt_matches[0]
dataset_dir = os.path.join(os.path.dirname(ground_truth), "dataset")

print(f"Ground Truth found at: {ground_truth}")
print(f"Dataset Dir found at: {dataset_dir}")

# 4. Install dependencies
run_cmd("pip install pymavlink numpy xgboost scikit-learn pyyaml")

# 5. Run benchmarks
output_dir = "/kaggle/working/benchmark_outputs"
os.makedirs(output_dir, exist_ok=True)

# Run the all-in-one benchmark script
# We pass the absolute paths from the Kaggle input
run_cmd(f"python3 training/run_all_benchmarks.py --dataset-dir {dataset_dir} --ground-truth {ground_truth} --output-dir {output_dir}")

# 6. Package results
os.chdir(working_dir)
run_cmd(f"zip -r benchmark_results_p3_final.zip benchmark_outputs")

print("--- Benchmark Complete ---")
