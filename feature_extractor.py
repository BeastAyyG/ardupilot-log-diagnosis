#!/usr/bin/env python3
"""
ArduPilot Log Feature Extractor

Parses flight logs and extracts statistical features (mean, max, min, std)
for critical telemetry streams like VIBE, MAG, BAT, and GPS.
"""

import sys
import json
import argparse
from typing import Dict, List, Any
import numpy as np
from pymavlink import mavutil


class FeatureExtractor:
    """Extracts aggregate statistical features from ArduPilot telemetry logs."""
    
    def __init__(self, log_path: str):
        self.log_path = log_path
        # Pre-allocate data stores for telemetry streams
        self.data: Dict[str, Any] = {
            'vibe_x': [], 'vibe_y': [], 'vibe_z': [], 'clips': [],
            'mag_field': [],
            'voltage': [], 'current': [],
            'hdop': [], 'nsats': [],
            'motors': {i: [] for i in range(1, 5)}
        }

    def _safe_stats(self, data: List[float], prefix: str) -> Dict[str, float]:
        """Calculates standard statistics for a given data array safely."""
        result = {}
        if data and len(data) > 0:
            arr = np.array(data)
            result[f'{prefix}_mean'] = float(np.mean(arr))
            result[f'{prefix}_max'] = float(np.max(arr))
            result[f'{prefix}_min'] = float(np.min(arr))
            result[f'{prefix}_std'] = float(np.std(arr))
            result[f'{prefix}_range'] = float(np.max(arr) - np.min(arr))
        else:
            for stat in ['mean', 'max', 'min', 'std', 'range']:
                result[f'{prefix}_{stat}'] = 0.0
        return result

    def extract(self) -> Dict[str, float]:
        """Runs the extraction process over the log file."""
        try:
            mlog = mavutil.mavlink_connection(self.log_path)
        except Exception as e:
            raise FileNotFoundError(f"Failed to open log file {self.log_path}: {e}")
        
        while True:
            msg = mlog.recv_match(blocking=False)
            if msg is None:
                break
                
            mtype = msg.get_type()
            
            if mtype == 'VIBE':
                self.data['vibe_x'].append(msg.VibeX)
                self.data['vibe_y'].append(msg.VibeY)
                self.data['vibe_z'].append(msg.VibeZ)
                self.data['clips'].append(getattr(msg, 'Clip0', 0))
                
            elif mtype == 'MAG':
                # Calculate total magnetic field vector length
                field = np.sqrt(msg.MagX**2 + msg.MagY**2 + msg.MagZ**2)
                self.data['mag_field'].append(field)
                
            elif mtype == 'BAT':
                self.data['voltage'].append(msg.Volt)
                self.data['current'].append(msg.Curr)
                
            elif mtype == 'GPS':
                self.data['hdop'].append(getattr(msg, 'HDop', 0))
                self.data['nsats'].append(getattr(msg, 'NSats', 0))
                
            elif mtype == 'RCOU':
                # Track outputs for motors 1-4 (typically Quadcopter)
                for i in range(1, 5):
                    self.data['motors'][i].append(getattr(msg, f'C{i}', 0))
                    
        return self._compile_features()

    def _compile_features(self) -> Dict[str, float]:
        """Compiles raw arrays into aggregated statistical features."""
        features = {}
        
        # Vibration
        features.update(self._safe_stats(self.data['vibe_x'], 'vibe_x'))
        features.update(self._safe_stats(self.data['vibe_y'], 'vibe_y'))
        features.update(self._safe_stats(self.data['vibe_z'], 'vibe_z'))
        features['clip_total'] = float(sum(self.data['clips']))
        
        # Power & Nav
        features.update(self._safe_stats(self.data['mag_field'], 'mag'))
        features.update(self._safe_stats(self.data['voltage'], 'volt'))
        features.update(self._safe_stats(self.data['current'], 'curr'))
        features.update(self._safe_stats(self.data['hdop'], 'hdop'))
        features.update(self._safe_stats(self.data['nsats'], 'nsats'))
        
        # Motors
        motor_data = self.data['motors']
        if all(motor_data[i] for i in range(1, 5)):
            means = [np.mean(motor_data[i]) for i in range(1, 5)]
            features['motor_spread'] = float(max(means) - min(means))
            features['motor_std'] = float(np.std(means))
        else:
            features['motor_spread'] = 0.0
            features['motor_std'] = 0.0
            
        return features


def main() -> None:
    """Main execution entry point."""
    parser = argparse.ArgumentParser(description="Extract statistical features from an ArduPilot .BIN log.")
    parser.add_argument("log_path", type=str, help="Path to the .BIN log file")
    args = parser.parse_args()

    extractor = FeatureExtractor(args.log_path)
    try:
        features = extractor.extract()
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
        
    print("\nEXTRACTED FEATURES:")
    print("=" * 45)
    for k, v in sorted(features.items()):
        print(f"  {k:<25} {v:>12.4f}")
        
    out_path = args.log_path.replace('.BIN', '_features.json').replace('.bin', '_features.json')
    with open(out_path, 'w') as f:
        json.dump(features, f, indent=4)
    print(f"\nSaved features to: {out_path}")


if __name__ == '__main__':
    main()
