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
from physics import thermo_relations as thermo

def verify_steady_state():
    print("--- Boiler Model Physical Verification ---")
    
    # 1. Setup nominal steady-state conditions
    P = 50e5        # 50 bar
    m_s_target = 10.0 # 10 kg/s nominal steam
    phi = m_s_target / const.M_DC
    L_target = 1.0
    V_dw = L_target * const.A_D
    
    # Inputs (Held Constant)
    m_w = 10.0      # Equal to m_s
    valve_opening = 1.0
    
    # Re-calculate Q to match m_g = m_s at steady state
    h_s = thermo.get_h_s(P)
    h_feed = 4186.0 * const.T_FEED
    Q = m_s_target * h_s - m_w * h_feed
    
    print(f"Initial State: P = {P/1e5:.1f} bar, V_dw = {V_dw:.1f} m^3, phi = {phi:.4f}")
    print(f"Constant Inputs: m_w = {m_w} kg/s, Q = {Q/1e6:.2f} MW, Valve = {valve_opening*100}%\n")
    
    # 2. Run simulation for a long time to prove stability and no divergence
    duration = 5000
    dt = 1.0
    
    for _ in np.arange(0, duration, dt):
        X = model.solve_system(P, V_dw, phi, m_w, Q, valve_opening)
        dP_dt, dVdw_dt, dphi_dt, m_g = X
        
        P += dP_dt * dt
        V_dw += dVdw_dt * dt
        phi += dphi_dt * dt
        
        # Clamp
        if P < 1.0: P = 1.0
        if V_dw < 0.0: V_dw = 0.0
        if phi < 0.0: phi = 0.0
        if phi > 1.0: phi = 1.0

    print("--- 1. Stability under constant inputs ---")
    print(f"After {duration} seconds:")
    print(f"dP/dt   = {dP_dt:10.5e} Pa/s  (Expected ~0)")
    print(f"dVdw/dt = {dVdw_dt:10.5e} m^3/s (Expected ~0)")
    print(f"dphi/dt = {dphi_dt:10.5e} 1/s   (Expected ~0)")
    if abs(dP_dt) < 1e-3 and abs(dVdw_dt) < 1e-3 and abs(dphi_dt) < 1e-4:
        print("[PASS] System is perfectly stable and derivatives approach 0.")
    else:
        print("[FAIL] System is not stable.")
        
    print("\n--- 2. No Divergence ---")
    print(f"Final P = {P/1e5:.2f} bar (Expected exactly 50.00 bar)")
    if abs(P - 50e5) < 100:
        print("[PASS] Pressure does not grow infinitely; remains bounded and solid.")
    else:
        print("[FAIL] Pressure diverged.")

    # Re-calculate m_s out
    Kv = const.K_VALVE * valve_opening
    m_s = Kv * np.sqrt(P)
    
    print("\n--- 3. Steam Balance ---")
    print(f"Generation (m_g) = {m_g:.5f} kg/s")
    print(f"Steam Out (m_s)  = {m_s:.5f} kg/s")
    if abs(m_g - m_s) < 1e-3:
        print("[PASS] mg = ms at steady state.")
    else:
        print("[FAIL] Steam balance violated.")
        
    print("\n--- 4. Mass Balance (Liquid) ---")
    accumulation = m_w - m_g
    print(f"Input (m_w) = {m_w:.5f} kg/s")
    print(f"Generation + Accumulation = {m_g + 0.0:.5f} kg/s (Accumulation is 0.0 at Steady State)")
    if abs(m_w - (m_g + 0.0)) < 1e-3:
        print("[PASS] mw = mg + accumulation.")
    else:
        print("[FAIL] Liquid mass balance violated.")
        
    print("\n--- 5. Energy Balance ---")
    energy_in = Q + m_w * h_feed
    energy_out = m_s * h_s
    # Energy stored at steady state is 0.
    print(f"Energy In (Q + m_w*h_feed) = {energy_in/1e6:.5f} MW")
    print(f"Energy Out (m_s*h_s)       = {energy_out/1e6:.5f} MW")
    if abs(energy_in - energy_out) < 100:
        print("[PASS] Q = energy stored (0) + energy carried by steam.")
    else:
        print("[FAIL] Energy balance violated.")

if __name__ == '__main__':
    verify_steady_state()
