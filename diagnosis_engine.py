#!/usr/bin/env python3
"""
ArduPilot Log Diagnosis Engine

Applies heuristic rules against extracted telemetry features to output
diagnostic reports and identify common hardware failures.
"""

import sys
import argparse
from typing import Dict, List, Any
from feature_extractor import FeatureExtractor


class DiagnosisEngine:
    """Evaluates telemetry features against a defined set of failure heuristics."""
    
    # Rule syntax: (Feature Key, Operator, Threshold)
    RULES = {
        'vibration_issue': {
            'checks': [
                ('vibe_x_max', '>', 30.0),
                ('vibe_y_max', '>', 30.0),
                ('vibe_z_max', '>', 30.0),
                ('clip_total', '>', 0.0),
            ],
            'fix': 'Balance propellers, tighten motor mounts, or improve flight controller damping.'
        },
        'compass_interference': {
            'checks': [
                ('mag_range', '>', 200.0),
                ('mag_std', '>', 50.0),
            ],
            'fix': 'Move compass away from power distribution boards, motors, or high-current wiring.'
        },
        'power_issue': {
            'checks': [
                ('volt_min', '<', 10.5),
                ('volt_range', '>', 2.0),
            ],
            'fix': 'Check battery health, internal resistance, and verify power module calibration.'
        },
        'gps_issue': {
            'checks': [
                ('hdop_max', '>', 2.0),
                ('nsats_min', '<', 8.0),
            ],
            'fix': 'Ensure a clear view of the sky, check GPS module wiring, or wait for better lock before arming.'
        },
        'motor_imbalance': {
            'checks': [
                ('motor_spread', '>', 100.0),
                ('motor_std', '>', 40.0),
            ],
            'fix': 'Check for twisted motor mounts, verify center of gravity (CG), or inspect for a failing ESC/Motor.'
        }
    }

    def __init__(self, features: Dict[str, float]):
        self.features = features

    def evaluate(self) -> List[Dict[str, Any]]:
        """
        Evaluates the loaded features against the rule definitions.
        
        Returns:
            List[Dict]: A list of diagnostic results sorted by confidence.
        """
        results = []
        
        for failure_name, rule_def in self.RULES.items():
            triggered_count = 0
            evidence = []
            
            for field, operator, threshold in rule_def['checks']:
                val = self.features.get(field, 0.0)
                
                # Evaluate condition
                condition_met = False
                if operator == '>' and val > threshold:
                    condition_met = True
                elif operator == '<' and val < threshold:
                    condition_met = True
                    
                if condition_met:
                    triggered_count += 1
                    evidence.append(f"{field} = {val:.2f} (threshold: {operator} {threshold})")
            
            # If any checks triggered, formulate a report
            if triggered_count > 0:
                confidence = triggered_count / len(rule_def['checks'])
                results.append({
                    'failure': failure_name,
                    'confidence': round(confidence, 2),
                    'evidence': evidence,
                    'fix': rule_def['fix']
                })
                
        # Sort so highest confidence alerts appear first
        results.sort(key=lambda x: x['confidence'], reverse=True)
        
        # If no issues found, log "healthy"
        if not results:
            results.append({
                'failure': 'healthy_flight',
                'confidence': 1.0,
                'evidence': ['All sensor heuristics within normal operating parameters.'],
                'fix': 'No action needed. Ready for flight.'
            })
            
        return results

    @staticmethod
    def print_report(results: List[Dict[str, Any]]) -> None:
        """Formats and prints the diagnosis results."""
        print("\n" + "=" * 60)
        print("                 LOG DIAGNOSIS REPORT")
        print("=" * 60)
        
        for r in results:
            pct = r['confidence'] * 100
            print(f"\n[{pct:.0f}%] {r['failure'].upper()}")
            for e in r['evidence']:
                print(f"  -> {e}")
            print(f"  Fix: {r['fix']}")
        print("\n" + "=" * 60)


def main() -> None:
    """Main execution entry point."""
    parser = argparse.ArgumentParser(description="Diagnose ArduPilot flight logs for common anomalies.")
    parser.add_argument("log_path", type=str, help="Path to the .BIN log file")
    args = parser.parse_args()

    # Step 1: Extract features
    print(f"Extracting features from {args.log_path}...")
    try:
        extractor = FeatureExtractor(args.log_path)
        features = extractor.extract()
    except Exception as e:
        print(f"Extraction failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Step 2: Diagnose
    engine = DiagnosisEngine(features)
    results = engine.evaluate()
    
    # Step 3: Report
    DiagnosisEngine.print_report(results)


if __name__ == '__main__':
    main()
