"""Forum log collector for expanding benchmark candidate data.

Collects candidate .bin/.zip logs from discuss.ardupilot.org based on search
queries and writes a manifest for downstream clean import.
"""

from __future__ import annotations

import csv
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

BASE_URL = "https://discuss.ardupilot.org"
DEFAULT_USER_AGENT = "ardupilot-log-diagnosis/collector"

DEFAULT_QUERIES = {
    "vibration_high": "high vibration crash .bin",
    "compass_interference": "compass variance crash .bin",
    "motor_imbalance": "motor desync thrust imbalance .bin",
    "gps_quality_poor": "gps glitch hdop crash .bin",
    "ekf_failure": "ekf variance failsafe crash .bin",
}

HREF_RE = re.compile(r"href=[\"']?([^\"' >]+)", re.IGNORECASE)
DRIVE_ID_RE = re.compile(r"/d/([a-zA-Z0-9_-]+)")


def _request_json(url: str, timeout_sec: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _request_bytes(url: str, timeout_sec: int = 60) -> Tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        payload = resp.read()
        headers = dict(resp.headers.items())
        return payload, headers


def _make_absolute(url: str) -> str:
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    if url.startswith("//"):
        return f"https:{url}"
    return urllib.parse.urljoin(BASE_URL, url)


def _normalize_download_url(url: str) -> str:
    normalized = _make_absolute(url)

    if "dropbox.com" in normalized and "dl=0" in normalized:
        normalized = normalized.replace("dl=0", "dl=1")

    if "drive.google.com" in normalized:
        m = DRIVE_ID_RE.search(normalized)
        if m:
            file_id = m.group(1)
            normalized = f"https://drive.google.com/uc?export=download&id={file_id}"

    return normalized


def _looks_log_url(url: str) -> bool:
    u = url.lower()
    return ".bin" in u or ".zip" in u


def _detect_kind(payload: bytes, source_url: str, headers: dict) -> str:
    lower = source_url.lower()
    if ".zip" in lower:
        return "zip"

    if payload.startswith(b"PK\x03\x04"):
        return "zip"
    if payload.startswith(b"\x89PNG"):
        return "png"
    if payload.startswith(b"GIF8"):
        return "gif"
    if payload.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if payload.startswith(b"<") or payload.lower().startswith(b"<!doctype html"):
        return "html"

    content_type = str(headers.get("Content-Type", "")).lower()
    if "text/html" in content_type:
        return "html"

    if ".bin" in lower:
        return "bin"
    return "binary"


def _ext_for_kind(kind: str) -> str:
    if kind == "zip":
        return ".zip"
    if kind == "bin":
        return ".bin"
    return ".dat"


def _iter_attachment_urls(post_html: str) -> Iterable[str]:
    for match in HREF_RE.findall(post_html or ""):
        if _looks_log_url(match):
            yield match


def _topic_url(slug: str, topic_id: int) -> str:
    return f"{BASE_URL}/t/{slug}/{topic_id}"


def collect_forum_logs(
    output_root: str,
    max_per_query: int = 20,
    max_topics_per_query: int = 60,
    sleep_ms: int = 250,
    include_zip: bool = True,
    query_overrides: Optional[Dict[str, str]] = None,
) -> dict:
    out = Path(output_root)
    downloads_dir = out / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    queries = dict(DEFAULT_QUERIES)
    if query_overrides:
        queries.update(query_overrides)

    manifest_rows: List[dict] = []
    seen_urls = set()
    saved_counter = 1

    for label, query in queries.items():
        encoded = urllib.parse.quote(query)
        search_url = f"{BASE_URL}/search.json?q={encoded}"

        try:
            search = _request_json(search_url)
        except Exception as exc:
            manifest_rows.append(
                {
                    "label": label,
                    "query": query,
                    "topic_id": "",
                    "topic_url": "",
                    "post_number": "",
                    "post_url": "",
                    "attachment_url": search_url,
                    "download_url": search_url,
                    "saved_file": "",
                    "status": "search_failed",
                    "kind": "",
                    "bytes": 0,
                    "error": str(exc),
                }
            )
            continue

        topics = search.get("topics", [])[:max_topics_per_query]
        downloaded_for_label = 0

        for topic in topics:
            if downloaded_for_label >= max_per_query:
                break

            topic_id = topic.get("id")
            topic_slug = topic.get("slug", "")
            if topic_id is None:
                continue

            topic_json_url = f"{BASE_URL}/t/{topic_id}.json"
            try:
                thread = _request_json(topic_json_url)
            except Exception as exc:
                manifest_rows.append(
                    {
                        "label": label,
                        "query": query,
                        "topic_id": topic_id,
                        "topic_url": _topic_url(topic_slug, topic_id),
                        "post_number": "",
                        "post_url": "",
                        "attachment_url": topic_json_url,
                        "download_url": topic_json_url,
                        "saved_file": "",
                        "status": "topic_failed",
                        "kind": "",
                        "bytes": 0,
                        "error": str(exc),
                    }
                )
                continue

            posts = thread.get("post_stream", {}).get("posts", [])
            for post in posts:
                if downloaded_for_label >= max_per_query:
                    break

                post_number = post.get("post_number", "")
                post_url = f"{_topic_url(topic_slug, topic_id)}/{post_number}"

                for raw_attachment in _iter_attachment_urls(post.get("cooked", "")):
                    if downloaded_for_label >= max_per_query:
                        break

                    normalized = _normalize_download_url(raw_attachment)
                    if not include_zip and ".zip" in normalized.lower():
                        continue
                    if normalized in seen_urls:
                        continue

                    seen_urls.add(normalized)

                    status = "downloaded"
                    error_msg = ""
                    payload = b""
                    headers = {}
                    kind = ""

                    try:
                        payload, headers = _request_bytes(normalized)
                        kind = _detect_kind(payload, normalized, headers)
                        if kind in {"html", "png", "gif", "jpg"}:
                            status = "not_log_payload"
                    except Exception as exc:
                        status = "download_failed"
                        error_msg = str(exc)

                    saved_name = ""
                    if status == "downloaded":
                        ext = _ext_for_kind(kind)
                        safe_label = re.sub(r"[^a-zA-Z0-9_]+", "_", label).strip("_")
                        saved_name = f"log_{saved_counter:04d}_{safe_label}{ext}"
                        saved_counter += 1
                        (downloads_dir / saved_name).write_bytes(payload)
                        downloaded_for_label += 1

                    manifest_rows.append(
                        {
                            "label": label,
                            "query": query,
                            "topic_id": topic_id,
                            "topic_url": _topic_url(topic_slug, topic_id),
                            "post_number": post_number,
                            "post_url": post_url,
                            "attachment_url": _make_absolute(raw_attachment),
                            "download_url": normalized,
                            "saved_file": saved_name,
                            "status": status,
                            "kind": kind,
                            "bytes": len(payload),
                            "error": error_msg,
                        }
                    )

                    if sleep_ms > 0:
                        time.sleep(sleep_ms / 1000.0)

    manifest_csv = out / "crawler_manifest.csv"
    manifest_json = out / "crawler_manifest.json"
    summary_json = out / "crawler_summary.json"

    fieldnames = [
        "label",
        "query",
        "topic_id",
        "topic_url",
        "post_number",
        "post_url",
        "attachment_url",
        "download_url",
        "saved_file",
        "status",
        "kind",
        "bytes",
        "error",
    ]

    with manifest_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)

    manifest_json.write_text(json.dumps(manifest_rows, indent=2) + "\n")

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_root": str(out),
        "downloads_dir": str(downloads_dir),
        "query_count": len(queries),
        "rows": len(manifest_rows),
        "downloaded": sum(1 for r in manifest_rows if r["status"] == "downloaded"),
        "not_log_payload": sum(1 for r in manifest_rows if r["status"] == "not_log_payload"),
        "download_failed": sum(1 for r in manifest_rows if r["status"] == "download_failed"),
        "topic_failed": sum(1 for r in manifest_rows if r["status"] == "topic_failed"),
        "search_failed": sum(1 for r in manifest_rows if r["status"] == "search_failed"),
        "artifacts": {
            "manifest_csv": str(manifest_csv),
            "manifest_json": str(manifest_json),
            "summary_json": str(summary_json),
        },
    }
    summary_json.write_text(json.dumps(summary, indent=2) + "\n")
    return summary
