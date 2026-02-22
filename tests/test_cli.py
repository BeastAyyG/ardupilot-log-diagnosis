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
            assert e.code == 0 or e.code is None

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
            assert e.code == 0 or e.code is None

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
