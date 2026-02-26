import os
import logging
from .forum_collector import collect_forum_logs

def run_orchestration(output_root="data/raw_downloads"):
    """Orchestrate the collection of logs from ArduPilot forum."""
    logging.info("Starting forum log collection orchestration...")
    
    # Example labels we are looking for
    labels = ["vibration_high", "compass_interference", "power_instability", "ekf_failure"]
    
    summary = collect_forum_logs(
        output_root=output_root,
        max_per_query=20,
        max_topics_per_query=50
    )
    
    return summary

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_orchestration()
