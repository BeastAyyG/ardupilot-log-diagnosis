import pytest
from unittest.mock import patch
import sys
from src.cli.main import main

def test_analyze_command(tmp_path):
    f = tmp_path / "test.BIN"
    f.write_text("dummy")
    
    test_args = ["main", "analyze", str(f), "--no-ml"]
    with patch.object(sys, 'argv', test_args):
        try:
            main()
        except SystemExit as e:
            # Exit 0 = success (real log, no issues)
            # Exit 2 = EXTRACTION_FAILED (expected for a dummy/corrupt file) ← B-01 fix
            assert e.code in (0, 2) or e.code is None

def test_features_command(tmp_path):
    f = tmp_path / "test.BIN"
    f.write_text("dummy")
    test_args = ["main", "features", str(f)]
    with patch.object(sys, 'argv', test_args):
        try:
            main()
        except SystemExit as e:
            assert e.code == 0 or e.code is None

def test_json_flag(tmp_path):
    f = tmp_path / "test.BIN"
    f.write_text("dummy")
    test_args = ["main", "analyze", str(f), "--json"]
    with patch.object(sys, 'argv', test_args):
        try:
            main()
        except SystemExit as e:
            # Exit 2 = EXTRACTION_FAILED (expected for a dummy/corrupt file) ← B-01 fix
            assert e.code in (0, 2) or e.code is None

def test_missing_file():
    test_args = ["main", "analyze", "nonexistent.BIN"]
    with patch.object(sys, 'argv', test_args):
        try:
            main()
        except SystemExit as e:
            pass


def test_import_clean_command_dispatch():
    test_args = ["main", "import-clean", "--source-root", "/tmp/source"]
    fake_summary = {
        "source_root": "/tmp/source",
        "output_root": "/tmp/out",
        "counts": {
            "total_bin_files": 0,
            "unique_parseable_after_dedupe": 0,
            "verified_labeled": 0,
            "provisional_labeled": 0,
            "verified_unlabeled": 0,
            "rejected_nonlog": 0,
            "benchmark_trainable": 0,
        },
        "artifacts": {"proof_markdown": "/tmp/out/proof.md"},
    }
    with patch("src.data.clean_import.run_clean_import", return_value=fake_summary):
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0 or e.code is None


def test_collect_forum_command_dispatch():
    test_args = ["main", "collect-forum", "--output-root", "/tmp/forum"]
    fake_summary = {
        "output_root": "/tmp/forum",
        "rows": 0,
        "downloaded": 0,
        "not_log_payload": 0,
        "download_failed": 0,
        "artifacts": {
            "manifest_csv": "/tmp/forum/crawler_manifest.csv",
            "summary_json": "/tmp/forum/crawler_summary.json",
        },
    }
    with patch("src.data.forum_collector.collect_forum_logs", return_value=fake_summary):
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0 or e.code is None


def test_mine_expert_labels_collect_dispatch():
    test_args = ["main", "mine-expert-labels", "--output-root", "/tmp/expert"]
    fake_summary = {
        "output_root": "/tmp/expert",
        "topics_scanned": 0,
        "topics_with_expert_label": 0,
        "rows": 0,
        "downloaded": 0,
        "not_log_payload": 0,
        "download_failed": 0,
        "artifacts": {
            "manifest_csv": "/tmp/expert/crawler_manifest_v2.csv",
            "block1_csv": "/tmp/expert/block1_ardupilot_discuss.csv",
            "summary_json": "/tmp/expert/crawler_summary_v2.json",
            "state_json": "/tmp/expert/expert_miner_state.json",
        },
    }
    with patch("src.data.expert_label_miner.collect_expert_labeled_forum_logs", return_value=fake_summary):
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0 or e.code is None


def test_mine_expert_labels_enrich_dispatch():
    test_args = ["main", "mine-expert-labels", "--enrich-only", "--source-root", "/tmp/source"]
    fake_summary = {
        "source_root": "/tmp/source",
        "input_manifest": "/tmp/source/crawler_manifest.csv",
        "output_manifest": "/tmp/source/crawler_manifest_v2.csv",
        "output_block1": "/tmp/source/block1_ardupilot_discuss.csv",
        "rows": 0,
        "topics_scanned": 0,
        "topics_with_expert_label": 0,
        "rows_with_label": 0,
        "summary_json": "/tmp/source/expert_label_summary.json",
    }
    with patch("src.data.expert_label_miner.enrich_manifest_with_expert_labels", return_value=fake_summary):
        with patch.object(sys, "argv", test_args):
            try:
                main()
            except SystemExit as e:
                assert e.code == 0 or e.code is None
