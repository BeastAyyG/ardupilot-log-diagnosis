import logging
from pymavlink import DFReader
from src.constants import ERR_SUBSYSTEM_MAP, ERR_AUTO_LABEL_MAP, MODE_NAMES, EV_NAMES

class LogParser:
    def __init__(self, filepath: str):
        self.filepath = filepath
        self.logger = logging.getLogger(__name__)
        
    def parse(self) -> dict:
        """
        Parse entire .BIN file.
        Returns a dict containing metadata, messages, parameters, errors, events,
        mode_changes, and status_messages.
        """
        parsed_data = {
            "metadata": {
                "filepath": self.filepath,
                "duration_sec": 0.0,
                "vehicle_type": "Unknown",
                "firmware_version": "Unknown",
                "total_messages": 0,
                "message_types": {}
            },
            "messages": {},
            "parameters": {},
            "errors": [],
            "events": [],
            "mode_changes": [],
            "status_messages": []
        }
        
        try:
            log = DFReader.DFReader_binary(self.filepath)
        except Exception as e:
            self.logger.error(f"Failed to open log file {self.filepath}: {e}")
            return parsed_data
            
        first_time = None
        last_time = None
        
        try:
            while True:
                msg = log.recv_msg()
                if msg is None:
                    break
                    
                msg_type = msg.get_type()
                
                # Metadata
                parsed_data["metadata"]["total_messages"] += 1
                parsed_data["metadata"]["message_types"][msg_type] = \
                    parsed_data["metadata"]["message_types"].get(msg_type, 0) + 1
                    
                time_us = getattr(msg, 'TimeUS', None)
                if time_us is not None:
                    if first_time is None:
                        first_time = time_us
                    last_time = time_us
                    
                if msg_type not in parsed_data["messages"]:
                    parsed_data["messages"][msg_type] = []
                    
                # Convert message fields to Python native types (dictionary)
                msg_dict = msg.to_dict()
                parsed_data["messages"][msg_type].append(msg_dict)
                
                if msg_type == "MSG":
                    message_text = msg_dict.get('Message', '')
                    parsed_data["status_messages"].append({
                        "time_us": time_us,
                        "message": message_text
                    })
                    # Attempt to extract vehicle type and firmware
                    if "ArduCopter" in message_text:
                        parsed_data["metadata"]["vehicle_type"] = "Copter"
                        parts = message_text.split()
                        if len(parts) > 1 and parts[0] == "ArduCopter":
                            parsed_data["metadata"]["firmware_version"] = parts[1]
                elif msg_type == "PARM":
                    name = msg_dict.get('Name')
                    value = msg_dict.get('Value')
                    if name is not None and value is not None:
                        parsed_data["parameters"][name] = float(value) if isinstance(value, (int, float)) else value
                elif msg_type == "ERR":
                    subsys = msg_dict.get('Subsys', 0)
                    ecode = msg_dict.get('ECode', 0)
                    subsys_name = ERR_SUBSYSTEM_MAP.get(subsys, f"UNKNOWN_{subsys}")
                    auto_label = ERR_AUTO_LABEL_MAP.get(subsys)
                    if subsys == 11 and ecode != 2:
                        auto_label = None # special condition for GPS
                    parsed_data["errors"].append({
                        "time_us": time_us,
                        "subsystem": subsys,
                        "subsystem_name": subsys_name,
                        "code": ecode,
                        "auto_label": auto_label
                    })
                elif msg_type == "EV":
                    ev_id = msg_dict.get('Id', 0)
                    ev_name = EV_NAMES.get(ev_id, f"EVENT_{ev_id}")
                    parsed_data["events"].append({
                        "time_us": time_us,
                        "id": ev_id,
                        "name": ev_name
                    })
                elif msg_type == "MODE":
                    mode_num = msg_dict.get('ModeNum', msg_dict.get('Mode', 0))
                    reason = msg_dict.get('Reason', 0)
                    mode_name = MODE_NAMES.get(mode_num, f"MODE_{mode_num}")
                    parsed_data["mode_changes"].append({
                        "time_us": time_us,
                        "mode": mode_num,
                        "mode_name": mode_name,
                        "reason": reason
                    })
                    
        except Exception as e:
            self.logger.warning(f"Error or log truncated while reading messages from {self.filepath}: {e}")
            
        if first_time is not None and last_time is not None and last_time > first_time:
            parsed_data["metadata"]["duration_sec"] = (last_time - first_time) / 1e6
            
        return parsed_data
