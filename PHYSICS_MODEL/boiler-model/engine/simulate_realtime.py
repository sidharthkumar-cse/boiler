import numpy as np
import matplotlib.pyplot as plt
import sys
import os
import time
import requests
import threading

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.solver_logic import run_continuous

import json
try:
    import serial
except ImportError:
    serial = None

# Global state for sensor data incoming from ESP32
ESP_URL = "http://10.77.160.147/data" # Replaced with actual ESP32 IP address
SERIAL_PORT = "/dev/tty.usbserial-0001"
BAUD_RATE = 115200

LATEST_SENSOR_DATA = {"mw": 10.0, "Q": 1000.0, "Kv": 1.0, "P": 1.013}  # Default 1.013 bar (1 atm) if no data

def fetch_esp_data():
    """Background thread to poll ESP32 without blocking the simulation. Tries Serial first, falls back to HTTP."""
    global ESP_URL
    if serial is not None:
        try:
            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2.0) as ser:
                print(f"Connected to ESP32 via Serial on {SERIAL_PORT} at {BAUD_RATE} baud.")
                while True:
                    try:
                        line = ser.readline().decode('utf-8', errors='ignore').strip()
                        if line:
                            # IP Auto-Detection to fix HTTP fallback dynamically
                            if "http://" in line and "/data" in line:
                                try:
                                    extracted_ip = line.split("http://")[1].split("/")[0]
                                    ESP_URL = f"http://{extracted_ip}/data"
                                    print(f"[ESP32 Network] Detected Hardware IP: {extracted_ip}")
                                except: pass

                            if line.startswith('{') and line.endswith('}'):
                                data = json.loads(line)
                                # L/min to kg/s conversion
                                LATEST_SENSOR_DATA["mw"] = data.get("mw", 0) / 60.0
                                LATEST_SENSOR_DATA["Q"] = data.get("Q", LATEST_SENSOR_DATA["Q"])
                                LATEST_SENSOR_DATA["Kv"] = data.get("Kv", LATEST_SENSOR_DATA["Kv"])
                                if "P" in data:
                                    LATEST_SENSOR_DATA["P"] = data["P"]
                            elif line.startswith("Flow:"):
                                try:
                                    # Convert Flow (L/min) -> kg/s
                                    LATEST_SENSOR_DATA["mw"] = float(line.split(":")[1].strip()) / 60.0
                                except ValueError:
                                    pass
                            elif line.startswith("Valve:"):
                                LATEST_SENSOR_DATA["Kv"] = 1.0 if "OPEN" in line else 0.0
                            elif line.startswith("Pressure:"):
                                try:
                                    LATEST_SENSOR_DATA["P"] = float(line.split(":")[1].strip())
                                except ValueError:
                                    pass
                            elif line.startswith("Temp:"):
                                try:
                                    raw_val = float(line.split(":")[1].strip())
                                    # Calibration: Most hobbyist sensors (TMP36) send millivolts
                                    if raw_val > 300: # Heuristic for raw mV vs Celsius
                                        LATEST_SENSOR_DATA["T"] = (raw_val - 500.0) / 10.0
                                    else:
                                        LATEST_SENSOR_DATA["T"] = raw_val
                                except ValueError:
                                    pass
                            elif line.startswith("Heater:"):
                                LATEST_SENSOR_DATA["Q"] = 1000.0 if "ON" in line else 0.0
                            elif line == "------" or line.startswith("Pump:") or line.startswith("LOW:"):
                                pass 
                            else:
                                print(f"[ESP32 Serial] {line}")
                    except Exception:
                        pass
        except Exception as e:
            print(f"Could not connect to {SERIAL_PORT} ({e}). Falling back to HTTP...")

    print(f"Starting HTTP fallback polling for {ESP_URL}...")
    while True:
        try:
            res = requests.get(ESP_URL, timeout=1.0)
            if res.status_code == 200:
                data = res.json()
                # Convert Flow (L/min) -> kg/s for solver
                LATEST_SENSOR_DATA["mw"] = data.get("mw", 0) / 60.0
                LATEST_SENSOR_DATA["Q"] = data.get("Q", LATEST_SENSOR_DATA["Q"])
                LATEST_SENSOR_DATA["Kv"] = data.get("Kv", LATEST_SENSOR_DATA["Kv"])
                if "P" in data:
                    LATEST_SENSOR_DATA["P"] = data["P"]
        except Exception:
            pass 
        time.sleep(1.0)

def simulate_realtime(duration=300, dt=1.0):
    print("--- Starting Real-Time Continuous Boiler Twin ---")
    
    # Start polling the ESP32 in a background thread
    threading.Thread(target=fetch_esp_data, daemon=True).start()
    
    # Wait briefly for the serial connection to grab the first real readings
    time.sleep(1.5)
    
    # Grab the true live initial pressure from the hardware (convert bar to Pascal)
    # Ensure a minimum physics constraint of 1.013 bar (atmospheric) so steam tables don't crash at 0
    starting_pressure_bar = max(1.013, LATEST_SENSOR_DATA["P"])
    P_init_pa = starting_pressure_bar * 1e5
    
    print(f"[Init] Live Pressure Sync: Calibrating Physical Twin to start at {starting_pressure_bar:.2f} bar.")
    
    # Initialize infinite continuous generator based on REAL initial state
    # Scale: Vdw_init = 0.003 (3 Liters) to match physical tabletop boiler
    boiler_twin = run_continuous(P_init=P_init_pa, Vdw_init=0.003, phi_init=0.1, 
                                 m_w=LATEST_SENSOR_DATA["mw"], Q=LATEST_SENSOR_DATA["Q"], 
                                 valve_opening=LATEST_SENSOR_DATA["Kv"], 
                                 T_init=LATEST_SENSOR_DATA.get("T", 25.0), dt=dt)
    
    # 1. Read first initial state
    P, Vdw, phi, L, T = next(boiler_twin)
    
    # Storage arrays for final plotting
    t_hist, P_hist, L_hist, mw_hist, Q_hist, Kv_hist = [], [], [], [], [], []
    
    t = 0.0
    while t <= duration:
        # A. Store outputs for plotting
        t_hist.append(t)
        P_hist.append(P)
        L_hist.append(L)
        mw_hist.append(LATEST_SENSOR_DATA["mw"])
        Q_hist.append(LATEST_SENSOR_DATA["Q"])
        Kv_hist.append(LATEST_SENSOR_DATA["Kv"])
        
        # Verbose trace every 20s
        if int(t) % 20 == 0:
            print(f"[t={t:5.1f}s] P={P/1e5:5.2f}bar | L={L:4.2f}m | T={T:5.1f}C || m_w={LATEST_SENSOR_DATA['mw']:4.1f} | Valve={LATEST_SENSOR_DATA['Kv']*100:3.0f}%")
        
        # B. Update inputs dynamically based on real-time t
        current_mw = LATEST_SENSOR_DATA["mw"]
        current_Q = LATEST_SENSOR_DATA["Q"]
        current_Kv = LATEST_SENSOR_DATA["Kv"]
        current_T = LATEST_SENSOR_DATA.get("T")
        
        # C. Advance explicitly, injecting dynamic variables into the solver natively
        P, Vdw, phi, L, T = boiler_twin.send((current_mw, current_Q, current_Kv, current_T))
        
        t += dt
        
    print(f"\nContinuous loop finished after {duration}s. Generating dynamic input tracking plot...")
    
    # D. Store and visualize the outputs
    fig, axs = plt.subplots(3, 1, figsize=(10, 8), sharex=True)
    
    # Plot 1: Outputs (Pressure & Drum Level)
    ax1 = axs[0]
    ax1.plot(t_hist, np.array(P_hist)/1e5, 'b-', label='Pressure (bar)')
    ax1.set_ylabel('Pressure (bar)', color='b')
    ax1.tick_params(axis='y', labelcolor='b')
    ax1.grid(True)
    ax2 = ax1.twinx()
    ax2.plot(t_hist, L_hist, 'g--', label='Water Level (m)')
    ax2.set_ylabel('Level (m)', color='g')
    ax2.tick_params(axis='y', labelcolor='g')
    axs[0].set_title('Real-Time Boiler Output Response')
    
    # Plot 2: Heat Input
    axs[1].plot(t_hist, np.array(Q_hist)/1e6, 'r-', label='Heat Q(t)')
    axs[1].set_ylabel('Heat (MW)')
    axs[1].grid(True)
    
    # Plot 3: Feedwater & Valve Input
    ax3 = axs[2]
    ax3.plot(t_hist, mw_hist, 'c-', label='Feedwater mw(t)')
    ax3.set_ylabel('Feedwater (kg/s)', color='c')
    ax3.tick_params(axis='y', labelcolor='c')
    ax3.grid(True)
    ax4 = ax3.twinx()
    ax4.plot(t_hist, np.array(Kv_hist)*100, 'k--', label='Valve Kv(t)')
    ax4.set_ylabel('Valve Position (%)', color='k')
    ax4.tick_params(axis='y', labelcolor='k')
    ax3.set_xlabel('Time (s)')
    
    plt.tight_layout()
    plt.savefig('results/realtime_simulation.png')
    print("Dashboard saved to results/realtime_simulation.png [Complete].")

if __name__ == '__main__':
    simulate_realtime(duration=60)
