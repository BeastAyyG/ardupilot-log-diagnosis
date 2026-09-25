"""Generate the paper's figures from committed result files.

Every number drawn here is read from ``data/benchmark/results/*.json`` or
``data/benchmark/*summary*.json``; nothing is typed in by hand.

    python paper/make_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "data/benchmark/results"
OUT = ROOT / "paper/figures"

# Validated categorical slots 1-3 (light surface); slot 3 needs visible labels.
SERIES = {"RandomForest": "#2a78d6", "ExtraTrees": "#eb6834", "LogisticRegression": "#1baf7a"}
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
PROTOCOLS = [
    ("window_random", "Random windows\n(leaky)"),
    ("log_grouped", "Grouped by\nlog file"),
    ("incident_grouped", "Grouped by\nincident"),
]


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(MUTED)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def leakage_figure(result_file: str, name: str, title: str) -> None:
    report = json.loads((RESULTS / result_file).read_text())
    results = report["split_study"]["results"]
    models = [m for m in SERIES if any(k.startswith(m + "/") for k in results)]
    chance = report["chance_baselines"]["frequency_random_macro_f1"]
    fig, ax = plt.subplots(figsize=(6.2, 3.4), facecolor=SURFACE)
    _style(ax)
    width = 0.8 / len(models)
    for i, model in enumerate(models):
        xs, ys = [], []
        for j, (key, _) in enumerate(PROTOCOLS):
            value = results[f"{model}/{key}"]["log_macro_f1_mean"]
            x = j + (i - (len(models) - 1) / 2) * width
            xs.append(x)
            ys.append(value)
            ax.text(x, value + 0.015, f"{value:.2f}", ha="center", va="bottom",
                    fontsize=7, color=INK)
        ax.bar(xs, ys, width=width - 0.03, color=SERIES[model], label=model,
               edgecolor=SURFACE, linewidth=1.0)
    ax.axhspan(0, chance["p95"], color=GRID, alpha=0.6, zorder=0)
    ax.axhline(chance["mean"], color=MUTED, linewidth=1.0, linestyle="--")
    ax.text(2.45, chance["p95"] + 0.01, "chance range (random guess, 95th pct)",
            ha="right", va="bottom", fontsize=7, color=MUTED)
    ax.set_xticks(range(len(PROTOCOLS)), [label for _, label in PROTOCOLS])
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Log-level macro-F1", color=MUTED, fontsize=8)
    ax.set_title(title, fontsize=9, color=INK, loc="left")
    ax.legend(frameon=False, fontsize=7, loc="upper right")
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"{name}.{ext}", dpi=200, facecolor=SURFACE)
    plt.close(fig)


def label_audit_figure() -> None:
    summary = json.loads((ROOT / "data/benchmark/registry_summary.json").read_text())
    counts = summary["v2_thread_verified"]["annotation_status_all_logs"]
    names = {
        "confirmed": "Label confirmed by thread",
        "relabelled": "Thread names a different cause",
        "undiagnosed": "No agreed cause in thread",
        "not_a_failure": "Not a failure flight",
        "not_real_flight": "Simulation, not real",
        "not_reviewed": "Source not reachable",
    }
    items = sorted(((names[k], v) for k, v in counts.items()), key=lambda kv: kv[1])
    fig, ax = plt.subplots(figsize=(6.2, 2.6), facecolor=SURFACE)
    _style(ax)
    ax.yaxis.grid(False)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.barh([k for k, _ in items], [v for _, v in items], color=SERIES["RandomForest"],
            height=0.6, edgecolor=SURFACE)
    for i, (_, value) in enumerate(items):
        ax.text(value + 0.3, i, str(value), va="center", fontsize=7, color=INK)
    ax.set_xlabel("Logs (of 55 previously labelled)", color=MUTED, fontsize=8)
    ax.set_title("Thread audit of forum-mined labels", fontsize=9, color=INK, loc="left")
    fig.tight_layout()
    for ext in ("pdf", "png"):
        fig.savefig(OUT / f"label_audit.{ext}", dpi=200, facecolor=SURFACE)
    plt.close(fig)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    label_audit_figure()
    leakage_figure("paper_eval_v1.json", "leakage_v1", "Benchmark v1 (41 logs, provisional labels)")
    if (RESULTS / "paper_eval_v3.json").exists():
        leakage_figure("paper_eval_v3.json", "leakage_v3",
                       "Benchmark v3 (thread-verified labels)")
    print("figures written to", OUT.relative_to(ROOT))


if __name__ == "__main__":
    main()
