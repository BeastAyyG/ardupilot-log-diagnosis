import json

from src.data import forum_collector
from src.data.forum_collector import (
    _detect_kind,
    _iter_attachment_urls,
    _looks_log_url,
    _normalize_download_url,
)


def test_normalize_dropbox_download_url():
    url = "https://www.dropbox.com/s/abc/file.bin?dl=0"
    out = _normalize_download_url(url)
    assert "dl=1" in out


def test_normalize_dropbox_url_without_query_forces_direct_download():
    url = "https://www.dropbox.com/s/abc/file.bin"
    out = _normalize_download_url(url)
    assert out.endswith("file.bin?dl=1")


def test_normalize_google_drive_file_url():
    url = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp/view?usp=sharing"
    out = _normalize_download_url(url)
    assert out.startswith("https://drive.google.com/uc?export=download&id=1AbCdEfGhIjKlMnOp")


def test_looks_log_url_detects_bin_and_zip():
    assert _looks_log_url("https://x/y/file.BIN") is True
    assert _looks_log_url("https://x/y/archive.zip") is True
    assert _looks_log_url("https://drive.google.com/file/d/abc123/view") is True
    assert _looks_log_url("https://x/y/image.png") is False


def test_detect_kind_html_and_zip_and_bin():
    assert _detect_kind(b"<!DOCTYPE html>", "https://x/y.bin", {}) == "html"
    assert _detect_kind(b"PK\x03\x04abc", "https://x/y.zip", {}) == "zip"
    assert _detect_kind(b"\x01\x02\x03", "https://x/y.bin", {}) == "bin"


def test_attachment_urls_unescape_html_query_parameters():
    html = '<a href="https://www.dropbox.com/scl/fi/id/log.bin?rlkey=x&amp;dl=0">log</a>'
    assert list(_iter_attachment_urls(html)) == [
        "https://www.dropbox.com/scl/fi/id/log.bin?rlkey=x&dl=0"
    ]


def test_explicit_query_overrides_replace_default_collection_plan(tmp_path, monkeypatch):
    requested_urls = []

    def fake_request_json(url):
        requested_urls.append(url)
        return {"topics": []}

    monkeypatch.setattr(forum_collector, "_request_json", fake_request_json)

    summary = forum_collector.collect_forum_logs(
        output_root=str(tmp_path / "collection"),
        query_overrides={"brownout": "controller reboot crash .bin"},
        sleep_ms=0,
    )

    assert summary["query_count"] == 1
    assert len(requested_urls) == 1
    assert "controller%20reboot%20crash%20.bin" in requested_urls[0]
    manifest = json.loads((tmp_path / "collection" / "crawler_manifest.json").read_text())
    assert manifest == []
