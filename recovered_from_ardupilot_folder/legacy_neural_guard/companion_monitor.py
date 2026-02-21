import time
import psutil
from pymavlink import mavutil
import threading
from flask import Flask, render_template, jsonify
import joblib
import pandas as pd
import numpy as np
import os
import logging
import requests

# Configuration
FC_CONNECTION = "tcp:127.0.0.1:5760"
COMPANION_ID = 255
FLASK_PORT = 5000
MODEL_FILE = "anomaly_model.joblib"
LOG_FILE = "neural_guard.log"
CLOUD_ENDPOINT = "http://localhost:8000/api/ingest"

# Setup Logging
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(console_handler)

# Load AI Model (Global)
try:
    logging.info(f"Loading AI Model from {MODEL_FILE}...")
    ai_model = joblib.load(MODEL_FILE)
    logging.info("AI Model Loaded Successfully!")
except Exception as e:
    logging.error(f"AI Model load failed: {e}")
    ai_model = None

# Global state to share data betwee threads
current_stats = {
    "cpu": 0,
    "mem": 0,
    "temp": 45.0,
    "ai_risk": 0.0,
    "flight_data": {
        "volt": 0, "curr": 0,
        "vibex": 0, "vibey": 0, "vibez": 0,
        "roll": 0, "pitch": 0, "yaw": 0,
        "c1": 1000, "c2": 1000, "c3": 1000, "c4": 1000
    },
    "connection_status": "disconnected"
}

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    # Helper for legacy dashboard
    return jsonify(current_stats)

@app.route('/api/telemetry')
def get_telemetry():
    # New API Contract for Cloud Agent
    return jsonify({
        "drone_id": "drone_01",
        "timestamp_ms": int(time.time() * 1000),
        "status": {
            "connection": current_stats["connection_status"],
            "ai_active": ai_model is not None,
            "battery_pct": int((current_stats["flight_data"]["volt"] - 10.0) / (12.6 - 10.0) * 100) if current_stats["flight_data"]["volt"] > 0 else 0
        },
        "inference": {
            "risk_score": current_stats["ai_risk"],
            "anomaly_type": "vibration" if current_stats["ai_risk"] > 0.5 else "none", # Mock classification
            "confidence": 0.95 if current_stats["ai_risk"] > 0.5 else 0.99
        },
        "physics": {
            "roll": current_stats["flight_data"]["roll"],
            "pitch": current_stats["flight_data"]["pitch"],
            "vibe_x": current_stats["flight_data"]["vibex"]
        }
    })

def mavlink_worker():
    """Background thread to handle MAVLink communication and AI Inference."""
    logging.info(f"Connecting to Flight Controller on {FC_CONNECTION}...")
    start_time = time.time()
    
    # Retry Loop for Connection
    while True:
        try:
            logging.info(f"Connecting to Flight Controller on {FC_CONNECTION}...")
            master = mavutil.mavlink_connection(
                FC_CONNECTION, 
                source_system=COMPANION_ID, 
                source_component=mavutil.mavlink.MAV_COMP_ID_ONBOARD_COMPUTER
            )
            master.wait_heartbeat(timeout=5)
            logging.info("Connected to FC!")
            current_stats["connection_status"] = "online"
            
            logging.info("Requesting Data Streams...")
            master.mav.request_data_stream_send(
                master.target_system, master.target_component,
                mavutil.mavlink.MAV_DATA_STREAM_ALL, 10, 1)
            break 
        except Exception as e:
            logging.error(f"MAVLink Connection failed: {e}. Retrying in 5s...")
            current_stats["connection_status"] = "connecting"
            time.sleep(5)

    flight_state = {
        'Volt': 0, 'Curr': 0,
        'VibeX': 0, 'VibeY': 0, 'VibeZ': 0,
        'Roll': 0, 'Pitch': 0, 'Yaw': 0,
        'C1': 1000, 'C2': 1000, 'C3': 1000, 'C4': 1000
    }

    last_heartbeat = 0
    last_inference = 0
    last_stats_update = 0

    # Main Loop
    while True:
        now = time.time()
        
        # 1. Provide Heartbeat (1Hz)
        if now - last_heartbeat > 1.0:
            try:
                master.mav.heartbeat_send(
                    mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                    mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                    0, 0, 0)
                last_heartbeat = now
            except Exception as e:
                logging.error(f"Heartbeat failed (Connection lost?): {e}")
                # Ideally break to outer retry loop, but for now just log
                pass

        # 2. Receive Messages
        try:
            msg = master.recv_match(type=['BATTERY_STATUS', 'SYS_STATUS', 'VIBRATION', 'ATTITUDE', 'SERVO_OUTPUT_RAW'], blocking=False)
            if msg:
                msg_type = msg.get_type()
                if msg_type == 'SYS_STATUS':
                        flight_state['Volt'] = msg.voltage_battery / 1000.0
                        flight_state['Curr'] = msg.current_battery / 100.0
                        flight_state['Curr'] = max(flight_state['Curr'], 0)

                elif msg_type == 'VIBRATION':
                    flight_state['VibeX'] = msg.vibration_x
                    flight_state['VibeY'] = msg.vibration_y
                    flight_state['VibeZ'] = msg.vibration_z
                
                elif msg_type == 'ATTITUDE':
                    flight_state['Roll'] = np.degrees(msg.roll)
                    flight_state['Pitch'] = np.degrees(msg.pitch)
                    flight_state['Yaw'] = np.degrees(msg.yaw)
                    
                elif msg_type == 'SERVO_OUTPUT_RAW':
                    flight_state['C1'] = msg.servo1_raw
                    flight_state['C2'] = msg.servo2_raw
                    flight_state['C3'] = msg.servo3_raw
                    flight_state['C4'] = msg.servo4_raw
        except Exception as e:
                logging.error(f"MAVLink receive error: {e}")

        # 3. Running Inference (5Hz)
        if ai_model and (now - last_inference > 0.2):
            try:
                X_live = pd.DataFrame([flight_state]) 
                X_live = X_live[['Volt', 'Curr', 'VibeX', 'VibeY', 'VibeZ', 'Roll', 'Pitch', 'Yaw', 'C1', 'C2', 'C3', 'C4']]
                X_live = X_live.fillna(0) 

                pred = ai_model.predict(X_live)[0] # -1 = Anomaly, 1 = Normal
                risk = 1.0 if pred == -1 else 0.0
                current_stats['ai_risk'] = risk
                
                boot_ms = int((time.time() - start_time) * 1000)
                master.mav.named_value_float_send(boot_ms, b'AI_RISK', risk)
                
                if risk > 0.5:
                        logging.warning(f"⚠️ AI ANOMALY DETECTED! Risk: {risk}")
                        master.mav.statustext_send(mavutil.mavlink.MAV_SEVERITY_CRITICAL, b"AI COPILOT: ANOMALY DETECTED!")
                        
                        if risk > 0.9:
                            logging.critical("🚨 ENGAGING AUTONOMOUS RTL!")
                            master.set_mode_rtl()
                            master.mav.statustext_send(mavutil.mavlink.MAV_SEVERITY_EMERGENCY, b"AI COPILOT: ENGAGING RTL!")
                
            except Exception as e:
                logging.error(f"Inference Error: {e}")
            
            last_inference = now

        # 4. Update System Stats (0.5Hz)
        if now - last_stats_update > 2.0:
            try:
                cpu = psutil.cpu_percent()
                mem = psutil.virtual_memory().percent
                temp = 45.0
                
                # Update global state safely
                current_stats["cpu"] = cpu
                current_stats["mem"] = mem
                current_stats["temp"] = temp
                current_stats["flight_data"]["volt"] = flight_state['Volt']
                current_stats["flight_data"]["curr"] = flight_state['Curr']
                current_stats["flight_data"]["vibex"] = flight_state['VibeX']
                current_stats["flight_data"]["vibey"] = flight_state['VibeY']
                current_stats["flight_data"]["vibez"] = flight_state['VibeZ']
                current_stats["flight_data"]["roll"] = flight_state['Roll']
                current_stats["flight_data"]["pitch"] = flight_state['Pitch']
                current_stats["flight_data"]["yaw"] = flight_state['Yaw']
                
                boot_ms = int((time.time() - start_time) * 1000)
                master.mav.named_value_float_send(boot_ms, b'COMP_CPU', cpu)
                last_stats_update = now
            except Exception as e:
                logging.error(f"Stats update error: {e}")

        time.sleep(0.01)



def build_telemetry_payload():
    """Constructs the JSON payload for the Cloud API."""
    return {
        "drone_id": "drone_01",
        "timestamp_ms": int(time.time() * 1000),
        "status": {
            "connection": current_stats["connection_status"],
            "ai_active": ai_model is not None,
            "battery_pct": int((current_stats["flight_data"]["volt"] - 10.0) / (12.6 - 10.0) * 100) if current_stats["flight_data"]["volt"] > 0 else 0
        },
        "inference": {
            "risk_score": current_stats["ai_risk"],
            "anomaly_type": "vibration" if current_stats["ai_risk"] > 0.5 else "none",
            "confidence": 0.95 if current_stats["ai_risk"] > 0.5 else 0.99
        },
        "physics": {
            "roll": current_stats["flight_data"]["roll"],
            "pitch": current_stats["flight_data"]["pitch"],
            "vibe_x": current_stats["flight_data"]["vibex"]
        },
        "location": {
            "lat": -35.363, # Mock location for SITL
            "lon": 149.165,
            "alt": 10.0
        }
    }

def cloud_uplink_worker():
    """Background thread to push data to Cloud Backend."""
    logging.info(f"Starting Cloud Uplink to {CLOUD_ENDPOINT}...")
    while True:
        try:
            if current_stats["connection_status"] == "online":
                payload = build_telemetry_payload()
                try:
                     response = requests.post(CLOUD_ENDPOINT, json=payload, timeout=2)
                     if response.status_code == 200:
                         logging.debug("Cloud Uplink Success")
                     else:
                         logging.warning(f"Cloud Uplink Error: {response.status_code}")
                except Exception as req_err:
                     logging.warning(f"Cloud Connection Failed: {req_err}")
            else:
                logging.debug("Cloud uplink waiting for drone connection...")
        except Exception as e:
             logging.error(f"Cloud Uplink Interface Error: {e}")
        
        time.sleep(1.0) # 1Hz Update Rate


if __name__ == "__main__":
    # Start MAVLink Thread
    mav_thread = threading.Thread(target=mavlink_worker, daemon=True)
    mav_thread.start()
    
    # Start Cloud Uplink Thread
    cloud_thread = threading.Thread(target=cloud_uplink_worker, daemon=True)
    cloud_thread.start()
    
    print(f"AI Copilot Dashboard available at http://localhost:{FLASK_PORT}")
    app.run(host='0.0.0.0', port=FLASK_PORT, debug=False, use_reloader=False)

