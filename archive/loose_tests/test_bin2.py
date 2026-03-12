from pymavlink import DFReader
log = DFReader.DFReader_binary("sample.bin")
messages_by_id = {}
while True:
    try:
        m = log.recv_match()
        if m is None:
            break
        fmt = m.get_type()
        if fmt not in messages_by_id:
            messages_by_id[fmt] = []
        messages_by_id[fmt].append(m.to_dict())
    except Exception as e:
        print("Error:", e)
        break

print("Message fields types:")
for fmt, msgs in messages_by_id.items():
    print(f"{fmt}: {len(msgs)} messages")
    if fmt == "ERR":
        for idx in range(min(5, len(msgs))):
            print(f"  ERR[{idx}]: {msgs[idx]}")

