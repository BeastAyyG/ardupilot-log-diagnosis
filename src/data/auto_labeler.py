#!/usr/bin/env python3
"""
Auto-Labeler: Extracts labels from ArduPilot forum threads.

For each raw .bin file in the manifest that has a source_url,
it fetches the forum thread with ScrapeGraphAI and extracts:
- The community root-cause verdict
- Confidence level
- Expert quotes

Output is written to data/to_label/<date>_ai_labeled/ground_truth_candidate.json
for HUMAN REVIEW before being merged into ground_truth.json.

POLICY: This script NEVER writes to ground_truth.json directly.
All AI-extracted labels MUST be reviewed by a human first.
"""

import os
import json
import time
import argparse
from pathlib import Path
from datetime import datetime, timezone
import requests
from pydantic import BaseModel, Field
import json

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

VALID_LABELS = [
    "vibration_high",
    "compass_interference",
    "ekf_failure",
    "motor_imbalance",
    "power_instability",
    "rc_failsafe",
    "gps_quality_poor",
    "pid_tuning_issue",
]

EXTRACTION_PROMPT = """
You are an ArduPilot flight log expert. Analyze this forum thread and extract:

1. root_cause: ONE of these exact labels only:
   - vibration_high (propeller/motor vibration clipping IMU)
   - compass_interference (magnetic interference causing yaw/EKF errors)
   - ekf_failure (EKF variance/lane switch causing loss of control)
   - motor_imbalance (motor desync, ESC failure, or asymmetric thrust)
   - power_instability (battery brownout, voltage sag, mid-air reboot)
   - rc_failsafe (radio signal loss triggering failsafe)
   - gps_quality_poor (GPS glitch, HDOP spike, position jump)
   - pid_tuning_issue (oscillation/instability from bad PID gains)
   - UNKNOWN (if consensus is unclear or not reached)

2. confidence: "high" (ArduPilot dev or expert confirms), "medium" (community consensus), or "low" (speculation only)

3. expert_quote: The most diagnostic sentence from the thread (max 120 chars)

4. community_consensus: true or false — was a single root cause agreed upon?

Return ONLY valid JSON with exactly these 4 keys and nothing else.
"""

class LabelExtraction(BaseModel):
    root_cause: str = Field(description="Exact label: vibration_high, compass_interference, ekf_failure, motor_imbalance, power_instability, rc_failsafe, gps_quality_poor, pid_tuning_issue, or UNKNOWN")
    confidence: str = Field(description="'high', 'medium', or 'low'")
    expert_quote: str = Field(description="Diagnostic quote from thread")
    community_consensus: bool = Field(description="Was a consensus reached?")

def fetch_and_label(url: str, sgai_key: str) -> dict:
    """Fetch a forum thread and extract label using ScrapeGraphAI."""
    try:
        from scrapegraph_py import Client
        
        # Fetch HTML to avoid scraping blocks inside the ScrapeGraph node
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            html_source = resp.text
        except:
            html_source = url # fallback to direct URL
            
        client = Client(api_key=sgai_key)
        result = client.smartscraper(
            user_prompt=EXTRACTION_PROMPT,
            website_html=html_source if len(html_source) > 100 else url,
            output_schema=LabelExtraction
        )
        
        # Output schema guarantees it conforms, but extract from dict
        if isinstance(result, str):
            result = json.loads(result)
            
        # SDK v2.x returns {'result': {...}}
        if 'result' in result and isinstance(result['result'], dict):
            return result['result']
        return result
        
    except Exception as e:
        return {"error": str(e), "root_cause": "UNKNOWN", "confidence": "low",
                "expert_quote": "", "community_consensus": False}


def run_auto_labeler(manifest_path: str, output_dir: str, limit: int = 20):
    """Process a crawler manifest and extract labels for each entry with a source_url."""
    sgai_key = os.getenv("SGAI_API_KEY")

    if not sgai_key:
        print("ERROR: SGAI_API_KEY not set in .env")
        return

    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(manifest_path) as f:
        manifest = json.load(f)

    entries = manifest if isinstance(manifest, list) else manifest.get("logs", [])
    print(f"[*] Found {len(entries)} entries in manifest. Processing up to {limit}...")

    candidates = []
    seen_urls = set()
    processed = 0

    for entry in entries:
        if processed >= limit:
            break

        # Support both forum_collector manifest format (saved_file) and ground_truth format (filename)
        source_url = entry.get("topic_url") or entry.get("source_url") or entry.get("attachment_url")
        filename = entry.get("saved_file") or entry.get("filename", "")
        status = entry.get("status", "downloaded")  # ground_truth entries have no status

        if not source_url or source_url in seen_urls:
            continue
        if status and status != "downloaded":
            continue
        if not filename.endswith(".bin"):
            continue

        # Use topic_url if we have it (better context than attachment URL)
        thread_url = entry.get("topic_url") or source_url
        seen_urls.add(thread_url)

        print(f"  [{processed+1}] {filename}")
        print(f"       URL: {thread_url}")

        result = fetch_and_label(thread_url, sgai_key)

        root_cause = result.get("root_cause", "UNKNOWN")
        confidence = result.get("confidence", "low")
        consensus = result.get("community_consensus", False)
        quote = result.get("expert_quote", "")

        # Only include if there's a valid label and community consensus
        if root_cause in VALID_LABELS and consensus:
            candidates.append({
                "filename": filename,
                "labels": [root_cause],
                "source_url": thread_url,
                "source_type": "ArduPilot_Discuss",
                "expert_quote": quote[:200],
                "confidence": confidence,
                "ai_extracted": True,  # MARKER: Must be human-reviewed before use
                "raw_ai_result": result
            })
            print(f"       ✅ Label: {root_cause} ({confidence})")
        else:
            print(f"       ⚠️  No consensus or unknown label: {root_cause}")
            print(f"         [Debug] Raw Result: {result}")

        processed += 1
        time.sleep(1.5)  # Rate limit

    # Save for HUMAN REVIEW — never goes directly to ground_truth.json
    output = {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "manifest_source": str(manifest_path),
            "total_processed": processed,
            "total_candidates": len(candidates),
            "policy": {
                "ai_extracted": True,
                "requires_human_review": True,
                "fabricated_labels": False
            }
        },
        "candidates": candidates
    }

    out_file = output_dir / "ai_label_candidates.json"
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\n✅ Done. {len(candidates)}/{processed} qualified candidates saved to:")
    print(f"   {out_file}")
    print(f"\n⚠️  REQUIRED: Human review before adding to ground_truth.json")
    print(f"   Run: python3 training/import_clean_batch.py --source {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Auto-label forum logs using ScrapeGraphAI")
    parser.add_argument("manifest", help="Path to crawler_manifest.json from collect-forum")
    parser.add_argument("--output-dir", default="data/to_label/ai_labeled",
                        help="Output directory for label candidates")
    parser.add_argument("--limit", type=int, default=20,
                        help="Max threads to process (API cost control)")
    args = parser.parse_args()
    run_auto_labeler(args.manifest, args.output_dir, args.limit)


if __name__ == "__main__":
    main()
