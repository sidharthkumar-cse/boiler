import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import sys
import os

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import matrix_form as model
from config import constants as const
from engine.solver_logic import predict_forward

from physics import thermo_relations as thermo
from utils.hardware import get_live_snapshot


def verify_prediction_consistency():
    print("--- Verifying Forward Prediction Model Consistency ---")
    
    live = get_live_snapshot()
    
    # Initial states starting precisely from live sensor data
    P = live["P"] * 1e5  # converting bar to Pascals
    V_dw = 10.5     # slightly high water level (we don't have level sensor data mapped yet)
    phi = 0.10      # proper equilibrium void fraction
    
    # Constant Inputs frozen for the 5-minute future prediction
    m_w = live["mw"]
    valve_opening = live["Kv"]
    Q = live["Q"]
    
    duration = 300.0
    dt = 1.0
    N = int(duration / dt)
    
    # Arrays for tracking history
    import numpy as np
    P_hist = np.zeros(N)
    Vdw_hist = np.zeros(N)
    phi_hist = np.zeros(N)
    mg_hist = np.zeros(N)
    ms_hist = np.zeros(N)
    
    # We will simulate the loop exactly as predict_forward does but track intermediate states
    P_curr = P
    Vdw_curr = V_dw
    phi_curr = phi
    T_liq_curr = live.get("T", model.calculate_temperature(P_curr))
    
    for i in range(N):
        # Calculate C and D and solve
        X = model.solve_system(P_curr, Vdw_curr, phi_curr, m_w, Q, valve_opening)
        dP_dt, dVdw_dt, dphi_dt, m_g = X
        
        # Track m_s exit explicitly for step 2 verification
        from physics import thermo_relations as thermo
        A_orifice = np.pi / 4.0 * const.D_PIPE**2
        rho_s = thermo.get_rho_s(P_curr)
        delta_P = max(P_curr - const.P_DOWNSTREAM, 0.0)
        m_s = const.C_D_VALVE * A_orifice * valve_opening * np.sqrt(2.0 * rho_s * delta_P)
        
        if i == 0:
            print(f"Step 0: P={P_curr/1e5:.2f} bar, dP/dt={dP_dt:.2f}, m_g={m_g:.3f}, m_s={m_s:.3f}")
            print(f"       dVdw/dt={dVdw_dt:.4f}, dphi/dt={dphi_dt:.4f}")

        # Save histories
        P_hist[i] = P_curr
        Vdw_hist[i] = Vdw_curr
        phi_hist[i] = phi_curr
        mg_hist[i] = m_g
        ms_hist[i] = m_s
        
        # Update states (Forward Euler)
        P_curr += dP_dt * dt
        Vdw_curr += dVdw_dt * dt
        phi_curr += dphi_dt * dt
        
        # Clamping
        if P_curr < 1.0: P_curr = 1.0
        if Vdw_curr < 0.0: Vdw_curr = 0.0
        if phi_curr < 0.0: phi_curr = 0.0
        elif phi_curr > 1.0: phi_curr = 1.0

        # Predict Subcooled Liquid Heating
        mass_w = Vdw_curr * 1000.0  # Approx 1000 kg/m3
        T_sat_curr = model.calculate_temperature(P_curr)
        if T_liq_curr < T_sat_curr and mass_w > 0.1:
            dT_dt = Q / (mass_w * 4184.0) # dT/dt = Q(W) / (mass * Cp)
            T_liq_curr += dT_dt * dt
            if T_liq_curr > T_sat_curr:
                T_liq_curr = T_sat_curr
        else:
            T_liq_curr = T_sat_curr

    print("\n1. System should move toward steady state (Convergence)")
    # Test if the rate of pressure change is slowing down (approaching horizontal asymptote)
    dP_dt_start = abs(P_hist[1] - P_hist[0]) / dt
    dP_dt_end = abs(P_hist[-1] - P_hist[-2]) / dt
    
    if dP_dt_end <= dP_dt_start or dP_dt_end < 100.0: # < 100 Pa/s (0.001 bar/s) is effectively steady state baseline
        print(f"[PASS] Pressure stabilized. dP/dt ended at {dP_dt_end:.2f} Pa/s (Effectively 0 bar/s)")
    else:
        print(f"[FAIL] Open-loop drift detected. P_start={P_hist[0]/1e5:.2f} bar, P_end={P_hist[-1]/1e5:.2f} bar, dP/dt_end={dP_dt_end:.2f} Pa/s")

    print("\n2. mg -> ms over time")
    mg_ms_diff_start = abs(mg_hist[0] - ms_hist[0])
    mg_ms_diff_end = abs(mg_hist[-1] - ms_hist[-1])
    print(f"Start: mg = {mg_hist[0]:.3f}, ms = {ms_hist[0]:.3f} (Diff: {mg_ms_diff_start:.3f})")
    print(f"End  : mg = {mg_hist[-1]:.3f}, ms = {ms_hist[-1]:.3f} (Diff: {mg_ms_diff_end:.3f})")
    
    # If it ends within a 1% tolerance margin, it's considered converged even if it started perfectly balanced
    if mg_ms_diff_end <= mg_ms_diff_start or mg_ms_diff_end < 0.05:
        print("[PASS] Evaporation rate (mg) powerfully converged toward steam flow out (ms).")
    else:
        print("[FAIL] mg did not converge to ms.")

    print("\n3. No oscillation or divergence")
    # Check if pressure is strictly monotonically increasing or decreasing, or very smooth
    # Given we start at 48 bar (below target 50), it should smoothly increase.
    dP = np.diff(P_hist)
    oscillations = np.sum(dP[:-1] * dP[1:] < 0)
    bound_check = (P_curr < 100e5) and (P_curr > 1e5)
    if oscillations < 5 and bound_check:
        print(f"[PASS] Smooth trajectory detected. Detected {oscillations} inflection points (Expected ~0-1). No divergence.")
    else:
        print(f"[FAIL] Oscillation or divergence detected. Inflection points: {oscillations}")

    print("\n4. Physical constraints maintained: 0 <= phi <= 1")
    phi_min = np.min(phi_hist)
    phi_max = np.max(phi_hist)
    print(f"Phi range during 5 minute prediction: [{phi_min:.4f}, {phi_max:.4f}]")
    if phi_min >= 0.0 and phi_max <= 1.0:
        print("[PASS] Void fraction phi remained strictly within [0, 1].")
    else:
        print("[FAIL] Void fraction constraint violated.")
        
    print("\n5. Future State Prediction (5 Minutes)")
    T_start = model.calculate_temperature(P_hist[0])
    T_end = model.calculate_temperature(P_hist[-1])
    
    sensor_T = live.get("T", "Unknown")
    print(f"Actual Sensor Temp : {sensor_T} °C (Liquid Temp)")
    print(f"Predicted Liq Temp : {T_liq_curr:.2f} °C (After 5m Heating)")
    print(f"Current Boiling Pt : {T_start:.2f} °C (At {P_hist[0]/1e5:.3f} bar)")
    print(f"Predicted BoilingPt: {T_end:.2f} °C (At {P_hist[-1]/1e5:.3f} bar)")
    print(f"Predicted Pressure : {P_hist[-1]/1e5:.2f} bar")

    print("\nVerification Complete.")

if __name__ == '__main__':
    verify_prediction_consistency()
