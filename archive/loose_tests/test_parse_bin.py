import sys
from src.parsers.binary import BinaryParser

parser = BinaryParser()
log_data = parser.parse("data/kaggle_backups/ardupilot-master-log-pool-v2/log_0046_thrust_loss.bin")
print(f"Messages parsed: {len(log_data.messages)}")
print(f"Message types: {list(log_data.messages.keys())}")
if 'MSG' in log_data.messages:
    print(f"MSG count: {len(log_data.messages['MSG'])}")
if 'ERR' in log_data.messages:
    print(f"ERR count: {len(log_data.messages['ERR'])}")

