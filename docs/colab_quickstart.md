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
cd /content
git clone https://github.com/<your-user>/<your-repo>.git
cd ardupilot-log-diagnosis
python -m pip install -r requirements.txt
cp /content/drive/MyDrive/ardupilot/colab_data_bundle.tar.gz .
tar -xzf colab_data_bundle.tar.gz
```

## 3) Run benchmark suite (all engines)

```bash
python training/run_all_benchmarks.py \
  --dataset-dir data/final_training_dataset_2026-02-23/dataset \
  --ground-truth data/final_training_dataset_2026-02-23/ground_truth.json \
  --output-dir data/final_training_dataset_2026-02-23
```

This writes:

- `data/final_training_dataset_2026-02-23/benchmark_results_ml.json`
- `data/final_training_dataset_2026-02-23/benchmark_results_hybrid.json`
- `data/final_training_dataset_2026-02-23/benchmark_results_rule.json`

## 4) Copy results back to Drive

```bash
mkdir -p /content/drive/MyDrive/ardupilot/results
cp data/final_training_dataset_2026-02-23/benchmark_results_* /content/drive/MyDrive/ardupilot/results/
```

## Notes

- Colab runtimes are ephemeral. Always copy results back to Drive.
- CPU runtime is sufficient for this benchmark workflow.
- Keep large logs and generated datasets out of git.
