"""Focused tests for the optional XGBoost dependency boundary."""

from __future__ import annotations

import importlib
import socket
from types import ModuleType

import pytest

from src.core.reasoning import xgboost_classifier


def test_boundary_import_does_not_resolve_xgboost(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def unexpected_import(name: str) -> ModuleType:
        calls.append(name)
        raise AssertionError("xgboost must not load during module import")

    monkeypatch.setattr(importlib, "import_module", unexpected_import)
    importlib.reload(xgboost_classifier)

    assert calls == []


def test_absent_xgboost_is_reported_without_side_effects(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    def missing_import(name: str) -> ModuleType:
        assert name == "xgboost"
        raise ModuleNotFoundError(name)

    def unexpected_network(*args, **kwargs):
        raise AssertionError("availability checks must not open network sockets")

    before = tuple(tmp_path.iterdir())
    monkeypatch.setattr(importlib, "import_module", missing_import)
    monkeypatch.setattr(socket, "socket", unexpected_network)

    assert xgboost_classifier.is_xgboost_available() is False
    with pytest.raises(xgboost_classifier.XGBoostUnavailableError):
        xgboost_classifier.load_xgboost()
    assert tuple(tmp_path.iterdir()) == before


def test_present_xgboost_is_loaded_only_on_explicit_request(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    fake_xgboost = ModuleType("xgboost")
    imported: list[str] = []

    def present_import(name: str) -> ModuleType:
        imported.append(name)
        assert name == "xgboost"
        return fake_xgboost

    before = tuple(tmp_path.iterdir())
    monkeypatch.setattr(importlib, "import_module", present_import)

    assert imported == []
    assert xgboost_classifier.is_xgboost_available() is True
    assert xgboost_classifier.load_xgboost() is fake_xgboost
    assert imported == ["xgboost", "xgboost"]
    assert tuple(tmp_path.iterdir()) == before
