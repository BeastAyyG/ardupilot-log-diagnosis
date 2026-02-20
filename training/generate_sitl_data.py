"""
Generate synthetic failure data in SITL using MAVProxy.
SITL_FAILURE_CONFIGS provides params for simulating specific failures.
"""

SITL_FAILURE_CONFIGS = {
    "vibration": {
        "params": {"SIM_ACC_RND": 5, "SIM_VIB_MOT_MAX": 10},
        "label": ["vibration_high"],
        "duration_sec": 90
    },
    "gps_loss": {
        "params": {"SIM_GPS_DISABLE": 1},
        "label": ["gps_quality_poor"],
        "duration_sec": 60
    },
    "gps_glitch": {
        "params": {"SIM_GPS_GLITCH_X": 100, "SIM_GPS_GLITCH_Y": 100},
        "label": ["gps_quality_poor"],
        "duration_sec": 60
    },
    "compass_interference": {
        "params": {"SIM_MAG_MOT": 50},
        "label": ["compass_interference"],
        "duration_sec": 90
    },
    "motor_failure": {
        "params": {"SIM_ENGINE_FAIL": 1, "SIM_ENGINE_MUL": 0.5},
        "label": ["motor_imbalance"],
        "duration_sec": 60
    },
    "rc_failsafe": {
        "params": {"SIM_RC_FAIL": 1},
        "label": ["rc_failsafe"],
        "duration_sec": 30
    },
    "wind": {
        "params": {"SIM_WIND_SPD": 15, "SIM_WIND_DIR": 180},
        "label": ["healthy"],
        "duration_sec": 90
    },
    "healthy": {
        "params": {},
        "label": ["healthy"],
        "duration_sec": 120
    }
}

def print_sitl_commands(failure_type: str):
    config = SITL_FAILURE_CONFIGS.get(failure_type)
    if not config:
        print(f"Unknown failure type: {failure_type}")
        return
        
    print(f"--- Commands for {failure_type} ---")
    for param, value in config["params"].items():
        print(f"param set {param} {value}")
    print(f"\nRun for {config['duration_sec']} seconds.")
    print("Labels to apply in dataset:", config["label"])

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print_sitl_commands(sys.argv[1])
    else:
        print("Available failures:")
        for k in SITL_FAILURE_CONFIGS:
            print(f" - {k}")
