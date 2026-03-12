#!/usr/bin/env python3
import psutil
import time
import threading
from pymavlink import mavutil


class CompanionMonitor:
    def __init__(self, conn_str):
        self.conn = mavutil.mavlink_connection(conn_str)
        self.conn.wait_heartbeat()
        print("Connected")
        self.running = True

    def send_heartbeat(self):
        while self.running:
            self.conn.mav.heartbeat_send(
                mavutil.mavlink.MAV_TYPE_ONBOARD_CONTROLLER,
                mavutil.mavlink.MAV_AUTOPILOT_INVALID,
                0,
                0,
                0,
            )
            time.sleep(1)

    def run(self):
        hb = threading.Thread(target=self.send_heartbeat)
        hb.daemon = True
        hb.start()
        while self.running:
            cpu = psutil.cpu_percent(interval=1)
            ram = psutil.virtual_memory().percent
            now = int(time.time() * 1000) & 0xFFFFFFFF
            self.conn.mav.named_value_float_send(now, b"CC_CPU\x00\x00\x00\x00", cpu)
            self.conn.mav.named_value_float_send(now, b"CC_RAM\x00\x00\x00\x00", ram)
            print(f"CPU={cpu:.0f}% RAM={ram:.0f}%")
            time.sleep(2)


if __name__ == "__main__":
    CompanionMonitor("udp:127.0.0.1:14550").run()
