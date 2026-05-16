import serial
import json
import time

SERIAL_PORT = "/dev/tty.usbserial-0001"
BAUD_RATE = 115200

def get_live_snapshot():
    """Takes 2 seconds to grab the absolute latest state from the physical ESP32.
    Applies production calibration for tabletop boiler scale.
    """
    # Standard tabletop defaults
    snapshot = {
        "mw": 0.0,      # kg/s
        "Q": 0.0,       # Watts
        "Kv": 1.0,      # 0.0 to 1.0
        "P": 1.013,     # bar
        "T": 25.0       # degC
    }
    
    print(f"Sampling LIVE data from USB {SERIAL_PORT}...")
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2.0) as ser:
            start_time = time.time()
            # Drain old buffer data to get fresh samples
            ser.reset_input_buffer()
            
            while time.time() - start_time < 2.5:
                line = ser.readline().decode('utf-8', errors='ignore').strip()
                if not line: continue
                
                # Try parsing as JSON first
                if line.startswith('{') and line.endswith('}'):
                    try:
                        data = json.loads(line)
                        # L/min to kg/s conversion if present
                        if "mw" in data: 
                            snapshot["mw"] = data["mw"] / 60.0
                        if "Q" in data: snapshot["Q"] = float(data["Q"])
                        if "Kv" in data: snapshot["Kv"] = float(data["Kv"])
                        if "P" in data: snapshot["P"] = max(1.013, float(data["P"]))
                        if "T" in data: snapshot["T"] = float(data["T"])
                    except Exception: pass
                
                # Fallback to field-based parsing
                elif line.startswith("Flow:"):
                    try:
                        # Convert Flow (L/min) -> kg/s
                        snapshot["mw"] = float(line.split(":")[1].strip()) / 60.0
                    except: pass
                elif line.startswith("Valve:"):
                    snapshot["Kv"] = 1.0 if "OPEN" in line else 0.0
                elif line.startswith("Pressure:"):
                    try:
                        snapshot["P"] = max(1.013, float(line.split(":")[1].strip()))
                    except: pass
                elif line.startswith("Temp:"):
                    try:
                        raw_val = float(line.split(":")[1].strip())
                        # Calibration: raw mV -> Celsius (for TMP36)
                        if raw_val > 300: 
                            snapshot["T"] = (raw_val - 500.0) / 10.0
                        else:
                            snapshot["T"] = raw_val
                    except: pass
                elif line.startswith("Heater:"):
                    snapshot["Q"] = 1000.0 if "ON" in line else 0.0
                    
        print(f"✅ Successfully grabbed LIVE state: {snapshot}")
    except Exception as e:
        print(f"⚠️ USB Blocked or Disconnected! Using fallback defaults. Error: {e}")
        
    return snapshot
