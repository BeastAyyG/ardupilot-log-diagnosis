import urllib.request
import json
import os
import ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

QUERIES = {
    "vibration_high": "high vibration crash .bin",
    "compass_interference": "compass variance crash .bin",
    "motor_imbalance": "motor failure thrust desync .bin",
    "gps_quality_poor": "gps glitch loss hdop crash .bin"
}

def search_and_download():
    os.makedirs("dataset", exist_ok=True)
    count = 1
    labels_dict = []
    
    for label, query in QUERIES.items():
        print(f"Searching for: {label}")
        q = urllib.parse.quote(query)
        url = f"https://discuss.ardupilot.org/search.json?q={q}"
        
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, context=ctx) as response:
                data = json.loads(response.read().decode())
                
            topics = data.get("topics", [])
            downloaded_for_label = 0
            
            for t in topics:
                if downloaded_for_label >= 5:
                    break
                    
                topic_id = t["id"]
                topic_slug = t["slug"]
                t_url = f"https://discuss.ardupilot.org/t/{topic_id}.json"
                
                req2 = urllib.request.Request(t_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req2, context=ctx) as r2:
                    t_data = json.loads(r2.read().decode())
                    
                posts = t_data.get("post_stream", {}).get("posts", [])
                for p in posts:
                    if downloaded_for_label >= 5:
                        break
                        
                    content = p.get("cooked", "")
                    if ".BIN" in content or ".bin" in content:
                        import re
                        urls = re.findall(r'href=[\'"]?([^\'" >]+\.bin)[\'"]?', content, re.IGNORECASE)
                        for file_url in urls:
                            if "dropbox.com" in file_url:
                                continue # Skip dropbox links as they send HTML
                                
                            if not file_url.startswith("http"):
                                file_url = "https://discuss.ardupilot.org" + file_url
                                    
                            filename = f"crash_{count:03d}.BIN"
                            filepath = os.path.join("dataset", filename)
                            
                            print(f" Downloading {file_url} to {filename}...")
                            try:
                                freq = urllib.request.Request(file_url, headers={'User-Agent': 'Mozilla/5.0'})
                                with urllib.request.urlopen(freq, context=ctx) as fr:
                                    content_bytes = fr.read()
                                    if content_bytes.startswith(b'<!DOCTYPE html>') or content_bytes.startswith(b'<html'):
                                        print("  Error: downloaded HTML instead of data. Skipping.")
                                        continue
                                    with open(filepath, 'wb') as out_f:
                                        out_f.write(content_bytes)
                                
                                labels_dict.append({
                                    "filename": filename,
                                    "labels": [label],
                                    "source_url": f"https://discuss.ardupilot.org/t/{topic_slug}/{topic_id}/{p['post_number']}",
                                    "source_type": "forum",
                                    "expert_quote": "auto-downloaded based on search query",
                                    "confidence": "medium"
                                })
                                count += 1
                                downloaded_for_label += 1
                                break # get only one per post
                            except Exception as e:
                                print(f" Failed to download: {e}")
                                
        except Exception as e:
            print(f"Error searching {label}: {e}")
            
    # Save seed
    if labels_dict:
        gt_path = "ground_truth.json"
        with open(gt_path, "r") as f:
            gt = json.load(f)
            
        gt["logs"] = labels_dict
        
        with open(gt_path, "w") as f:
            json.dump(gt, f, indent=2)
            
        print(f"\nSaved {len(labels_dict)} logs to ground_truth.json")

search_and_download()
