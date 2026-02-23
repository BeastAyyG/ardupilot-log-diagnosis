# Google Colab Quickstart

This project can run fully on Colab CPU runtime. Keep code in Git and upload only
the data bundle to Google Drive.

## 1) Prepare data bundle locally

Run from repo root:

```bash
python training/create_colab_bundle.py \
  --output colab_data_bundle.tar.gz \
  --paths data/final_training_dataset_2026-02-23
```

Upload `colab_data_bundle.tar.gz` to your Google Drive, for example:
`MyDrive/ardupilot/colab_data_bundle.tar.gz`.

## 2) Colab setup

In a new Colab notebook, run:

```python
from google.colab import drive
drive.mount('/content/drive')
```

```bash
set -e
cd /content
git clone https://github.com/BeastAyyG/ardupilot-log-diagnosis.git
cd ardupilot-log-diagnosis
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp /content/drive/MyDrive/ardupilot/colab_data_bundle.tar.gz .
sha256sum colab_data_bundle.tar.gz
tar -xzf colab_data_bundle.tar.gz
```

Expected SHA256:

`81baa8ac01649e3be68e0cd6e5ff6496e0cf493f8fc86cb24f7f9704ec3de0dc`

## 3) Run benchmark suite (all engines)

```bash
set -e
python training/run_all_benchmarks.py \
  --dataset-dir data/final_training_dataset_2026-02-23/dataset \
  --ground-truth data/final_training_dataset_2026-02-23/ground_truth.json \
  --output-dir data/final_training_dataset_2026-02-23
```

This writes:

- `data/final_training_dataset_2026-02-23/benchmark_results_ml.json`
- `data/final_training_dataset_2026-02-23/benchmark_results_hybrid.json`
- `data/final_training_dataset_2026-02-23/benchmark_results_rule.json`

## Troubleshooting: bundle path not found

If Colab shows `cp: cannot stat '/content/drive/MyDrive/ardupilot/...': No such file or directory`,
the Drive path does not match the actual upload location.

Use these cells to locate the real file path:

```bash
ls /content/drive
ls /content/drive/MyDrive
```

```python
import os

for base in ["/content/drive/MyDrive", "/content/drive/Shareddrives"]:
    if not os.path.exists(base):
        continue
    for root, _, files in os.walk(base):
        if "colab_data_bundle.tar.gz" in files:
            print(os.path.join(root, "colab_data_bundle.tar.gz"))
```

Then update the copy command to the exact path you found, for example:

```bash
cp "/content/drive/MyDrive/Colab Notebooks/colab_data_bundle.tar.gz" .
```

## 4) Copy results back to Drive

```bash
set -e
mkdir -p /content/drive/MyDrive/ardupilot/results
cp data/final_training_dataset_2026-02-23/benchmark_results_* /content/drive/MyDrive/ardupilot/results/
```

## Notes

- Colab runtimes are ephemeral. Always copy results back to Drive.
- CPU runtime is sufficient for this benchmark workflow.
- Keep large logs and generated datasets out of git.
