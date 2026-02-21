#!/bin/bash
set -e

# 1. Start the Backend Cloud Service
echo "Starting Cloud Backend..."
uvicorn backend.main:app --port 8000 --reload > backend.log 2>&1 &
BACKEND_PID=$!
sleep 5

# 2. Start SITL (Simulated Drone) with AI Parameters
echo "Starting SITL..."
echo "SCR_ENABLE 1" > ai_failsafe.parm
echo "RELAY_DEFAULT 0" >> ai_failsafe.parm
echo "RELAY_PIN 13" >> ai_failsafe.parm
python3 Tools/autotest/sim_vehicle.py -v ArduCopter -L CMAC --no-rebuild --no-mavproxy --speedup 1 --add-param-file=ai_failsafe.parm > sitl.log 2>&1 &
SITL_PID=$!
sleep 30

# 3. Start Companion Monitor (Edge AI Agent)
echo "Starting Edge AI Agent..."
python3 companion_monitor.py > edge.log 2>&1 &
EDGE_PID=$!
sleep 15

# 4. Verify Data Flow
if grep -q "Cloud Uplink Success" edge.log; then
    echo "✅ SUCCESS: Edge Agent reported successful Cloud Uplink!"
else
    echo "⚠️ WARNING: Edge Agent did not report success in logs."
fi

RESPONSE=$(curl -s http://localhost:8000/api/drones/drone_01)
echo "Backend Response: $RESPONSE"

if [[ $RESPONSE == *"status"* && $RESPONSE != *"online"* ]]; then
     # It might still show mock data if updates are slow/failed
     echo "❓ CHECK: Status is '$RESPONSE'. If it says 'online' and risk score changes, it's working."
fi

# Cleanup
kill $BACKEND_PID $SITL_PID $EDGE_PID
pkill -f arducopter
pkill -f sim_vehicle.py
