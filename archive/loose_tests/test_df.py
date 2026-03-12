import sys
from pymavlink import DFReader

try:
    log = DFReader.DFReader_binary(sys.argv[1])
except Exception as e:
    print(f"Failed to open: {e}")
    sys.exit(1)

count = 0
msg_types = set()
try:
    while True:
        m = log.recv_match()
        if m is None:
            break
        count += 1
        msg_types.add(m.get_type())
        if count % 100000 == 0:
            print(f"Read {count} messages...")
except Exception as e:
    print(f"Error parsing: {e}")

print(f"Total messages read: {count}")
print(f"Message types: {list(msg_types)[:10]}...")
