import serial
import time
import json
import threading
import queue
import csv
import math
from collections import deque
from http.server import BaseHTTPRequestHandler, HTTPServer
import sys
import os
from pathlib import Path
from datetime import datetime

# Add the boiler-model directory to path so we can import the solver
repo_root = Path(__file__).parent.parent
sys.path.append(str(repo_root / "boiler-model"))
from engine.solver_logic import predict_forward, predict_timeline, compute_initial_state
from engine.kalman_filter import BoilerEKF
import physics.thermo_relations as thermo
from config import constants as const

import joblib
import numpy as np
import warnings

# Suppress the harmless scikit-learn warning about missing feature names during inference
warnings.filterwarnings("ignore", message="X does not have valid feature names")

# Load the trained residual models
try:
    hybrid_ml_T = joblib.load(str(Path(__file__).parent / 'models/residual_model_T.pkl'))
    hybrid_ml_P = joblib.load(str(Path(__file__).parent / 'models/residual_model_P.pkl'))
    print("🧠 Hybrid AI Models Loaded successfully!")
except Exception as e:
    hybrid_ml_T = None
    hybrid_ml_P = None
    print(f"Physics-only mode. (No AI models found: {e})")
# --- Calibration Offsets (from session log analysis) ---
TEMP_CALIBRATION_OFFSET = 0.541
THERMAL_RESISTANCE_FACTOR = 0.022
PRESSURE_CALIBRATION_OFFSET = -0.12  # Default fallback; will be auto-zeroed if cold start detected
_pressure_autozero_samples = []      # Collect readings for auto-zero
_pressure_autozero_done = False      # Flag: once set, offset is locked
_temp_received = False               # Gate: must receive at least one real T reading first
AUTOZERO_N_SAMPLES = 10             # Number of cold readings to average


# ── Sensor Smoothing (Median + Outlier Rejection) ──────────────────────
class SensorSmoother:
    """
    Rolling median filter with outlier rejection for incoming serial data.
    This is the SECOND defense layer (after the ESP32's onboard EMA filter).

    Strategy:
      1. Maintain a sliding window of the last `window` readings.
      2. Reject readings that deviate > `sigma_thresh` standard deviations
         from the current median (spike rejection).
      3. Return the median of the window as the smoothed value.
    """
    def __init__(self, window=5, sigma_thresh=3.0, min_sigma=0.5):
        self.window = window
        self.sigma_thresh = sigma_thresh
        self.min_sigma = min_sigma
        self.buffer = deque(maxlen=window)

    def update(self, raw_value, sensor_name="Unknown"):
        """Feed a new raw reading.  Returns the smoothed (median) value."""
        if len(self.buffer) >= 3:
            # Outlier rejection: check if new value is wildly off
            sorted_buf = sorted(self.buffer)
            median = sorted_buf[len(sorted_buf) // 2]
            # Use MAD (Median Absolute Deviation) for robust σ estimate
            mad = sorted(abs(v - median) for v in sorted_buf)[len(sorted_buf) // 2]
            sigma_est = max(mad * 1.4826, self.min_sigma) # Added floor to prevent locking

            # Reject only if it's both a statistical outlier AND exceeds a minimum absolute delta
            # This prevents "locking" when the sensor is very stable.
            abs_delta = abs(raw_value - median)
            if abs_delta > self.sigma_thresh * sigma_est and abs_delta > 1.5:
                # Spike detected — ignore this reading, return current median
                print(f"⚠️ [Smoother] {sensor_name} spike rejected: {raw_value:.2f} (median: {median:.2f}, delta: {abs_delta:.2f}, thresh: {self.sigma_thresh * sigma_est:.2f})")
                return median
        self.buffer.append(raw_value)
        sorted_buf = sorted(self.buffer)
        return sorted_buf[len(sorted_buf) // 2]

# Create per-sensor smoothers with tailored noise floors
# min_sigma prevents the filter from "locking" during periods of high stability
smooth_temp     = SensorSmoother(window=5, sigma_thresh=3.0, min_sigma=0.5)  # 0.5°C floor
smooth_pressure = SensorSmoother(window=5, sigma_thresh=4.0, min_sigma=0.02) # 0.02 bar floor
smooth_flow     = SensorSmoother(window=3, sigma_thresh=2.5, min_sigma=0.1)  # 0.1 L/min floor


# ── Feature 1: Model Validation Engine ──────────────────────────────────
class ValidationLogger:
    """
    Records predictions and compares them against actual sensor values
    to compute live RMSE and MAPE (Mean Absolute Percentage Error).
    This provides hard evidence that the physics model works.
    """
    def __init__(self, max_history=500):
        self.predictions = deque(maxlen=max_history)  # {timestamp, predicted_T, predicted_P, horizon_s}
        self.actuals = deque(maxlen=max_history)       # {timestamp, actual_T, actual_P}
        self.matched_pairs = deque(maxlen=max_history)  # {pred_T, act_T, pred_P, act_P, t_min}
        self.lock = threading.Lock()

    def record_prediction(self, timeline):
        """Store a prediction timeline for later comparison."""
        if not timeline:
            return
        now = time.time()
        with self.lock:
            for pt in timeline:
                self.predictions.append({
                    "ts": now,
                    "target_ts": now + pt["t_min"] * 60.0,
                    "t_min": pt["t_min"],
                    "pred_T": pt["T"],
                    "pred_P": pt["P"]
                })

    def record_actual(self, T, P_abs):
        """Store an actual sensor reading with timestamp."""
        now = time.time()
        with self.lock:
            # Store P as Gauge pressure to match predictions
            P_gauge = max(0, P_abs - 1.013)
            self.actuals.append({"ts": now, "T": T, "P": P_gauge})
            # Match predictions that have matured (their target_ts has passed)
            to_remove = []
            for i, pred in enumerate(self.predictions):
                if pred["target_ts"] <= now:
                    # Find closest actual reading to the target timestamp
                    best = None
                    best_dist = float('inf')
                    for act in self.actuals:
                        dist = abs(act["ts"] - pred["target_ts"])
                        if dist < best_dist:
                            best_dist = dist
                            best = act
                    if best and best_dist < 5.0:  # Within 5 seconds
                        self.matched_pairs.append({
                            "t_min": pred["t_min"],
                            "pred_T": pred["pred_T"], "act_T": best["T"],
                            "pred_P": pred["pred_P"], "act_P": best["P"]
                        })
                    to_remove.append(i)
            # Remove matched predictions (iterate in reverse)
            for i in reversed(to_remove):
                if i < len(self.predictions):
                    del self.predictions[i]

    def get_metrics(self):
        """Compute RMSE and MAPE from matched prediction-actual pairs."""
        with self.lock:
            n = len(self.matched_pairs)
            if n < 3:
                return {
                    "n_samples": n, "rmse_T": None, "rmse_P": None,
                    "mape_T": None, "mape_P": None, "pairs": []
                }
            sum_sq_T = sum((p["pred_T"] - p["act_T"])**2 for p in self.matched_pairs)
            sum_sq_P = sum((p["pred_P"] - p["act_P"])**2 for p in self.matched_pairs)
            rmse_T = math.sqrt(sum_sq_T / n)
            rmse_P = math.sqrt(sum_sq_P / n)

            mape_T = 100.0 * sum(abs(p["pred_T"] - p["act_T"]) / max(abs(p["act_T"]), 1.0) for p in self.matched_pairs) / n
            mape_P = 100.0 * sum(abs(p["pred_P"] - p["act_P"]) / max(abs(p["act_P"]), 0.01) for p in self.matched_pairs) / n

            # Last 20 pairs for chart overlay
            recent = list(self.matched_pairs)[-20:]
            return {
                "n_samples": n,
                "rmse_T": round(rmse_T, 2),
                "rmse_P": round(rmse_P, 4),
                "mape_T": round(mape_T, 2),
                "mape_P": round(mape_P, 2),
                "pairs": [{"t_min": p["t_min"], "pred_T": p["pred_T"], "act_T": p["act_T"],
                           "pred_P": p["pred_P"], "act_P": p["act_P"]} for p in recent]
            }


# ── Feature 2: Boiler Efficiency Calculator ─────────────────────────────
class EfficiencyTracker:
    """
    Real-time thermal efficiency: η = Q_useful / Q_input.
    Tracks cumulative energy metrics for the session.
    """
    def __init__(self):
        self.session_start = time.time()
        self.last_update = time.time()
        self.total_Q_input_J = 0.0      # Total heater energy input (J)
        self.total_Q_useful_J = 0.0     # Energy stored in water (J)
        self.total_Q_loss_J = 0.0       # Environmental heat losses (J)
        self.prev_T = None
        self.instantaneous_eta = 0.0
        self.lock = threading.Lock()

    def update(self, T_celsius, P_abs_bar, Q_watts, water_mass_kg, dt_seconds):
        """Call every sensor update cycle."""
        with self.lock:
            if dt_seconds <= 0 or dt_seconds > 10:
                return

            # Energy input from heater
            Q_in = Q_watts * dt_seconds
            self.total_Q_input_J += Q_in

            # Useful energy = sensible heating of water + metal
            CP_WATER = 4186.0
            if self.prev_T is not None:
                dT = T_celsius - self.prev_T
                Q_sensible = water_mass_kg * CP_WATER * dT
                self.total_Q_useful_J += max(0, Q_sensible)
            self.prev_T = T_celsius

            # Environmental loss estimate
            from config import constants as const
            Q_loss = const.U_LOSS * const.A_VESSEL * max(T_celsius - const.T_AMB, 0.0) * dt_seconds
            self.total_Q_loss_J += Q_loss

            # Instantaneous efficiency
            if Q_in > 0:
                self.instantaneous_eta = max(0, min(100, (Q_in - Q_loss) / Q_in * 100))

    def get_metrics(self):
        with self.lock:
            session_mins = (time.time() - self.session_start) / 60.0
            overall_eta = 0.0
            if self.total_Q_input_J > 0:
                overall_eta = (self.total_Q_useful_J / self.total_Q_input_J) * 100.0
            return {
                "session_minutes": round(session_mins, 1),
                "eta_instant": round(self.instantaneous_eta, 1),
                "eta_overall": round(min(100, max(0, overall_eta)), 1),
                "kWh_input": round(self.total_Q_input_J / 3.6e6, 4),
                "kWh_useful": round(self.total_Q_useful_J / 3.6e6, 4),
                "kWh_loss": round(self.total_Q_loss_J / 3.6e6, 4)
            }


# ── Feature 3: Anomaly Detection ───────────────────────────────────────
class AnomalyDetector:
    """
    Detects when actual sensor readings deviate from model predictions.
    Catches: sensor faults, scale buildup, leaks, heater degradation.
    """
    def __init__(self, window=30, sigma_thresh=3.0):
        self.residuals_T = deque(maxlen=window)
        self.residuals_P = deque(maxlen=window)
        self.active_anomalies = []  # Current anomaly alerts
        self.health_score = 100     # 0-100 overall health
        self.lock = threading.Lock()

    def update(self, actual_T, predicted_T, actual_P, predicted_P):
        """Feed a new actual vs predicted pair."""
        with self.lock:
            res_T = actual_T - predicted_T
            res_P = actual_P - predicted_P
            self.residuals_T.append(res_T)
            self.residuals_P.append(res_P)

            self.active_anomalies = []

            if len(self.residuals_T) >= 10:
                mean_T = sum(self.residuals_T) / len(self.residuals_T)
                std_T = max(0.5, math.sqrt(sum((r - mean_T)**2 for r in self.residuals_T) / len(self.residuals_T)))
                if abs(res_T) > 3.0 * std_T:
                    self.active_anomalies.append({
                        "type": "TEMP_DRIFT",
                        "severity": "WARNING" if abs(res_T) < 5.0 * std_T else "CRITICAL",
                        "message": f"Temperature deviation: {res_T:+.1f}°C from model",
                        "value": round(res_T, 2)
                    })

                mean_P = sum(self.residuals_P) / len(self.residuals_P)
                std_P = max(0.01, math.sqrt(sum((r - mean_P)**2 for r in self.residuals_P) / len(self.residuals_P)))
                if abs(res_P) > 3.0 * std_P:
                    self.active_anomalies.append({
                        "type": "PRESSURE_DRIFT",
                        "severity": "WARNING" if abs(res_P) < 5.0 * std_P else "CRITICAL",
                        "message": f"Pressure deviation: {res_P:+.3f} bar from model",
                        "value": round(res_P, 4)
                    })

                # Health score: 100 = perfect match, decays with residual magnitude
                norm_T = min(1.0, abs(mean_T) / (3.0 * std_T)) if std_T > 0 else 0
                norm_P = min(1.0, abs(mean_P) / (3.0 * std_P)) if std_P > 0 else 0
                self.health_score = max(0, int(100 * (1.0 - 0.5 * norm_T - 0.5 * norm_P)))

    def get_status(self):
        with self.lock:
            return {
                "health_score": self.health_score,
                "anomalies": list(self.active_anomalies),
                "n_residuals": len(self.residuals_T)
            }


# ── Feature 4: CSV Session Logger ──────────────────────────────────────
class SessionLogger:
    """Logs all telemetry + predictions to CSV for export and validation."""
    def __init__(self):
        self.log_dir = Path(__file__).parent / "session_logs"
        self.log_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.filepath = self.log_dir / f"session_{ts}.csv"
        self.row_count = 0
        self.lock = threading.Lock()
        self._init_csv()

    def _init_csv(self):
        with open(self.filepath, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "timestamp", "T_actual", "P_actual_gauge", "T_predicted", "P_predicted",
                "Q_watts", "flow_lpm", "water_L", "eta_instant", "health_score", "anomaly_flag",
                "prediction_horizon_s", "prediction_target_timestamp", "L_predicted"
            ])

    def log(self, T_act, P_gauge, T_pred, P_pred, Q, flow, water_L, eta, health, anomaly,
            prediction_horizon_s=None, prediction_target_timestamp=None, L_pred=None):
        with self.lock:
            try:
                with open(self.filepath, 'a', newline='') as f:
                    writer = csv.writer(f)
                    writer.writerow([
                        datetime.now().isoformat(),
                        round(T_act, 2), round(P_gauge, 4),
                        round(T_pred, 2) if T_pred is not None else "",
                        round(P_pred, 4) if P_pred is not None else "",
                        round(Q, 1), round(flow, 3), round(water_L, 3),
                        round(eta, 1), health,
                        1 if anomaly else 0,
                        round(prediction_horizon_s, 1) if prediction_horizon_s is not None else "",
                        prediction_target_timestamp or "",
                        round(L_pred, 3) if L_pred is not None else ""
                    ])
                    self.row_count += 1
            except Exception as e:
                print(f"⚠️ CSV log error: {e}")

    def get_info(self):
        return {
            "filepath": str(self.filepath),
            "filename": self.filepath.name,
            "rows": self.row_count
        }


# ── Create global instances ──
validation_logger = ValidationLogger()
efficiency_tracker = EfficiencyTracker()
anomaly_detector = AnomalyDetector()
session_logger = SessionLogger()

# ── Feature 5: Extended Kalman Filter for Sensor-Model Fusion ──
boiler_ekf = BoilerEKF()
boiler_ekf.set_physics_model(predict_forward, compute_initial_state)
print("🧮 Extended Kalman Filter (EKF) initialized — sensor-model fusion active")

SERIAL_PORT = "/dev/tty.usbserial-0001"
BAUD_RATE = 115200

# Shared state memory
latest_data = {
    "mw": 0.0,
    "Q": 0.0,
    "T": 0.0,
    "P": 1.013,
    "pump": 0,
    "ip": "0.0.0.0",
    "mode": "AUTO",
    "valve": "CLOSED",
    "float_low": 0,
    "float_high": 0,
    "ready": 0
}
is_connected = False
command_queue = queue.Queue()

# ── Water Volume & Level Tracking from Arduino ──
INITIAL_WATER_VOLUME_L = const.V_WATER_INIT * 1000.0

# Cumulative water mass in the boiler (kg)
water_mass_kg = INITIAL_WATER_VOLUME_L * thermo.get_rho_w_subcooled(1.013e5, const.T_FEED) / 1000.0
last_flow_time = time.time()

# Explicit Volume Tracking
# V_new_L = V_old_L + (Flow_in_Lpm - Flow_out_Lpm) * dt_min
current_water_volume_L = INITIAL_WATER_VOLUME_L

# Heater command intent tracking
# When user clicks "Start Heater", we set this True immediately
heater_cmd_pending = False
SHORT_FORECAST_SECONDS = 60.0

# ── Predictive Autopilot State ──
autopilot_state = {
    "mode": "manual",        # manual | auto
    "target_p": 1.5,         # Target Gauge Pressure (bar)
    "status": "idle",        # idle | heating | coasting | stabilizing
    "forecast_p_60s": 0.0
}


def sync_water_from_float_state():
    """
    Use the float switch as an absolute level reference.

    Flow integration drifts over time. When float_high is active, the boiler is
    at the measured high-water mark, so reset volume and mass to that known
    geometry instead of carrying accumulated flow error forward.
    """
    global current_water_volume_L, water_mass_kg

    if latest_data.get("float_high", 0):
        cur_P_pa = latest_data.get("P", 1.013) * 1e5
        cur_T = latest_data.get("T", const.T_FEED)
        rho = thermo.get_rho_w_subcooled(cur_P_pa, cur_T)
        current_water_volume_L = INITIAL_WATER_VOLUME_L
        water_mass_kg = INITIAL_WATER_VOLUME_L * rho / 1000.0
        latest_data["Water_Volume_Liters"] = round(current_water_volume_L, 3)


def get_model_start_state():
    """Build a consistent model initial state from EKF when ready, else raw sensors."""
    fused = boiler_ekf.get_fused_state() if boiler_ekf.initialized else None
    if fused and boiler_ekf.n_updates > 5:
        T_init = fused["T_fused"]
        P_init_pa = fused["P_fused"] * 1e5
        V_init_L = fused["V_fused"]
        rho_w = thermo.get_rho_w_subcooled(P_init_pa, T_init)
        model_water_mass_kg = V_init_L * (rho_w / 1000.0)
    else:
        T_init = latest_data["T"]
        P_init_pa = latest_data["P"] * 1e5
        V_init_L = current_water_volume_L
        model_water_mass_kg = water_mass_kg

    return T_init, P_init_pa, V_init_L, model_water_mass_kg


def compute_short_forecast(horizon_s=SHORT_FORECAST_SECONDS):
    """
    Forecast the near future on every log tick.

    These values are written into the session CSV so exported logs contain
    actual prediction-vs-future-actual evidence, not blank prediction columns.
    """
    try:
        T_init, P_init_pa, _, model_water_mass_kg = get_model_start_state()
        Vdw_init, phi_init, _ = compute_initial_state(
            T_celsius=T_init,
            P_pa=P_init_pa,
            water_mass_kg=model_water_mass_kg
        )

        effective_Q = latest_data["Q"]
        if effective_Q == 0 and heater_cmd_pending:
            effective_Q = 1000.0

        P_pred_pa, Vdw_pred, _, _, T_pred, _ = predict_forward(
            P_init=P_init_pa,
            Vdw_init=Vdw_init,
            phi_init=phi_init,
            m_w=latest_data.get("mw", 0.0) / 60.0,
            Q=effective_Q,
            valve_opening=1.0 if latest_data.get("valve") == "OPEN" else 0.0,
            T_init=T_init,
            duration=float(horizon_s)
        )

        # Convert to dashboard units
        physics_T = float(T_pred)
        physics_P = max(0.0, float(P_pred_pa) / 1e5 - 1.013)
        
        # 2. Hybrid AI Step: Predict the Residual (Error)
        error_T = 0.0
        error_P = 0.0
        
        if hybrid_ml_T is not None and hybrid_ml_P is not None:
            # Create the feature array [T, P, Q, flow, water] matching the training data
            current_features = np.array([[
                latest_data["T"], 
                max(0.0, latest_data["P"] - 1.013), 
                effective_Q, 
                latest_data.get("mw", 0.0), 
                current_water_volume_L
            ]])
            
            # Predict the mistake the physics model is about to make!
            error_T = hybrid_ml_T.predict(current_features)[0]
            error_P = hybrid_ml_P.predict(current_features)[0]
            
        # 3. Final Hybrid Prediction = Physics + ML Correction
        hybrid_T = physics_T + error_T
        hybrid_P = physics_P + error_P

        target_ts = datetime.fromtimestamp(time.time() + horizon_s).isoformat()
        return {
            "T": hybrid_T,
            "P": hybrid_P,
            "physics_T": physics_T,
            "physics_P": physics_P,
            "L": max(0.0, float(Vdw_pred) * 1000.0),
            "horizon_s": float(horizon_s),
            "target_ts": target_ts,
        }
    except Exception as e:
        print(f"⚠️ [ShortForecast] Failed: {e}")
        return {
            "T": None,
            "P": None,
            "physics_T": None,
            "physics_P": None,
            "L": None,
            "horizon_s": float(horizon_s),
            "target_ts": datetime.fromtimestamp(time.time() + horizon_s).isoformat(),
        }

def read_serial():
    global is_connected, _temp_received, _pressure_autozero_done, _pressure_autozero_samples, PRESSURE_CALIBRATION_OFFSET
    print(f"🔌 Opening up physical connection to {SERIAL_PORT}...")
    while True:
        try:
            with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2) as ser:
                print("✅ Serial connected! Listening for incoming telemetry...")
                is_connected = True
                while True:
                    # Check for outgoing commands
                    try:
                        cmd = command_queue.get_nowait()
                        print(f"📤 Sending command to serial: {cmd.strip()}")
                        ser.write(cmd.encode('utf-8'))
                        # Track heater intent immediately
                        global heater_cmd_pending
                        if 'HEATER_ON' in cmd:
                            heater_cmd_pending = True
                            print("🔥 Heater intent flagged — predictions will activate")
                        elif 'HEATER_OFF' in cmd:
                            heater_cmd_pending = False
                    except queue.Empty:
                        pass

                    # Read incoming telemetry (non-blocking-ish with small timeout)
                    ser.timeout = 0.1
                    line = ser.readline().decode('utf-8', errors='ignore').strip()
                    if not line:
                        continue

                    # IP Auto-Detection from Arduino log
                    if "http://" in line and "/data" in line:
                        try:
                            # Extract IP from http://172.20.10.3/data
                            extracted_ip = line.split("http://")[1].split("/")[0]
                            latest_data["ip"] = extracted_ip
                            print(f"📡 Detected ESP32 Hardware IP: {extracted_ip}")
                        except:
                            pass

                    if "Temp:" in line:
                        try:
                            # Handle both "Temp: 760" and "Temp:760"
                            raw_val = float(line.split(":")[1].strip())
                            # Calibration: Most hobbyist sensors (TMP36) send millivolts
                            # conversion: (mV - 500) / 10
                            if raw_val > 300: # Heuristic for raw mV vs Celsius
                                raw_val = (raw_val - 500.0) / 10.0
                            # Layer 2: Median + outlier rejection
                            smoothed = smooth_temp.update(raw_val, "Temp")
                            base_t = smoothed + TEMP_CALIBRATION_OFFSET
                            latest_data["T"] = base_t + THERMAL_RESISTANCE_FACTOR * max(0.0, base_t - 25.0)
                            _temp_received = True
                            print(f"🌡️ TEMP DEBUG → Raw: {raw_val:.2f}°C | Smoothed: {smoothed:.2f}°C | Calibrated: {latest_data['T']:.2f}°C | Heater Q: {latest_data['Q']}W | Ready: {latest_data.get('ready', '?')}")
                        except: pass
                    elif "Pressure:" in line:
                        try:
                            # ESP32 sends gauge pressure in MPa from the 1.2 MPa sensor.
                            p_val_mpa = float(line.split(":")[1].strip())
                            p_val = p_val_mpa * 10.0 # Convert MPa to bar
                            # Layer 2: Median + outlier rejection (on gauge value)
                            p_smoothed = smooth_pressure.update(p_val, "Pressure")
                            # Auto-zero: if cold and not yet calibrated, collect samples
                            if not _pressure_autozero_done and _temp_received and latest_data.get("T", 99) < 40:
                                _pressure_autozero_samples.append(p_smoothed)
                                if len(_pressure_autozero_samples) >= AUTOZERO_N_SAMPLES:
                                    PRESSURE_CALIBRATION_OFFSET = -np.mean(_pressure_autozero_samples)
                                    _pressure_autozero_done = True
                                    print(f"🎯 PRESSURE AUTO-ZERO: offset set to {PRESSURE_CALIBRATION_OFFSET:+.4f} bar from {AUTOZERO_N_SAMPLES} cold readings")
                            latest_data["P"] = p_smoothed + 1.013 + PRESSURE_CALIBRATION_OFFSET
                            print(f"🔍 PRESSURE DEBUG → Raw: {p_val:.4f} | Smoothed: {p_smoothed:.4f} bar | Offset: {PRESSURE_CALIBRATION_OFFSET:+.3f} | Abs: {latest_data['P']:.4f} bar")
                        except:
                            pass
                    elif "P_ADC:" in line:
                        try:
                            adc_raw = int(line.split(":")[1].strip())
                            adc_voltage = adc_raw * 0.0001875
                            sensor_voltage = adc_voltage * 1.5
                            pressure_bar = max(0.0, min(12.0, (sensor_voltage - 0.664) * 3.0))
                            p_smoothed = smooth_pressure.update(pressure_bar, "Pressure")
                            # Auto-zero from ADS readings too
                            if not _pressure_autozero_done and _temp_received and latest_data.get("T", 99) < 40:
                                _pressure_autozero_samples.append(p_smoothed)
                                if len(_pressure_autozero_samples) >= AUTOZERO_N_SAMPLES:
                                    PRESSURE_CALIBRATION_OFFSET = -np.mean(_pressure_autozero_samples)
                                    _pressure_autozero_done = True
                                    print(f"🎯 PRESSURE AUTO-ZERO: offset set to {PRESSURE_CALIBRATION_OFFSET:+.4f} bar from {AUTOZERO_N_SAMPLES} cold readings")
                            latest_data["P"] = p_smoothed + 1.013 + PRESSURE_CALIBRATION_OFFSET
                            print(f"🔍 PRESSURE DEBUG → ADS1115 counts: {adc_raw} | ADS V: {adc_voltage:.4f} | Sensor V: {sensor_voltage:.4f} | Calc: {pressure_bar:.3f} bar gauge")
                        except:
                            pass
                    elif "P_Volts:" in line:
                        try:
                            ads_v = float(line.split(":")[1].strip())
                            sensor_v = ads_v * 1.5
                            pressure_bar = max(0.0, min(12.0, (sensor_v - 0.664) * 3.0))
                            p_smoothed = smooth_pressure.update(pressure_bar, "Pressure")
                            # Auto-zero from P_Volts readings too
                            if not _pressure_autozero_done and _temp_received and latest_data.get("T", 99) < 40:
                                _pressure_autozero_samples.append(p_smoothed)
                                if len(_pressure_autozero_samples) >= AUTOZERO_N_SAMPLES:
                                    PRESSURE_CALIBRATION_OFFSET = -np.mean(_pressure_autozero_samples)
                                    _pressure_autozero_done = True
                                    print(f"🎯 PRESSURE AUTO-ZERO: offset set to {PRESSURE_CALIBRATION_OFFSET:+.4f} bar from {AUTOZERO_N_SAMPLES} cold readings")
                            latest_data["P"] = p_smoothed + 1.013 + PRESSURE_CALIBRATION_OFFSET
                            print(f"🔍 PRESSURE DEBUG → ADS voltage: {ads_v:.4f} V | Sensor voltage: {sensor_v:.4f} V | Calc: {pressure_bar:.3f} bar gauge")
                        except:
                            pass
                    elif "P_SensorVolts:" in line:
                        try:
                            sensor_v = float(line.split(":")[1].strip())
                            pressure_bar = max(0.0, min(12.0, (sensor_v - 0.664) * 3.0))
                            p_smoothed = smooth_pressure.update(pressure_bar, "Pressure")
                            latest_data["P"] = p_smoothed + 1.013 + PRESSURE_CALIBRATION_OFFSET
                            print(f"🔍 PRESSURE DEBUG → Sensor voltage: {sensor_v:.4f} V | Calc: {pressure_bar:.3f} bar gauge | Abs: {latest_data['P']:.4f} bar")
                        except:
                            pass
                    elif "P_RawBar:" in line:
                        try:
                            pressure_bar = max(0.0, min(12.0, float(line.split(":")[1].strip())))
                            p_smoothed = smooth_pressure.update(pressure_bar, "Pressure")
                            latest_data["P"] = p_smoothed + 1.013 + PRESSURE_CALIBRATION_OFFSET
                            print(f"🔍 PRESSURE DEBUG → RawBar: {pressure_bar:.3f} | Smoothed: {p_smoothed:.3f} bar gauge | Abs: {latest_data['P']:.4f} bar")
                        except:
                            pass
                    elif "Flow:" in line:
                        try:
                            # Flow in L/min from Arduino flow meter
                            raw_flow = float(line.split(":")[1].strip())
                            # Layer 2: Median + outlier rejection
                            flow_lpm = smooth_flow.update(raw_flow, "Flow")
                            latest_data["mw"] = flow_lpm

                            # ── Live Water Tracking in Liters ──
                            global water_mass_kg, current_water_volume_L, last_flow_time
                            now = time.time()
                            dt_sec = now - last_flow_time

                            if dt_sec < 10:  # Guard against stale timestamps
                                dt_min = dt_sec / 60.0

                                # 1. Water IN (from Arduino L/min)
                                # Apply a small deadband to prevent noise-induced accumulation
                                flow_lpm_clean = flow_lpm if flow_lpm >= 0.05 else 0.0
                                flow_in_L = flow_lpm_clean * dt_min

                                # Use actual density at current temperature for mass tracking
                                cur_P_pa = latest_data.get("P", 1.013) * 1e5
                                cur_T_actual = latest_data.get("T", 25.0)
                                rho_w_actual = thermo.get_rho_w_subcooled(cur_P_pa, cur_T_actual)
                                if flow_lpm_clean > 0:
                                    water_mass_kg += flow_lpm_clean * dt_min * (rho_w_actual / 1000.0)

                                # 2. Steam OUT (Physical Venting & Leaks)
                                # Mass only leaves the boiler if the valve is open or via parasitic leaks.
                                # Boiling in a closed vessel conserves total mass (liquid turns to trapped vapor).
                                P_gauge_bar = max(0.0, cur_P_pa / 1e5 - 1.013)
                                m_leak_kg_s = const.K_LEAK * P_gauge_bar
                                m_valve_kg_s = 0.0

                                if latest_data.get("valve") == "OPEN" and P_gauge_bar > 0.02:
                                    rho_s = thermo.get_rho_s(cur_P_pa)
                                    A_orifice = 3.14159 / 4.0 * const.D_PIPE**2
                                    k = 1.3
                                    r = 1.013e5 / cur_P_pa
                                    r_c = (2.0 / (k + 1.0)) ** (k / (k - 1.0))
                                    if r <= r_c: r = r_c
                                    term = max(0.0, (k / (k - 1.0)) * (r**(2.0/k) - r**((k+1.0)/k)))
                                    m_valve_kg_s = const.C_D_VALVE * A_orifice * 1.0 * (2.0 * cur_P_pa * rho_s * term)**0.5

                                mass_loss_kg = (m_leak_kg_s + m_valve_kg_s) * dt_sec
                                water_mass_kg -= mass_loss_kg
                                flow_out_L = mass_loss_kg / (rho_w_actual / 1000.0)

                                # ── V_new = V_old + (dV/dt * dt) ──
                                from config import constants as const
                                current_water_volume_L = max(0.1, min(current_water_volume_L + (flow_in_L - flow_out_L), const.V_T * 1000.0))

                                # Hard-clamp water mass to physical vessel capacity to prevent hydraulic lock in the model
                                water_mass_kg = min(water_mass_kg, const.V_T * rho_w_actual)

                                # Make this live explicitly visible to dashboard as a live sensor!
                                latest_data["Water_Volume_Liters"] = round(current_water_volume_L, 3)

                            last_flow_time = now
                        except: pass
                    elif "Pump:" in line:
                        try: latest_data["pump"] = int(line.split(":")[1].strip())
                        except: pass
                    elif "Heater:" in line:
                        val = line.split(":")[1].strip()
                        new_Q = 1000.0 if val == "ON" else 0.0
                        # Log heater state transitions
                        if new_Q != latest_data["Q"]:
                            print(f"🔥 HEATER STATE CHANGED → {val} (Q: {latest_data['Q']}→{new_Q}W) | Ready: {latest_data.get('ready', '?')} | FloatHigh: {latest_data.get('float_high', '?')}")
                        latest_data["Q"] = new_Q
                        # Serial confirmed heater state — clear pending flag
                        if val == "ON":
                            heater_cmd_pending = False
                        elif val == "OFF":
                            heater_cmd_pending = False
                    elif "Mode:" in line:
                        latest_data["mode"] = line.split(":")[1].strip()
                    elif "FloatLow:" in line:
                        latest_data["float_low"] = 1 if line.split(":")[1].strip() == "1" else 0
                        sync_water_from_float_state()
                    elif "FloatHigh:" in line:
                        latest_data["float_high"] = 1 if line.split(":")[1].strip() == "1" else 0
                        sync_water_from_float_state()
                    elif "Valve:" in line:
                        val = line.split(":")[1].strip()
                        if val in ("OPEN", "CLOSED"):
                            latest_data["valve"] = val
                    elif "Ready:" in line:
                        new_ready = 1 if line.split(":")[1].strip() == "1" else 0
                        if new_ready != latest_data.get("ready", -1):
                            print(f"⚠️ SYSTEM READY STATE → {'READY' if new_ready else 'NOT READY (heater will be blocked!)'} | FloatHigh: {latest_data.get('float_high', '?')}")
                        latest_data["ready"] = new_ready

                    # ── Live Analytical Updates ──
                    now = time.time()
                    dt_sec = now - last_flow_time if 'last_flow_time' in globals() else 2.0

                    # 0. EKF Predict-Update Cycle (sensor-model fusion)
                    try:
                        boiler_ekf.predict_and_update(
                            z_T=latest_data["T"],
                            z_P_abs=latest_data["P"],
                            z_V_L=current_water_volume_L,
                            Q_watts=latest_data["Q"],
                            m_w_kgs=latest_data["mw"] / 60.0,
                            valve_opening=0.0,
                            water_mass_kg=water_mass_kg
                        )
                        # Store fused state in latest_data for dashboard access
                        fused = boiler_ekf.get_fused_state()
                        latest_data["kalman"] = fused
                    except Exception as ekf_err:
                        print(f"⚠️ [EKF] Update failed: {ekf_err}")

                    # 1. Update Efficiency Tracker
                    try:
                        efficiency_tracker.update(
                            T_celsius=latest_data["T"],
                            P_abs_bar=latest_data["P"],
                            Q_watts=latest_data["Q"],
                            water_mass_kg=water_mass_kg,
                            dt_seconds=dt_sec
                        )
                    except Exception as eff_err:
                        print(f"⚠️ [Efficiency] Update failed: {eff_err}")

                    # 2. Update Validation Logger with current actuals
                    try:
                        validation_logger.record_actual(
                            T=latest_data["T"],
                            P_abs=latest_data["P"]
                        )
                    except Exception as val_err:
                        print(f"⚠️ [Validation] Record failed: {val_err}")

                    # 3. Session Logging (throttle to ~1Hz)
                    # We use a simple counter to log every 5th valid line
                    if 'log_throttle' not in locals(): log_throttle = 0
                    log_throttle += 1
                    if log_throttle >= 5:
                        log_throttle = 0
                        try:
                            short_forecast = compute_short_forecast()
                            if short_forecast["T"] is not None and short_forecast["P"] is not None:
                                validation_logger.record_prediction([{
                                    "t_min": short_forecast["horizon_s"] / 60.0,
                                    "T": short_forecast["T"],
                                    "P": short_forecast["P"],
                                }])

                            session_logger.log(
                                T_act=latest_data["T"],
                                P_gauge=max(0, latest_data["P"] - 1.013),
                                T_pred=short_forecast["physics_T"],
                                P_pred=short_forecast["physics_P"],
                                Q=latest_data["Q"],
                                flow=latest_data["mw"],
                                water_L=latest_data.get("Water_Volume_Liters", 0),
                                eta=efficiency_tracker.instantaneous_eta,
                                health=anomaly_detector.health_score,
                                anomaly=len(anomaly_detector.active_anomalies) > 0,
                                prediction_horizon_s=short_forecast["horizon_s"],
                                prediction_target_timestamp=short_forecast["target_ts"],
                                L_pred=short_forecast["L"]
                            )
                        except Exception as log_err:
                            print(f"⚠️ [Logger] CSV log failed: {log_err}")

        except Exception as e:
            if is_connected:
                print(f"⚠️ Serial Error: {e}")
                # Don't just say unplugged, show the traceback if it's not a SerialException
                if not isinstance(e, serial.SerialException):
                    import traceback
                    traceback.print_exc()
                is_connected = False
            time.sleep(2)

def run_autopilot():
    """
    Background thread for Proactive Model-Based Control.
    Runs a 5-minute forecast every few seconds to decide heater state.
    """
    global autopilot_state, latest_data, water_mass_kg
    print("🤖 Predictive Autopilot Thread Started")

    while True:
        try:
            # Heartbeat for debugging
            # print(f"DEBUG: Autopilot Thread Heartbeat (Mode: {autopilot_state['mode']}, Connected: {is_connected})")

            if not is_connected or autopilot_state["mode"] != "auto":
                time.sleep(2)
                continue

            print(f"🤖 [Auto] Decision Cycle Start...")

            # 1. Get current state
            P_gauge = max(0, latest_data["P"] - 1.013)
            T_curr = latest_data["T"]
            mw_curr = latest_data.get("mw", 0) / 60.0
            target = autopilot_state["target_p"]

            # 2. Run 5-minute "What If" Forecast (assuming 1kW heater is ON)
            # Internal prediction for proactive decision making
            P_init_pa = latest_data["P"] * 1e5
            Vdw_init, phi_init, _ = compute_initial_state(
                T_celsius=T_curr,
                P_pa=P_init_pa,
                water_mass_kg=water_mass_kg
            )

            # Predict 5 minutes ahead
            P_final, _, _, _, _, _ = predict_forward(
                P_init=P_init_pa,
                Vdw_init=Vdw_init,
                phi_init=phi_init,
                m_w=mw_curr,
                Q=1000.0, # What if heater is ON?
                valve_opening=0.0,
                T_init=T_curr,
                duration=60.0 # 60-second forecast
            )

            f_p_gauge = max(0, (P_final / 1e5) - 1.013)
            autopilot_state["forecast_p_60s"] = round(f_p_gauge, 3)

            # 3. Decision Logic (Auto-Valve — heater runs until target is actually reached)
            if P_gauge >= target:
                # ── Target reached: cut heater AND open valve to vent ──
                if latest_data["Q"] > 0:
                    command_queue.put("HEATER_OFF\n")
                    print(f"🤖 [Auto] Target reached ({P_gauge:.2f} bar). Cutting heat.")
                if latest_data.get("valve") != "OPEN":
                    command_queue.put("VALVE_ON\n")
                    print(f"🤖 [Auto] Opening valve to vent excess pressure at {P_gauge:.2f} bar (target: {target:.2f}).")
                autopilot_state["status"] = "venting"
            elif P_gauge < (target - 0.1):
                # Below target with hysteresis — close valve and heat
                if latest_data.get("valve") == "OPEN":
                    command_queue.put("VALVE_OFF\n")
                    print(f"🤖 [Auto] Closing valve — below target, conserving pressure.")
                if latest_data["Q"] == 0:
                    command_queue.put("HEATER_ON\n")
                    autopilot_state["status"] = "heating"
                    print(f"🤖 [Auto] Below target. Heating.")
            else:
                # In the deadband (target - 0.1 to target): keep heating, close valve
                if latest_data.get("valve") == "OPEN":
                    command_queue.put("VALVE_OFF\n")
                    print(f"🤖 [Auto] Closing valve — approaching target.")
                autopilot_state["status"] = "stabilizing"

            time.sleep(5) # Control cycle interval

        except Exception as e:
            print(f"❌ [Autopilot] Error in control loop: {e}")
            time.sleep(5)

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        print(f"📥 Incoming GET request: {self.path}")
        try:
            # Clean path to ignore query parameters like ?predict=true
            clean_path = self.path.split('?')[0]

            if clean_path == '/data':
                if is_connected:
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    # Inject Autopilot state and Digital Twin metrics into the telemetry feed
                    response = {
                        **latest_data,
                        "autopilot": autopilot_state,
                        "digital_twin": {
                            "efficiency": efficiency_tracker.get_metrics(),
                            "validation": validation_logger.get_metrics(),
                            "health": anomaly_detector.get_status(),
                            "session": session_logger.get_info(),
                            "kalman": boiler_ekf.get_metrics()
                        }
                    }
                    self.wfile.write(json.dumps(response).encode('utf-8'))
                else:
                    self.send_response(503)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "Serial not connected"}).encode('utf-8'))
            elif clean_path == '/predict':
                print("DEBUG: Received prediction request")
                try:
                    if is_connected:
                        import math
                        from urllib.parse import urlparse, parse_qs
                        def clean_val(v, default=0.0):
                            return default if math.isnan(v) or math.isinf(v) else v

                        # ── Parse demand parameters from query string ──
                        parsed = urlparse(self.path)
                        qp = parse_qs(parsed.query)
                        demand_minutes = int(qp.get('minutes', ['10'])[0])
                        target_pressure_bar = float(qp.get('target_pressure', ['0'])[0])
                        r_fouling_str = qp.get('r_fouling', ['0.0'])[0]

                        try:
                            from config import constants as const
                            const.R_FOULING = float(r_fouling_str)
                            print(f"DEBUG: R_FOULING set to {const.R_FOULING}")
                        except Exception as e:
                            print(f"DEBUG: Failed to override Fouling Factor - {e}")

                        # Clamp to valid range
                        demand_minutes = max(1, min(demand_minutes, 30))
                        print(f"DEBUG: Demand → {demand_minutes} min, target P = {target_pressure_bar} bar")

                        # Determine effective heater power:
                        # Use actual Q if serial has confirmed, OR use pending flag
                        effective_Q = latest_data["Q"]
                        if effective_Q == 0 and heater_cmd_pending:
                            effective_Q = 1000.0  # 1kW — user has clicked Start Heater
                            print("DEBUG: Using heater_cmd_pending flag (serial echo not yet received)")

                        # If heater is effectively OFF AND no water is flowing, return static idle baseline
                        # But if water IS flowing, still run the prediction to track water level changes
                        if effective_Q == 0 and latest_data.get("mw", 0) <= 0:
                            # Derive current state from live sensors + flow tracking
                            _, _, L_live = compute_initial_state(
                                T_celsius=latest_data["T"],
                                P_pa=latest_data["P"] * 1e5,
                                water_mass_kg=water_mass_kg
                            )
                            prediction = {
                                "status": "idle_baseline",
                                "heater_power_kw": 0.0,
                                "demand_minutes": demand_minutes,
                                "target_pressure_bar": target_pressure_bar,
                                "current": {
                                    "T": latest_data["T"],
                                    "P": round(max(0, latest_data["P"] - 1.013), 3),
                                    "L": round(L_live, 3)
                                },
                                "timeline": [],
                                "time_to_target": None
                            }
                        elif effective_Q == 0 and latest_data.get("mw", 0) > 0:
                            # Water is flowing but heater is OFF — still calculate water level prediction
                            P_init_pa = latest_data["P"] * 1e5
                            mw_init_kgs = latest_data["mw"] / 60.0

                            Vdw_init, phi_init, L_init = compute_initial_state(
                                T_celsius=latest_data["T"],
                                P_pa=P_init_pa,
                                water_mass_kg=water_mass_kg
                            )
                            print(f"DEBUG: [Filling] Sensor-derived state → Vdw={Vdw_init:.5f} m³, phi={phi_init:.4f}, L={L_init:.4f} m (water={water_mass_kg:.2f} kg, flow={latest_data['mw']:.2f} L/min)")

                            timeline = []
                            timeline.append({
                                "t_min": 0,
                                "T": round(latest_data["T"], 1),
                                "P": round(max(0, latest_data["P"] - 1.013), 3),
                                "L": round(current_water_volume_L, 3)
                            })

                            try:
                                raw_timeline = predict_timeline(
                                    P_init=P_init_pa,
                                    Vdw_init=Vdw_init,
                                    phi_init=phi_init,
                                    m_w=mw_init_kgs,
                                    Q=0.0,  # No heater — just tracking water fill
                                    valve_opening=0.0,
                                    T_init=latest_data["T"],
                                    n_points=demand_minutes,
                                    step_seconds=60.0
                                )

                                for pt in raw_timeline:
                                    P_gauge = max(0, clean_val(pt["P"] / 1e5, latest_data["P"]) - 1.013)
                                    timeline.append({
                                        "t_min": pt["t_min"],
                                        "T": round(clean_val(pt["T"], latest_data["T"]), 1),
                                        "P": round(P_gauge, 3),
                                        "L": round(pt["Vdw"] * 1000.0, 3)
                                    })

                                prediction = {
                                    "status": "filling_prediction",
                                    "heater_power_kw": 0.0,
                                    "demand_minutes": demand_minutes,
                                    "target_pressure_bar": target_pressure_bar,
                                    "time_to_target": None,
                                    "current": {
                                        "T": latest_data["T"],
                                        "P": round(max(0, latest_data["P"] - 1.013), 3),
                                        "L": round(current_water_volume_L, 3)
                                    },
                                    "timeline": timeline
                                }
                                print(f"DEBUG: [Filling] {demand_minutes}-min water-level forecast served — L: {timeline[0]['L']}→{timeline[-1]['L']} L")

                            except Exception as solver_err:
                                print(f"❌ [Solver] Error calculating filling timeline: {solver_err}")
                                prediction = {
                                    "status": "solver_error",
                                    "heater_power_kw": 0.0,
                                    "current": {
                                        "T": latest_data["T"],
                                        "P": round(max(0, latest_data["P"] - 1.013), 3),
                                        "L": round(current_water_volume_L, 3)
                                    },
                                    "timeline": [],
                                    "error": str(solver_err)
                                }
                        else:
                            # ── Forward Prediction Timeline (demand-driven) ──
                            # Use Kalman-fused state if available, else raw sensors
                            fused = boiler_ekf.get_fused_state() if boiler_ekf.initialized else None
                            if fused and boiler_ekf.n_updates > 5:
                                T_init_val = fused["T_fused"]
                                P_init_pa = fused["P_fused"] * 1e5
                                V_init_L = fused["V_fused"]
                                # FIX: Use subcooled density at actual temperature, NOT saturated density
                                # get_rho_w() returns density at T_sat (~958 kg/m³ at 1atm/100°C)
                                # but actual water at 25°C is ~997 kg/m³ — 4% error per cycle!
                                rho_w_fused = thermo.get_rho_w_subcooled(P_init_pa, T_init_val)
                                water_mass_fused = V_init_L * (rho_w_fused / 1000.0)
                                print(f"DEBUG: [EKF] Using Kalman-fused state → T={T_init_val:.1f}°C, P={fused['P_fused']:.4f} bar, V={V_init_L:.3f} L, mass={water_mass_fused:.3f} kg (ρ={rho_w_fused:.1f})")
                            else:
                                T_init_val = latest_data["T"]
                                P_init_pa = latest_data["P"] * 1e5
                                V_init_L = current_water_volume_L
                                water_mass_fused = water_mass_kg
                                print(f"DEBUG: [EKF] Kalman not ready — using raw sensors")

                            mw_init_kgs = latest_data["mw"] / 60.0

                            # Compute Vdw, phi, L from fused state
                            Vdw_init, phi_init, L_init = compute_initial_state(
                                T_celsius=T_init_val,
                                P_pa=P_init_pa,
                                water_mass_kg=water_mass_fused
                            )
                            print(f"DEBUG: Fused-derived state → Vdw={Vdw_init:.5f} m³, phi={phi_init:.4f}, L={L_init:.4f} m")

                            timeline = []
                            # t=0 is the current state — gauge pressure (0 at atmospheric)
                            P_abs_bar = P_init_pa / 1e5
                            timeline.append({
                                "t_min": 0,
                                "T": round(T_init_val, 1),
                                "P": round(max(0, P_abs_bar - 1.013), 3),
                                "L": round(V_init_L, 3)
                            })

                            try:
                                # Single-shot ODE solve with demand-driven time horizon
                                raw_timeline = predict_timeline(
                                    P_init=P_init_pa,
                                    Vdw_init=Vdw_init,
                                    phi_init=phi_init,
                                    m_w=mw_init_kgs,
                                    Q=effective_Q,
                                    valve_opening=0.0,
                                    T_init=T_init_val,
                                    n_points=demand_minutes,
                                    step_seconds=60.0
                                )

                                # Predict the 1-minute error rates using the ML model
                                error_rate_T = 0.0
                                error_rate_P = 0.0
                                if hybrid_ml_T is not None and hybrid_ml_P is not None:
                                    current_features = np.array([[
                                        latest_data["T"],
                                        max(0, latest_data["P"] - 1.013),
                                        latest_data["Q"],
                                        latest_data.get("mw", 0),
                                        current_water_volume_L
                                    ]])
                                    error_rate_T = hybrid_ml_T.predict(current_features)[0]
                                    error_rate_P = hybrid_ml_P.predict(current_features)[0]

                                for pt in raw_timeline:
                                    # Base pure physics prediction
                                    physics_T = clean_val(pt["T"], latest_data["T"])
                                    physics_P_gauge = max(0, clean_val(pt["P"] / 1e5, latest_data["P"]) - 1.013)
                                    
                                    # Temperature error does NOT scale linearly over 10 mins (non-linear heat loss curve)
                                    # So we apply a flat, smoothed offset. 
                                    hybrid_T = physics_T + error_rate_T
                                    
                                    # Pressure error scales linearly because it's a fixed volume expansion leak rate
                                    # UPDATE: Since K_LEAK is now 0.0, pure physics handles expansion perfectly.
                                    # We just apply a flat, smoothed offset to prevent massive overshoots above 100C!
                                    hybrid_P_gauge = max(0, physics_P_gauge + error_rate_P)
                                    
                                    timeline.append({
                                        "t_min": pt["t_min"],
                                        "T": round(hybrid_T, 1),
                                        "P": round(hybrid_P_gauge, 3),
                                        "L": round(pt["Vdw"] * 1000.0, 3)
                                    })

                                # ── Calculate time to reach target pressure ──
                                time_to_target = None
                                if target_pressure_bar > 0:
                                    for pt in timeline:
                                        if pt["P"] >= target_pressure_bar:
                                            time_to_target = pt["t_min"]
                                            break
                                    # If not reached within the window
                                    if time_to_target is None and len(timeline) > 1:
                                        time_to_target = -1  # -1 signals "not reachable in this window"

                                prediction = {
                                    "status": "active_prediction",
                                    "heater_power_kw": effective_Q / 1000.0,
                                    "demand_minutes": demand_minutes,
                                    "target_pressure_bar": target_pressure_bar,
                                    "time_to_target": time_to_target,
                                    "current": {
                                        "T": latest_data["T"],
                                        "P": round(max(0, latest_data["P"] - 1.013), 3),
                                        "L": round(current_water_volume_L, 3)
                                    },
                                    "timeline": timeline
                                }
                                # ── Feature 1: Record prediction for validation ──
                                validation_logger.record_prediction(timeline)

                                # ── Feature 3: Update Anomaly Detector with immediate forecast ──
                                if len(timeline) > 1:
                                    anomaly_detector.update(
                                        actual_T=latest_data["T"],
                                        predicted_T=timeline[0]["T"],
                                        actual_P=max(0, latest_data["P"] - 1.013),
                                        predicted_P=timeline[0]["P"]
                                    )

                                print(f"DEBUG: {demand_minutes}-min forecast served — T: {timeline[0]['T']}→{timeline[-1]['T']}°C, P: {timeline[0]['P']}→{timeline[-1]['P']} bar")

                            except Exception as solver_err:
                                print(f"❌ [Solver] Error calculating timeline: {solver_err}")
                                prediction = {
                                    "status": "solver_error",
                                    "heater_power_kw": effective_Q / 1000.0,
                                    "current": {
                                        "T": latest_data["T"],
                                        "P": round(max(0, latest_data["P"] - 1.013), 3),
                                        "L": round(current_water_volume_L, 3)
                                    },
                                    "timeline": [],
                                    "error": str(solver_err)
                                }

                        self.send_response(200)
                        self.send_header('Content-type', 'application/json')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(json.dumps(prediction).encode('utf-8'))
                        if effective_Q == 0:
                            print("DEBUG: Served idle baseline (Heater OFF)")
                    else:
                        print("DEBUG: Prediction requested but Serial not connected")
                        self.send_response(503)
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        self.wfile.write(json.dumps({"error": "Serial not connected"}).encode('utf-8'))
                except Exception as e:
                    print(f"❌ [Server] Prediction handler crashed: {e}")
                    self.send_response(500)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
            elif clean_path == '/export':
                # Serve the CSV log file
                info = session_logger.get_info()
                if os.path.exists(info["filepath"]):
                    self.send_response(200)
                    self.send_header('Content-type', 'text/csv')
                    self.send_header('Content-Disposition', f'attachment; filename="{info["filename"]}"')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    with open(info["filepath"], 'rb') as f:
                        self.wfile.write(f.read())
                else:
                    self.send_response(404)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            # Happens if the client (browser) disconnects early
            pass
    def do_POST(self):
        print(f"📥 Incoming POST request: {self.path}")
        try:
            if self.path == '/control':
                content_length = int(self.headers['Content-Length'])
                post_data = self.rfile.read(content_length)
                data = json.loads(post_data.decode('utf-8'))
                print(f"DEBUG: Control Payload → {data}")
                command = data.get('command')
                if command:
                    # Legacy command support
                    if not command.endswith('\n'):
                        command += '\n'
                    command_queue.put(command)

                    self.send_response(200)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "queued", "command": command.strip()}).encode('utf-8'))
                elif 'autopilot' in data:
                    # New Autopilot configuration support
                    cfg = data['autopilot']
                    if 'mode' in cfg:
                        autopilot_state['mode'] = cfg['mode']
                    if 'target_p' in cfg:
                        autopilot_state['target_p'] = float(cfg['target_p'])

                    print(f"🤖 [Auto] Configuration Updated: {autopilot_state['mode'].upper()}, Target: {autopilot_state['target_p']} bar")

                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "updated", "autopilot": autopilot_state}).encode('utf-8'))
                else:
                    self.send_response(400)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": "No command provided"}).encode('utf-8'))
            else:
                self.send_response(404)
                self.end_headers()
        except Exception as e:
            print(f"Server Error handling POST: {e}")
            self.send_response(500)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, format, *args):
        pass # Suppress logging so it doesn't spam the console

if __name__ == "__main__":
    # Start the serial reader in the background
    t = threading.Thread(target=read_serial, daemon=True)
    t.start()

    # Start the Autopilot background thread
    ta = threading.Thread(target=run_autopilot, daemon=True)
    ta.start()

    # Start the local Proxy Web Server for the Next.js Dashboard to read from
    server = HTTPServer(('127.0.0.1', 8080), RequestHandler)
    print("🌐 Python Serial-to-HTTP Proxy running on http://127.0.0.1:8080/data")
    server.serve_forever()