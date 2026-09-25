"""Check every thread annotation quote against the forum post it cites.

Each record in ``data/benchmark/thread_annotations.json`` that carries a
quote must name a post whose author matches and whose text contains the
quote verbatim (whitespace-normalised). By default the cached threads in
``data/raw/threads/`` are used (fetch them with ``training/fetch_threads.py``);
``--live N`` also re-downloads N random cited posts from the forum.

Example::

    python training/verify_thread_annotations.py --live 5
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from training.fetch_threads import fetch_topic  # noqa: E402


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def check(record: dict, thread: dict) -> str | None:
    """Return an error message, or None when the quote is verified."""
    post_number = int(record["diagnosing_post"].rstrip("/").rsplit("/", 1)[1])
    post = next((p for p in thread["posts"] if p["post_number"] == post_number), None)
    if post is None:
        return f"post {post_number} not found"
    if post["username"] != record["author"]:
        return f"author {record['author']!r} != {post['username']!r}"
    if _norm(record["quote"]) not in _norm(post["text"]):
        return "quote not found verbatim"
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--annotations", default="data/benchmark/thread_annotations.json")
    parser.add_argument("--threads-dir", default="data/raw/threads")
    parser.add_argument("--live", type=int, default=0, help="also re-fetch N random posts")
    args = parser.parse_args()

    records = json.loads((ROOT / args.annotations).read_text(encoding="utf-8"))["records"]
    quoted = [r for r in records if r["quote"] and r["diagnosing_post"]]
    failures = 0
    for record in quoted:
        topic = record["thread"].split(":", 1)[1]
        cached = ROOT / args.threads_dir / f"{topic}.json"
        if not cached.exists():
            print(f"{record['log_key']}: cached thread {topic} missing (run fetch_threads.py)")
            failures += 1
            continue
        error = check(record, json.loads(cached.read_text(encoding="utf-8")))
        if error:
            print(f"{record['log_key']}: {error}")
            failures += 1
    print(f"cached check: {len(quoted) - failures}/{len(quoted)} quotes verified")

    if args.live:
        sample = random.Random(20260925).sample(quoted, min(args.live, len(quoted)))
        live_fail = 0
        for record in sample:
            error = check(record, fetch_topic(record["thread"].split(":", 1)[1]))
            print(f"live {record['diagnosing_post']}: {error or 'ok'}")
            live_fail += bool(error)
        failures += live_fail
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
