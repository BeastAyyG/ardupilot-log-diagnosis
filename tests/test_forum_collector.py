from src.data.forum_collector import _detect_kind, _looks_log_url, _normalize_download_url


def test_normalize_dropbox_download_url():
    url = "https://www.dropbox.com/s/abc/file.bin?dl=0"
    out = _normalize_download_url(url)
    assert "dl=1" in out


def test_normalize_google_drive_file_url():
    url = "https://drive.google.com/file/d/1AbCdEfGhIjKlMnOp/view?usp=sharing"
    out = _normalize_download_url(url)
    assert out.startswith("https://drive.google.com/uc?export=download&id=1AbCdEfGhIjKlMnOp")


def test_looks_log_url_detects_bin_and_zip():
    assert _looks_log_url("https://x/y/file.BIN") is True
    assert _looks_log_url("https://x/y/archive.zip") is True
    assert _looks_log_url("https://x/y/image.png") is False


def test_detect_kind_html_and_zip_and_bin():
    assert _detect_kind(b"<!DOCTYPE html>", "https://x/y.bin", {}) == "html"
    assert _detect_kind(b"PK\x03\x04abc", "https://x/y.zip", {}) == "zip"
    assert _detect_kind(b"\x01\x02\x03", "https://x/y.bin", {}) == "bin"
