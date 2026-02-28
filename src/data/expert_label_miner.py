"""Expert-labeled forum mining utilities.

This module mines discuss.ardupilot.org for logs that already have a diagnosis
from Developer/staff users, then downloads those attachments and emits
provenance artifacts compatible with clean-import.
"""

from __future__ import annotations

import csv
import html
import json
import re
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

from src.data.forum_collector import (
    BASE_URL,
    DEFAULT_USER_AGENT,
    _detect_kind,
    _ext_for_kind,
    _iter_attachment_urls,
    _make_absolute,
    _normalize_download_url,
    _request_bytes,
)


DEFAULT_SEARCH_QUERIES = {
    "crash_analysis_01": "crash analysis .bin log attached",
    "crash_analysis_02": "need help with log .bin ardupilot",
    "crash_analysis_03": "EKF failsafe crash .bin",
    "crash_analysis_04": "radio failsafe crash .bin",
    "crash_analysis_05": "brownout reboot crash .bin",
    "crash_analysis_06": "compass variance crash .bin",
    "crash_analysis_07": "high vibration crash .bin",
    "crash_analysis_08": "motor desync crash .bin",
}

LABEL_REGEX = {
    "rc_failsafe": [
        r"\bradio failsafe\b",
        r"\brc failsafe\b",
        r"\bno rc receiver\b",
        r"\brx failsafe\b",
    ],
    "brownout": [
        r"\bbrownout\b",
        r"\bflight controller reboot\b",
        r"\breboot(ed)? in (air|flight)\b",
        r"\bwatchdog\b",
        r"\bcrash[_ ]dump\b",
    ],
    "power_instability": [
        r"\bvoltage sag\b",
        r"\bbattery sag\b",
        r"\bpower issue\b",
        r"\bvcc drop\b",
        r"\bpower (instability|problem)\b",
    ],
    "ekf_failure": [
        r"\bekf (variance|fail|failsafe)\b",
        r"\blane switch\b",
        r"\bekf3? position\b",
    ],
    "compass_interference": [
        r"\bcompass variance\b",
        r"\bmag(netic)? interference\b",
        r"\bmag variance\b",
        r"\byaw reset\b",
    ],
    "vibration_high": [
        r"\bhigh vibration\b",
        r"\bvibration issue\b",
        r"\bclipping\b",
        r"\bvibe\b",
    ],
    "motor_imbalance": [
        r"\besc desync\b",
        r"\bmotor(s)? (stopped|cut|stop)\b",
        r"\bthrust loss\b",
        r"\bmotor imbalance\b",
    ],
    "gps_quality_poor": [
        r"\bgps glitch\b",
        r"\bhdop\b",
        r"\bgps (quality|issue|loss|lost)\b",
    ],
    "pid_tuning_issue": [
        r"\bpid\b",
        r"\boscillation\b",
        r"\bwobble\b",
        r"\btuning issue\b",
    ],
    "mechanical_failure": [
        r"\bmechanical failure\b",
        r"\bbroken (prop|arm|frame)\b",
        r"\bprop(eller)? (came off|failed|broke)\b",
    ],
    "crash_unknown": [
        r"\bunknown cause\b",
        r"\bcause (is )?unknown\b",
        r"\bnot clear what caused\b",
        r"\bunable to determine\b",
    ],
}

INTENT_REGEX = re.compile(
    r"\b(this|that|it)\s+(is|was|looks|seems|appears)\b|"
    r"\b(root cause|cause is|caused by|problem is|issue is)\b",
    re.IGNORECASE,
)

UNCERTAIN_REGEX = re.compile(
    r"\b(maybe|not sure|hard to tell|unclear|possibly)\b",
    re.IGNORECASE,
)

TOPIC_URL_RE = re.compile(r"/t/([^/]+)/([0-9]+)")
WEB_CITATION_RE = re.compile(r"\s*\[web:[0-9]+\]")


def _request_json(url: str, timeout_sec: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout_sec) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def _strip_html(text_html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text_html or "")
    text = html.unescape(text)
    text = WEB_CITATION_RE.sub("", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def canonicalize_topic_url(url: str) -> str:
    if not url:
        return ""
    clean = WEB_CITATION_RE.sub("", url).strip()
    parsed = urllib.parse.urlparse(clean)
    netloc = parsed.netloc.lower()
    if netloc not in {"discuss.ardupilot.org", "www.discuss.ardupilot.org"}:
        return clean.rstrip("/")

    m = TOPIC_URL_RE.search(parsed.path)
    if not m:
        return f"https://discuss.ardupilot.org{parsed.path}".rstrip("/")

    slug, topic_id = m.groups()
    return f"https://discuss.ardupilot.org/t/{slug}/{topic_id}"


def _topic_json_url(topic_id: int) -> str:
    return f"{BASE_URL}/t/{topic_id}.json"


def _safe_filename_label(label: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]+", "_", label).strip("_") or "unknown"


def _is_expert_post(post: dict, developer_usernames: Set[str]) -> bool:
    username = (post.get("username") or "").strip()
    if username and username in developer_usernames:
        return True

    user_title = (post.get("user_title") or "").strip().lower()
    if "developer" in user_title:
        return True

    group_name = (post.get("primary_group_name") or "").strip().lower()
    if "developer" in group_name:
        return True

    if post.get("staff") or post.get("moderator") or post.get("admin"):
        return True

    return False


def _score_label_from_text(text: str) -> Optional[Tuple[str, int, str]]:
    lowered = text.lower()
    has_intent = bool(INTENT_REGEX.search(lowered))
    has_uncertain = bool(UNCERTAIN_REGEX.search(lowered))

    best: Optional[Tuple[str, int, str]] = None
    for label, patterns in LABEL_REGEX.items():
        score = 0
        match_phrase = ""
        for pat in patterns:
            m = re.search(pat, lowered, flags=re.IGNORECASE)
            if m:
                score += 1
                if not match_phrase:
                    match_phrase = m.group(0)

        if score == 0:
            continue

        if has_intent:
            score += 2
        if has_uncertain:
            score -= 1

        if best is None or score > best[1]:
            best = (label, score, match_phrase)

    if best is None:
        return None

    label, score, phrase = best
    if score < 2:
        return None

    return label, score, phrase


def extract_label_from_text(text: str) -> Optional[str]:
    scored = _score_label_from_text(text)
    if scored is None:
        return None
    return scored[0]


def _extract_expert_diagnosis(topic_json: dict, developer_usernames: Set[str]) -> Optional[dict]:
    posts = topic_json.get("post_stream", {}).get("posts", [])
    candidates: List[dict] = []

    for post in posts:
        if not _is_expert_post(post, developer_usernames):
            continue

        cleaned = _strip_html(post.get("cooked", ""))
        scored = _score_label_from_text(cleaned)
        if scored is None:
            continue

        label, score, phrase = scored
        candidates.append(
            {
                "label": label,
                "score": score,
                "phrase": phrase,
                "username": post.get("username", ""),
                "post_number": post.get("post_number", 0),
                "quote": cleaned[:420],
            }
        )

    if not candidates:
        return None

    candidates.sort(key=lambda x: (-x["score"], x["post_number"]))
    return candidates[0]


def _read_json_queries(path: Optional[str]) -> Dict[str, str]:
    if not path:
        return dict(DEFAULT_SEARCH_QUERIES)

    raw = json.loads(Path(path).read_text(encoding="utf-8"))

    if isinstance(raw, dict) and "queries" in raw and isinstance(raw["queries"], list):
        label = str(raw.get("label") or "crash_analysis")
        out = {}
        for i, q in enumerate(raw["queries"], start=1):
            if not q:
                continue
            out[f"{label}_{i:03d}"] = str(q)
        return out

    if isinstance(raw, list):
        out = {}
        for i, q in enumerate(raw, start=1):
            if not q:
                continue
            out[f"query_{i:03d}"] = str(q)
        return out

    if isinstance(raw, dict):
        out = {}
        for key, value in raw.items():
            if isinstance(value, str) and value.strip():
                out[str(key)] = value
        return out

    raise ValueError("Unsupported queries JSON format")


def _load_state(path: Path) -> dict:
    if not path.exists():
        return {
            "last_run_utc": "",
            "processed_topic_ids": [],
            "processed_download_urls": [],
        }

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {
            "last_run_utc": "",
            "processed_topic_ids": [],
            "processed_download_urls": [],
        }

    data.setdefault("last_run_utc", "")
    data.setdefault("processed_topic_ids", [])
    data.setdefault("processed_download_urls", [])
    return data


def _write_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def _load_existing_labeled_topics(data_root: str = "data") -> Set[str]:
    root = Path(data_root)
    if not root.exists():
        return set()

    topics: Set[str] = set()
    for gt_path in root.glob("**/ground_truth.json"):
        try:
            payload = json.loads(gt_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for row in payload.get("logs", []):
            source_url = row.get("source_url", "")
            if "discuss.ardupilot.org/t/" not in source_url:
                continue
            topics.add(canonicalize_topic_url(source_url))
    return topics


def _extract_topic_id(topic_url: str) -> Optional[int]:
    m = TOPIC_URL_RE.search(topic_url or "")
    if not m:
        return None
    try:
        return int(m.group(2))
    except Exception:
        return None


def _download_developer_usernames() -> Set[str]:
    usernames: Set[str] = set()
    offset = 0
    limit = 50

    while True:
        url = f"{BASE_URL}/groups/developer/members.json?limit={limit}&offset={offset}"
        data = _request_json(url)
        members = data.get("members", [])
        if not members:
            break

        for member in members:
            username = (member.get("username") or "").strip()
            if username:
                usernames.add(username)

        meta = data.get("meta", {})
        total = int(meta.get("total") or 0)
        offset += len(members)
        if total and offset >= total:
            break
        if len(members) < limit:
            break

    return usernames


def _search_topics(query: str, max_topics: int) -> List[dict]:
    encoded = urllib.parse.quote(query)
    url = f"{BASE_URL}/search.json?q={encoded}"
    data = _request_json(url)
    return list(data.get("topics", []))[:max_topics]


def _rows_to_csv(path: Path, rows: List[dict], fieldnames: Sequence[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def enrich_manifest_with_expert_labels(
    source_root: str,
    input_manifest_name: str = "crawler_manifest.csv",
    output_manifest_name: str = "crawler_manifest_v2.csv",
    output_block1_name: str = "block1_ardupilot_discuss.csv",
    sleep_ms: int = 250,
) -> dict:
    src = Path(source_root)
    input_manifest = src / input_manifest_name
    output_manifest = src / output_manifest_name
    output_block1 = src / output_block1_name

    if not input_manifest.exists():
        raise FileNotFoundError(f"Manifest not found: {input_manifest}")

    with input_manifest.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    developers = _download_developer_usernames()

    topic_label_map: Dict[str, dict] = {}
    topic_urls = sorted({canonicalize_topic_url(r.get("topic_url", "")) for r in rows if r.get("topic_url")})

    for topic_url in topic_urls:
        topic_id = _extract_topic_id(topic_url)
        if not topic_id:
            continue

        try:
            topic_json = _request_json(_topic_json_url(topic_id))
        except Exception:
            continue

        diagnosis = _extract_expert_diagnosis(topic_json, developers)
        if diagnosis:
            topic_label_map[topic_url] = diagnosis

        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)

    enriched_rows: List[dict] = []
    for row in rows:
        topic_url = canonicalize_topic_url(row.get("topic_url", ""))
        diagnosis = topic_label_map.get(topic_url)
        out = dict(row)
        if diagnosis:
            out["normalized_label"] = diagnosis["label"]
            out["expert_username"] = diagnosis["username"]
            out["expert_quote"] = diagnosis["quote"]
            out["label_source"] = "developer_post"
        else:
            out.setdefault("normalized_label", "")
            out.setdefault("expert_username", "")
            out.setdefault("expert_quote", "")
            out.setdefault("label_source", "")
        enriched_rows.append(out)

    fieldnames = list(rows[0].keys()) if rows else []
    for extra in ["normalized_label", "expert_username", "expert_quote", "label_source"]:
        if extra not in fieldnames:
            fieldnames.append(extra)

    _rows_to_csv(output_manifest, enriched_rows, fieldnames)

    block1_rows = []
    for topic_url, diagnosis in sorted(topic_label_map.items()):
        block1_rows.append(
            {
                "Thread_URL": topic_url,
                "Expert_Username": diagnosis["username"],
                "Diagnostic_Quote": diagnosis["quote"],
                "Normalized_Label": diagnosis["label"].upper(),
            }
        )

    _rows_to_csv(
        output_block1,
        block1_rows,
        ["Thread_URL", "Expert_Username", "Diagnostic_Quote", "Normalized_Label"],
    )

    summary = {
        "mode": "enrich_manifest",
        "source_root": str(src),
        "input_manifest": str(input_manifest),
        "output_manifest": str(output_manifest),
        "output_block1": str(output_block1),
        "rows": len(rows),
        "topics_scanned": len(topic_urls),
        "topics_with_expert_label": len(topic_label_map),
        "rows_with_label": sum(1 for r in enriched_rows if (r.get("normalized_label") or "").strip()),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    summary_path = src / "expert_label_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    summary["summary_json"] = str(summary_path)
    return summary


def collect_expert_labeled_forum_logs(
    output_root: str,
    queries_json: Optional[str] = None,
    max_topics_per_query: int = 120,
    max_downloads: int = 300,
    sleep_ms: int = 300,
    include_zip: bool = True,
    after_date: Optional[str] = None,
    state_path: Optional[str] = None,
    skip_existing_labeled_topics: bool = True,
    existing_data_root: str = "data",
) -> dict:
    out = Path(output_root)
    downloads_dir = out / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)

    queries = _read_json_queries(queries_json)
    developers = _download_developer_usernames()

    state_file = Path(state_path) if state_path else (out / "expert_miner_state.json")
    state = _load_state(state_file)
    seen_topic_ids: Set[int] = set(int(x) for x in state.get("processed_topic_ids", []) if str(x).isdigit())
    seen_download_urls: Set[str] = set(state.get("processed_download_urls", []))

    known_labeled_topics: Set[str] = set()
    if skip_existing_labeled_topics:
        known_labeled_topics = _load_existing_labeled_topics(existing_data_root)

    query_items = list(queries.items())
    if after_date:
        query_items = [(k, f"{v} after:{after_date} order:latest") for k, v in query_items]

    topic_candidates: Dict[int, dict] = {}
    for q_key, q_text in query_items:
        try:
            topics = _search_topics(q_text, max_topics=max_topics_per_query)
        except Exception:
            continue
        for topic in topics:
            topic_id = topic.get("id")
            if topic_id is None:
                continue
            rec = topic_candidates.get(topic_id)
            if rec is None:
                topic_candidates[topic_id] = {
                    "topic": topic,
                    "query_keys": [q_key],
                    "query_texts": [q_text],
                }
            else:
                rec["query_keys"].append(q_key)
                rec["query_texts"].append(q_text)

        if sleep_ms > 0:
            time.sleep(sleep_ms / 1000.0)

    manifest_rows: List[dict] = []
    block1_rows: List[dict] = []
    saved_counter = 1

    topics_scanned = 0
    topics_with_label = 0
    topics_skipped_known = 0
    topics_skipped_state = 0
    topics_without_label = 0
    download_count = 0

    downloaded_topic_seen: Set[str] = set()

    for topic_id in sorted(topic_candidates.keys()):
        if max_downloads and download_count >= max_downloads:
            break

        if topic_id in seen_topic_ids:
            topics_skipped_state += 1
            continue

        try:
            topic_json = _request_json(_topic_json_url(topic_id))
        except Exception:
            continue

        topic_title = topic_json.get("title", "")
        topic_slug = topic_json.get("slug", "")
        topic_url = canonicalize_topic_url(f"{BASE_URL}/t/{topic_slug}/{topic_id}")

        if skip_existing_labeled_topics and topic_url in known_labeled_topics:
            topics_skipped_known += 1
            seen_topic_ids.add(topic_id)
            continue

        topics_scanned += 1
        diagnosis = _extract_expert_diagnosis(topic_json, developers)
        if diagnosis is None:
            topics_without_label += 1
            seen_topic_ids.add(topic_id)
            continue

        topics_with_label += 1
        if topic_url not in downloaded_topic_seen:
            block1_rows.append(
                {
                    "Thread_URL": topic_url,
                    "Expert_Username": diagnosis["username"],
                    "Diagnostic_Quote": diagnosis["quote"],
                    "Normalized_Label": diagnosis["label"].upper(),
                }
            )
            downloaded_topic_seen.add(topic_url)

        posts = topic_json.get("post_stream", {}).get("posts", [])
        for post in posts:
            if max_downloads and download_count >= max_downloads:
                break

            post_number = post.get("post_number", "")
            post_url = f"{topic_url}/{post_number}" if post_number else topic_url

            for raw_attachment in _iter_attachment_urls(post.get("cooked", "")):
                if max_downloads and download_count >= max_downloads:
                    break

                normalized_url = _normalize_download_url(raw_attachment)
                if not include_zip and ".zip" in normalized_url.lower():
                    continue
                if normalized_url in seen_download_urls:
                    continue

                seen_download_urls.add(normalized_url)
                status = "downloaded"
                error_msg = ""
                payload = b""
                headers = {}
                kind = ""

                try:
                    payload, headers = _request_bytes(normalized_url)
                    kind = _detect_kind(payload, normalized_url, headers)
                    if kind in {"html", "png", "gif", "jpg"}:
                        status = "not_log_payload"
                except Exception as exc:
                    status = "download_failed"
                    error_msg = str(exc)

                saved_name = ""
                if status == "downloaded":
                    ext = _ext_for_kind(kind)
                    safe_label = _safe_filename_label(diagnosis["label"])
                    saved_name = f"log_{saved_counter:05d}_{safe_label}{ext}"
                    saved_counter += 1
                    (downloads_dir / saved_name).write_bytes(payload)
                    download_count += 1

                manifest_rows.append(
                    {
                        "label": diagnosis["label"],
                        "normalized_label": diagnosis["label"],
                        "query": " | ".join(topic_candidates[topic_id]["query_texts"][:3]),
                        "topic_id": topic_id,
                        "topic_title": topic_title,
                        "topic_url": topic_url,
                        "post_number": post_number,
                        "post_url": post_url,
                        "attachment_url": _make_absolute(raw_attachment),
                        "download_url": normalized_url,
                        "saved_file": saved_name,
                        "status": status,
                        "kind": kind,
                        "bytes": len(payload),
                        "error": error_msg,
                        "source_type": "ArduPilot_Discuss",
                        "expert_username": diagnosis["username"],
                        "expert_post_number": diagnosis["post_number"],
                        "expert_quote": diagnosis["quote"],
                        "label_source": "developer_post",
                        "label_match": diagnosis["phrase"],
                        "label_score": diagnosis["score"],
                    }
                )

                if sleep_ms > 0:
                    time.sleep(sleep_ms / 1000.0)

        seen_topic_ids.add(topic_id)

    manifest_csv = out / "crawler_manifest_v2.csv"
    manifest_json = out / "crawler_manifest_v2.json"
    summary_json = out / "crawler_summary_v2.json"
    block1_csv = out / "block1_ardupilot_discuss.csv"

    manifest_fieldnames = [
        "label",
        "normalized_label",
        "query",
        "topic_id",
        "topic_title",
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
        "source_type",
        "expert_username",
        "expert_post_number",
        "expert_quote",
        "label_source",
        "label_match",
        "label_score",
    ]

    _rows_to_csv(manifest_csv, manifest_rows, manifest_fieldnames)
    manifest_json.write_text(json.dumps(manifest_rows, indent=2) + "\n", encoding="utf-8")

    block1_fieldnames = ["Thread_URL", "Expert_Username", "Diagnostic_Quote", "Normalized_Label"]
    _rows_to_csv(block1_csv, block1_rows, block1_fieldnames)

    state["last_run_utc"] = datetime.now(timezone.utc).isoformat()
    state["processed_topic_ids"] = sorted(seen_topic_ids)
    state["processed_download_urls"] = sorted(seen_download_urls)
    _write_state(state_file, state)

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "output_root": str(out),
        "downloads_dir": str(downloads_dir),
        "query_count": len(queries),
        "topic_candidates": len(topic_candidates),
        "topics_scanned": topics_scanned,
        "topics_with_expert_label": topics_with_label,
        "topics_without_expert_label": topics_without_label,
        "topics_skipped_known_labeled": topics_skipped_known,
        "topics_skipped_state": topics_skipped_state,
        "rows": len(manifest_rows),
        "downloaded": sum(1 for r in manifest_rows if r["status"] == "downloaded"),
        "not_log_payload": sum(1 for r in manifest_rows if r["status"] == "not_log_payload"),
        "download_failed": sum(1 for r in manifest_rows if r["status"] == "download_failed"),
        "artifacts": {
            "manifest_csv": str(manifest_csv),
            "manifest_json": str(manifest_json),
            "block1_csv": str(block1_csv),
            "summary_json": str(summary_json),
            "state_json": str(state_file),
        },
    }

    summary_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
