#!/usr/bin/env python3
"""
ArduPilot Log Parser

A lightweight utility to parse ArduPilot DataFlash/Telemetry logs (.BIN) 
and summarize the available message types.
"""

import sys
import argparse
from typing import Dict
from collections import defaultdict
from pymavlink import mavutil


class LogParser:
    """Parses ArduPilot .BIN logs and extracts message frequencies."""

    def __init__(self, log_path: str):
        self.log_path = log_path
    
    def get_message_frequencies(self) -> Dict[str, int]:
        """
        Reads the log file and counts occurrences of each MAVLink message type.
        
        Returns:
            Dict[str, int]: A dictionary mapping message types to their counts.
        """
        try:
            mlog = mavutil.mavlink_connection(self.log_path)
        except Exception as e:
            raise FileNotFoundError(f"Failed to open log file {self.log_path}: {e}")

        counts: Dict[str, int] = defaultdict(int)
        
        while True:
            msg = mlog.recv_match(blocking=False)
            if msg is None:
                break
            
            mtype = msg.get_type()
            if mtype != "BAD_DATA":
                counts[mtype] += 1
                
        return dict(counts)

    def print_summary(self, counts: Dict[str, int]) -> None:
        """Prints a formatted summary of message counts."""
        print("=" * 45)
        print(f"{'Message Type':<25} {'Count':>10}")
        print("=" * 45)
        
        for mtype, count in sorted(counts.items(), key=lambda item: item[1], reverse=True):
            print(f"  {mtype:<25} {count:>10}")


def main() -> None:
    """Main execution entry point."""
    parser = argparse.ArgumentParser(description="Parse and summarize an ArduPilot .BIN log file.")
    parser.add_argument("log_path", type=str, help="Path to the .BIN log file")
    args = parser.parse_args()

    parser_obj = LogParser(args.log_path)
    try:
        counts = parser_obj.get_message_frequencies()
        parser_obj.print_summary(counts)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
