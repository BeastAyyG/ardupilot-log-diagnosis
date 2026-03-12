import os, sys, time

print("Importing pymavlink...", flush=True)
from pymavlink import mavutil
print("Done importing", flush=True)

filepath = 'data/kaggle_backups/ardupilot-master-log-pool-v2/log_0034_hardware_failure.bin'
print(f"Testing {filepath} ({os.path.getsize(filepath)} bytes)", flush=True)

start_time = time.time()
print("Opening connection...", flush=True)
log = mavutil.mavlink_connection(filepath)
print("Connected", flush=True)

count = 0
while True:
    try:
        msg = log.recv_msg()
    except Exception as e:
        print(f"Exception: {e}", flush=True)
        break
    if msg is None:
        break
    count += 1
    if count % 1000 == 0:
        print(f"Read {count} messages...", flush=True)

duration = time.time() - start_time
print(f"Done. Total: {count} messages in {duration:.2f}s", flush=True)
