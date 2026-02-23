# Kaggle Quickstart

Use Kaggle Notebooks if your laptop cannot handle repeated benchmark runs.

## 1) Upload bundle to Kaggle

Create a data bundle locally:

```bash
python training/create_colab_bundle.py \
  --output colab_data_bundle.tar.gz \
  --paths data/final_training_dataset_2026-02-23
```

In Kaggle, create a new Dataset and upload `colab_data_bundle.tar.gz`.

## 2) Start a Kaggle notebook

- Enable **Internet** in notebook settings.
- Add your uploaded dataset as notebook input.

## 3) Notebook setup

```bash
set -e
cd /kaggle/working
git clone https://github.com/BeastAyyG/ardupilot-log-diagnosis.git
cd ardupilot-log-diagnosis
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp /kaggle/input/<your-dataset-name>/colab_data_bundle.tar.gz .
sha256sum colab_data_bundle.tar.gz
tar -xzf colab_data_bundle.tar.gz
```

Expected SHA256:

`81baa8ac01649e3be68e0cd6e5ff6496e0cf493f8fc86cb24f7f9704ec3de0dc`

## 4) Run all benchmarks

```bash
set -e
python training/run_all_benchmarks.py \
  --dataset-dir data/final_training_dataset_2026-02-23/dataset \
  --ground-truth data/final_training_dataset_2026-02-23/ground_truth.json \
  --output-dir data/final_training_dataset_2026-02-23
```

## 5) Save outputs for download

```bash
set -e
mkdir -p /kaggle/working/results
cp data/final_training_dataset_2026-02-23/benchmark_results_* /kaggle/working/results/
cd /kaggle/working
zip -r benchmark_results.zip results
```

Then download `/kaggle/working/benchmark_results.zip` from the notebook output.

## Notes

- Kaggle sessions are temporary. Download outputs before stopping.
- Keep data bundles in Kaggle/Drive storage, not in git.
