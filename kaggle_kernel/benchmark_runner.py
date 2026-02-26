import os
import subprocess
import sys
import shutil
import shlex

def run_cmd(cmd, cwd=None, shell=False, check=True):
    print(f"[CMD] {cmd}", flush=True)
    if shell:
        result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    else:
        result = subprocess.run(shlex.split(cmd) if isinstance(cmd, str) else cmd,
                                cwd=cwd, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, flush=True)
    if result.stderr:
        print("[STDERR]", result.stderr[:2000], flush=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed (rc={result.returncode}): {cmd}")
    return result

print("=" * 60, flush=True)
print("ArduPilot Log Benchmark — Recovery v8", flush=True)
print("=" * 60, flush=True)

# ── 1. Setup ──────────────────────────────────────────────────
WORK_DIR = "/kaggle/working"
os.chdir(WORK_DIR)

# ── 2. Locate and Prepare Code ──────────────────────────────────
print("Locating source code in datasets...", flush=True)
DATASET_ROOT = None
for root, dirs, files in os.walk("/kaggle/input"):
    if "src" in dirs and "ground_truth.json" in files:
        DATASET_ROOT = root
        break

if not DATASET_ROOT:
    sys.exit("FATAL: Dataset with 'src' and 'ground_truth.json' not found.")

REPO_DIR = os.path.join(WORK_DIR, "repo")
if os.path.exists(REPO_DIR): shutil.rmtree(REPO_DIR)
shutil.copytree(os.path.join(DATASET_ROOT, "src"), os.path.join(REPO_DIR, "src"))
print(f"Copied src to {REPO_DIR}", flush=True)

# ── 3. Find data ──────────────────────────────────────────────
GROUND_TRUTH = os.path.join(DATASET_ROOT, "ground_truth.json")
DATASET_DIR  = os.path.join(DATASET_ROOT, "dataset")
OUTPUT_DIR   = os.path.join(WORK_DIR, "benchmark_outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

print(f"Ground truth : {GROUND_TRUTH}", flush=True)
print(f"Dataset dir  : {DATASET_DIR}", flush=True)
print(f"Output dir   : {OUTPUT_DIR}", flush=True)

# ── 3.5. Setup Models ──────────────────────────────────────────
MODELS_SRC = os.path.join(os.path.dirname(GROUND_TRUTH), "models")
MODELS_DST = os.path.join(REPO_DIR, "models")
if os.path.exists(MODELS_SRC):
    print(f"Found models in dataset: {MODELS_SRC}", flush=True)
    if os.path.islink(MODELS_DST) or os.path.exists(MODELS_DST):
        if os.path.islink(MODELS_DST): os.unlink(MODELS_DST)
        else: shutil.rmtree(MODELS_DST)
    os.symlink(MODELS_SRC, MODELS_DST)
    print(f"Symlinked models to {MODELS_DST}", flush=True)
else:
    print(f"WARN: Models not found in dataset at {MODELS_SRC}", flush=True)

# Verify dataset dir has files
import json, glob
with open(GROUND_TRUTH) as f:
    gt_data = json.load(f)
n_logs = len(gt_data.get("logs", []))
n_files = len(glob.glob(os.path.join(DATASET_DIR, "*.bin")))
print(f"Ground truth logs: {n_logs}", flush=True)
print(f"Dataset .bin files: {n_files}", flush=True)

# ── 4. Install deps ───────────────────────────────────────────
run_cmd("pip install -q pymavlink numpy xgboost scikit-learn pyyaml")

# ── 5. Run each engine separately with explicit env/cwd ───────
env = os.environ.copy()
env["PYTHONPATH"] = REPO_DIR  # ensure src/ is importable

ENGINES = ["rule", "hybrid", "ml"]

summaries = []
for engine in ENGINES:
    prefix = os.path.join(OUTPUT_DIR, f"benchmark_results_{engine}")
    cmd = [
        sys.executable, "-m", "src.cli.main", "benchmark",
        "--engine", engine,
        "--dataset-dir", DATASET_DIR,
        "--ground-truth", GROUND_TRUTH,
        "--output-prefix", prefix,
    ]
    print(f"\n{'─'*50}", flush=True)
    print(f"[ENGINE] {engine}", flush=True)
    print(f"{'─'*50}", flush=True)

    result = subprocess.run(
        cmd,
        cwd=REPO_DIR,
        env=env,
        capture_output=True,
        text=True,
    )
    print(result.stdout, flush=True)
    if result.stderr:
        # Only print non-trivial stderr
        stderr_lines = [l for l in result.stderr.splitlines()
                        if l.strip() and not l.startswith("WARNING")]
        if stderr_lines:
            print("[STDERR]\n" + "\n".join(stderr_lines[:40]), flush=True)

    if result.returncode != 0:
        print(f"[ERROR] Engine {engine} failed with rc={result.returncode}", flush=True)
        summaries.append({"engine": engine, "error": True})
        continue

    # Load result JSON
    json_path = prefix + ".json"
    if os.path.exists(json_path):
        with open(json_path) as f:
            data = json.load(f)
        ov = data.get("overall", {})
        summaries.append({
            "engine": engine,
            "accuracy":   ov.get("accuracy", 0.0),
            "top1_acc":   ov.get("top1_accuracy", 0.0),
            "macro_f1":   ov.get("macro_f1", 0.0),
            "total_logs": ov.get("total_logs", 0),
            "ok":         ov.get("successful_extractions", 0),
            "failed":     ov.get("failed_extractions", 0),
        })
    else:
        print(f"[WARN] No output JSON at {json_path}", flush=True)
        summaries.append({"engine": engine, "error": "no_json"})

# ── 6. Print summary ──────────────────────────────────────────
print("\n" + "=" * 60, flush=True)
print("BENCHMARK SUMMARY", flush=True)
print("=" * 60, flush=True)
for s in summaries:
    if s.get("error"):
        print(f"  {s['engine']:10s}: FAILED ({s.get('error')})", flush=True)
    else:
        print(
            f"  {s['engine']:10s}: any_match={s['accuracy']:.2%}  top1={s['top1_acc']:.2%}"
            f"  macro_f1={s['macro_f1']:.4f}  logs={s['ok']}/{s['total_logs']}",
            flush=True,
        )

# ── 7. Package ────────────────────────────────────────────────
os.chdir(WORK_DIR)
run_cmd(f"zip -r benchmark_recovery_v8.zip benchmark_outputs", shell=False,
        cmd=f"zip -r benchmark_recovery_v8.zip benchmark_outputs")
print("\n[DONE] Benchmark complete.", flush=True)
