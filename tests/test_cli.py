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
