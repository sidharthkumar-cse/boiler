import sys
import os
import time
import math
from collections import deque

# Add parent directory to path to allow imports from serial_proxy and model
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import classes from serial_proxy
from serial_proxy import EfficiencyTracker, AnomalyDetector, ValidationLogger
from physics import thermo_relations as thermo
from config import constants as const

def run_integration_test():
    print("====================================================")
    print("      DIGITAL TWIN INTEGRATION & DIAGNOSTICS       ")
    print("====================================================")

    # 1. Test Efficiency Tracker
    print("\n--- Testing Efficiency Tracker ---")
    tracker = EfficiencyTracker()
    
    # Simulate 60 seconds of heating at 1000W in 1-second steps
    T_curr = 25.0
    Q = 1000.0
    mass = 4.5 # kg
    for _ in range(60):
        T_curr += 0.1 # Heating up
        tracker.update(T_celsius=T_curr, P_abs_bar=1.013, Q_watts=Q, water_mass_kg=mass, dt_seconds=1.0)
    
    metrics = tracker.get_metrics()
    print(f"Heater Energy: {metrics['kWh_input']*3.6e6:.0f} J")
    print(f"Stored Energy: {metrics['kWh_useful']*3.6e6:.0f} J")
    print(f"Overall Efficiency: {metrics['eta_overall']}%")
    
    if metrics['eta_overall'] > 0:
        print("[SUCCESS] Efficiency tracking functional.")
    else:
        print("[FAILED] Efficiency tracking returned 0.")

    # 2. Test Anomaly Detection (Drift Scenario)
    print("\n--- Testing Anomaly Detector (Sensor Drift) ---")
    detector = AnomalyDetector(window=30)
    
    # Feed 30 normal readings to populate the window
    for i in range(30):
        detector.update(actual_T=100.0, predicted_T=100.0, actual_P=1.5, predicted_P=1.5)
    
    print(f"Health Score (Normal): {detector.get_status()['health_score']}")
    
    # Introduce a MASSIVE drift (50 degrees)
    print("Introducing 50°C temperature drift...")
    for i in range(10):
        detector.update(actual_T=150.0, predicted_T=100.0, actual_P=1.5, predicted_P=1.5)
    
    status = detector.get_status()
    print(f"Health Score (Post-Drift): {status['health_score']}")
    print(f"Active Anomalies: {len(status['anomalies'])}")

    if status['health_score'] < 100 and len(status['anomalies']) > 0:
        print("[SUCCESS] Anomaly detector successfully flagged the sensor drift.")
    else:
        print("[FAILED] Anomaly detector failed to flag drift.")

    # 3. Test Validation Logger (Accuracy)
    print("\n--- Testing Validation Logger (Accuracy) ---")
    val_logger = ValidationLogger()
    now = time.time()
    # Mocking prediction history
    val_logger.last_serving_pred = [
        {'t_min': 1, 'P': 1.1, 'T': 102.0}
    ]
    # Prediction was made exactly 60s ago
    val_logger.last_pred_timestamp = now - 60 
    
    # Record actual reading NOW (should match t_min=1 exactly)
    val_logger.record_actual(T=103.0, P=1.1)
    
    val_metrics = val_logger.get_metrics()
    print(f"RMSE (Temperature): {val_metrics['rmse_T']}")
    print(f"N Samples: {val_metrics['n_samples']}")
    
    if val_metrics['n_samples'] > 0:
        print("[SUCCESS] Validation engine matched prediction to reality.")
    else:
        print("[FAILED] Validation engine failed to match samples.")

if __name__ == "__main__":
    run_integration_test()
