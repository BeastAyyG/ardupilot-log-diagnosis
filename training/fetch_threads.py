"""Cache the full post stream of every forum thread cited in the registry.

Read-only against discuss.ardupilot.org (public Discourse JSON API). Output
goes to the git-ignored ``data/raw/threads/<topic_id>.json`` so annotations in
``data/benchmark/thread_annotations.json`` can be re-checked against the
exact post text.

Example::

    python training/fetch_threads.py
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://discuss.ardupilot.org"
CHUNK = 20


def _get(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": "logdiagnosis-research/1.0"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except Exception:  # noqa: BLE001 - retry transient network failures
            if attempt == 3:
                raise
            time.sleep(2 ** (attempt + 1))
    raise RuntimeError("unreachable")


def plain_text(cooked: str) -> str:
    text = re.sub(r"<aside class=\"quote.*?</aside>", " [quoted earlier post] ", cooked, flags=re.S)
    text = re.sub(r"<br\s*/?>|</p>|</li>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", html.unescape(text)).strip()


def fetch_topic(topic_id: str) -> dict:
    topic = _get(f"{BASE}/t/{topic_id}.json")
    posts = {post["id"]: post for post in topic["post_stream"]["posts"]}
    missing = [pid for pid in topic["post_stream"]["stream"] if pid not in posts]
    for start in range(0, len(missing), CHUNK):
        query = "&".join(f"post_ids[]={pid}" for pid in missing[start : start + CHUNK])
        extra = _get(f"{BASE}/t/{topic_id}/posts.json?{query}")
        posts.update({post["id"]: post for post in extra["post_stream"]["posts"]})
    ordered = [posts[pid] for pid in topic["post_stream"]["stream"] if pid in posts]
    return {
        "topic_id": topic_id,
        "title": topic["title"],
        "slug": topic["slug"],
        "posts": [
            {
                "post_number": post["post_number"],
                "username": post["username"],
                "trust_level": post.get("trust_level"),
                "staff": bool(post.get("staff") or post.get("moderator") or post.get("admin")),
                "created_at": post["created_at"],
                "text": plain_text(post["cooked"]),
                "links": sorted(set(re.findall(r'href="([^"]+)"', post["cooked"]))),
            }
            for post in ordered
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--incidents", default="data/benchmark/incidents.csv")
    parser.add_argument("--out-dir", default="data/raw/threads")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    out = ROOT / args.out_dir
    out.mkdir(parents=True, exist_ok=True)
    with (ROOT / args.incidents).open(encoding="utf-8") as handle:
        ids = sorted(
            {row["incident_id"].split(":", 1)[1] for row in csv.DictReader(handle)
             if row["incident_id"].startswith("discuss:")}
        )
    for topic_id in ids:
        path = out / f"{topic_id}.json"
        if path.exists() and not args.refresh:
            continue
        try:
            data = fetch_topic(topic_id)
        except Exception as exc:  # noqa: BLE001
            print(f"{topic_id}: FAILED {exc}")
            continue
        path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{topic_id}: {len(data['posts'])} posts - {data['title']}")
        time.sleep(1.0)  # be polite to the forum


if __name__ == "__main__":
    main()
