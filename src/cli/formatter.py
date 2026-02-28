import json

class DiagnosisFormatter:
    """Formats diagnosis output for humans."""
    
    def format_terminal(self, diagnoses: list, metadata: dict, decision: dict = None) -> str:
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
            if decision:
                lines.append(f"Decision: {decision.get('status', 'healthy').upper()}")
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

        if decision:
            lines.append("")
            lines.append(f"Decision: {decision.get('status', 'unknown').upper()}")
            top_guess = decision.get("top_guess")
            top_conf = int(float(decision.get("top_confidence", 0.0)) * 100)
            if top_guess:
                lines.append(f"Top Guess: {top_guess.upper()} ({top_conf}%)")
                
            subsystems = decision.get("ranked_subsystems", [])
            if subsystems:
                lines.append("\nSubsystem Blame Ranking:")
                for sub in subsystems[:3]: # top 3
                    lines.append(f"  - {sub['subsystem']:>18}: {int(sub['likelihood']*100)}%")
                    
            if decision.get("requires_human_review"):
                lines.append("\nHuman Review: REQUIRED")
            else:
                lines.append("\nHuman Review: Not required")
            
        return "\n".join(lines)
        
    def format_json(self, diagnoses: list, metadata: dict, features: dict, decision: dict = None) -> str:
        return json.dumps({
            "metadata": metadata,
            "diagnoses": diagnoses,
            "decision": decision or {},
            "features_summary": {k: v for k, v in features.items() if not k.startswith("_")}
        }, indent=2)
