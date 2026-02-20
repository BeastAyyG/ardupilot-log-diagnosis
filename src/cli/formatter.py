import json

class DiagnosisFormatter:
    """Formats diagnosis output for humans."""
    
    def format_terminal(self, diagnoses: list, metadata: dict) -> str:
        lines = []
        lines.append("╔═══════════════════════════════════════╗")
        lines.append("║  ArduPilot Log Diagnosis Report       ║")
        lines.append("╠═══════════════════════════════════════╣")
        filename = metadata.get('log_file', 'unknown').split('/')[-1]
        lines.append(f"║  Log:      {filename:<27}║")
        duration = metadata.get('duration_sec', 0.0)
        mins = int(duration // 60)
        secs = int(duration % 60)
        dur_str = f"{mins}m {secs}s"
        lines.append(f"║  Duration: {dur_str:<27}║")
        vehicle = f"{metadata.get('vehicle_type', 'Unknown')} {metadata.get('firmware', '')}"
        lines.append(f"║  Vehicle:  {vehicle:<27}║")
        lines.append("╚═══════════════════════════════════════╝")
        lines.append("")
        
        if not diagnoses:
            lines.append("HEALTHY — No critical failures detected.")
            lines.append("\nOverall: SAFE TO FLY")
            return "\n".join(lines)
            
        overall_safe = True
        
        for d in diagnoses:
            ftype = d["failure_type"].upper()
            pct = int(d["confidence"] * 100)
            sev = d["severity"].upper()
            if sev == "CRITICAL":
                overall_safe = False
                
            lines.append(f"{sev} — {ftype} ({pct}%)")
            for ev in d.get("evidence", []):
                feature = ev.get("feature")
                val = ev.get("value")
                thresh = ev.get("threshold")
                lines.append(f"  {feature} = {val} (limit: {thresh})")
            lines.append(f"  Method: {d['detection_method']}")
            lines.append(f"  Fix: {d['recommendation']}")
            lines.append("")
            
        if overall_safe:
            lines.append("Overall: PROCEED WITH CAUTION")
        else:
            lines.append("Overall: NOT SAFE TO FLY")
            
        return "\n".join(lines)
        
    def format_json(self, diagnoses: list, metadata: dict, features: dict) -> str:
        return json.dumps({
            "metadata": metadata,
            "diagnoses": diagnoses,
            "features_summary": {k: v for k, v in features.items() if not k.startswith("_")}
        }, indent=2)
