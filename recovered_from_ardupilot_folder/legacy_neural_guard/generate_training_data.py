import subprocess
import time
import os
import shutil
from pymavlink import mavutil

# Configuration
SITL_PATH = "Tools/autotest/sim_vehicle.py"
LOGS_DIR = "logs"
TRAIN_NORMAL_DIR = "logs/train/normal"
TRAIN_ANOMALY_DIR = "logs/train/anomaly"
VEHICLE_TYPE = "ArduCopter"
LOCATION = "CMAC"


def run_sitl_session(scenario_name, is_anomaly=False, param_file=None):
    print(f"\n--- Starting SITL Session: {scenario_name} ---")
    
    # Build command
    cmd = [
        "python3", SITL_PATH,
        "-v", VEHICLE_TYPE,
        "-L", LOCATION,
        "--no-rebuild",
        "--no-mavproxy", # We'll connect directly
        "--speedup", "5" # Run 5x faster
    ]

    if param_file:
        cmd.extend(["--add-param-file", param_file])
    
    # Start SITL in background
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    try:
        # Connect to SITL
        # When running without MAVProxy, SITL usually listens on TCP 5760
        connection_string = 'tcp:127.0.0.1:5760'
        print(f"Connecting to SITL on {connection_string}...")
        master = mavutil.mavlink_connection(connection_string)
        
        # Wait for heartbeat with a timeout
        master.wait_heartbeat(timeout=60)
        print("Heartbeat received!")


        # Wait for EKF (Home position) - don't block forever
        print("Waiting for SITL to stabilize...")
        time.sleep(10) 

        # Set Mode to GUIDED
        print("Setting Mode to GUIDED...")
        # GUIDED = 4 for ArduCopter
        master.mav.set_mode_send(
            master.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            4)

        # Arm and Takeoff
        print("Arming...")
        master.mav.command_long_send(
            master.target_system, master.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
        
        # We'll just wait a bit instead of blocking arm wait which can be flaky
        time.sleep(2)

        print("Taking off...")
        master.mav.command_long_send(
            master.target_system, master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, 10)
        
        # Allow 15s (sim) for takeoff and flight
        print("Simulating flight...")
        time.sleep(15) 
        
        print("Landing...")
        master.mav.command_long_send(
            master.target_system, master.target_component,
            mavutil.mavlink.MAV_CMD_NAV_LAND, 0, 0, 0, 0, 0, 0, 0, 0)
        
        # Wait a bit for landing
        time.sleep(5)

        
    except Exception as e:
        print(f"Error during SITL run: {e}")
    finally:
        # Kill SITL
        print("Stopping SITL...")
        process.terminate()
        process.wait()
        subprocess.run(["pkill", "-9", "-f", "ArduCopter"], stderr=subprocess.DEVNULL)
        
        # Identify the latest log
        latest_log = os.path.join(LOGS_DIR, "latest.BIN")
        if os.path.exists(latest_log):
            target_dir = TRAIN_ANOMALY_DIR if is_anomaly else TRAIN_NORMAL_DIR
            target_path = os.path.join(target_dir, f"{scenario_name}_{int(time.time())}.BIN")
            shutil.copy(latest_log, target_path)
            print(f"Saved log to: {target_path}")
        else:
            print("Error: No log found!")

if __name__ == "__main__":
    # Ensure dirs exist
    os.makedirs(TRAIN_NORMAL_DIR, exist_ok=True)
    os.makedirs(TRAIN_ANOMALY_DIR, exist_ok=True)

    # 1. Normal Flight
    run_sitl_session("normal_flight_1", is_anomaly=False)
    
    # 2. Motor Failure
    run_sitl_session("motor_failure_1", is_anomaly=True, param_file="simulate_motor_failure.parm")
    
    print("\nData Generation Finished!")
