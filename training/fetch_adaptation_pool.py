"""Download the unlabelled real logs (cohort ``adaptation_pool``) and their threads.

For every adaptation-pool record in ``data/cohorts/cohort_manifest.json`` with a
discuss.ardupilot.org source thread, this caches the thread (as
``training/fetch_threads.py`` does) and downloads the attachment. When the
manifest key is a full SHA256, the downloaded payload must match it. Zip
payloads are unpacked and every DataFlash ``.bin`` inside is kept. Everything
goes to the git-ignored ``data/raw/``; a manifest of what was obtained is
written to ``data/raw/adaptation/manifest.json``.

Example::

    python training/fetch_adaptation_pool.py
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.build_incident_registry import incident_id_for  # noqa: E402
from training.fetch_threads import fetch_topic  # noqa: E402

OUT = ROOT / "data/raw/adaptation"
THREADS = ROOT / "data/raw/threads"


def _download(url: str) -> bytes:
    if "dropbox.com" in url:
        url = re.sub(r"([?&])dl=0", r"\1dl=1", url)
        if "dl=1" not in url:
            url += ("&" if "?" in url else "?") + "dl=1"
    request = urllib.request.Request(url, headers={"User-Agent": "logdiagnosis-research/1.0"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return response.read()


def main() -> None:
    manifest = json.loads((ROOT / "data/cohorts/cohort_manifest.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    THREADS.mkdir(parents=True, exist_ok=True)
    results = []
    for key, record in sorted(manifest["records"].items()):
        if record["cohort"] != "adaptation_pool":
            continue
        url = (record["source_urls"] or [""])[0]
        incident = incident_id_for(url)
        entry = {"log_key": key[:10], "manifest_key": key, "incident_id": incident,
                 "source_url": url, "download_url": (record["download_urls"] or [""])[0],
                 "status": "", "files": []}
        results.append(entry)
        if not incident.startswith("discuss:"):
            entry["status"] = "no_forum_thread"
            continue
        topic = incident.split(":", 1)[1]
        thread_path = THREADS / f"{topic}.json"
        if not thread_path.exists():
            try:
                thread_path.write_text(json.dumps(fetch_topic(topic), indent=1, ensure_ascii=False))
                time.sleep(1.0)
            except Exception as exc:  # noqa: BLE001
                entry["status"] = f"thread_fetch_failed: {exc}"
                continue
        if not entry["download_url"]:
            entry["status"] = "no_download_url"
            continue
        try:
            payload = _download(entry["download_url"])
        except Exception as exc:  # noqa: BLE001
            entry["status"] = f"download_failed: {str(exc)[:80]}"
            continue
        digest = hashlib.sha256(payload).hexdigest()
        if record["key_quality"] == "sha256" and digest != key:
            entry["status"] = "sha256_mismatch"
            continue
        if not digest.startswith(key[:10]):
            entry["status"] = "sha256_prefix_mismatch"
            continue
        entry["payload_sha256"] = digest
        blobs = []
        if payload[:2] == b"PK":
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                for info in archive.infolist():
                    if info.filename.lower().endswith(".bin") and not info.is_dir():
                        blobs.append((Path(info.filename).name, archive.read(info)))
        else:
            blobs.append((Path(record["filenames"][0]).name, payload))
        for index, (name, data) in enumerate(blobs):
            sha = hashlib.sha256(data).hexdigest()
            stem = f"{key[:10]}__{index}__{re.sub(r'[^A-Za-z0-9._-]', '_', name)}"
            (OUT / stem).write_bytes(data)
            entry["files"].append({"file": stem, "sha256": sha, "bytes": len(data)})
        entry["status"] = "ok" if entry["files"] else "no_bin_in_payload"
        time.sleep(0.5)
    (OUT / "manifest.json").write_text(json.dumps(results, indent=1) + "\n")
    from collections import Counter

    print(Counter(e["status"].split(":")[0] for e in results))


if __name__ == "__main__":
    main()
