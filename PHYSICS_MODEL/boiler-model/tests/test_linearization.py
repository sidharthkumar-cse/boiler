import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import constants as const
from engine.solver_logic import predict_forward
from engine.linearization import predict_linear_jump

def run_test():
    print("=== Testing Linearized Matrix Exponentiation against Non-Linear Model ===")
    
    # Define equilibrium / operating point (x_op)
    P_op = 50e5
    m_s_target = 10.0
    phi_op = m_s_target / const.M_DC
    Vdw_op = 1.0 * const.A_D
    op_state = (P_op, Vdw_op, phi_op)
    
    # Define inputs (u_op) that maintain steady state
    m_w = 10.0
    valve_opening = 1.0
    from physics import thermo_relations as thermo
    h_s_nom = thermo.get_h_s(P_op)
    h_feed = 4186.0 * const.T_FEED
    Q = 10.0 * h_s_nom - 10.0 * h_feed
    op_inputs = (m_w, Q, valve_opening)
    
    # Evaluate a 2-minute jump for an initial state near equilibrium
    duration = 120.0
    
    P_init = 49e5  # 1 bar lower
    Vdw_init = 9.8 # slightly lower
    phi_init = phi_op + 0.01
    
    print("\n--- Initial State Before Jump ---")
    print(f"P: {P_init/1e5:.2f} bar | Vdw: {Vdw_init:.2f} m3 | phi: {phi_init:.4f}")
    
    # 1. Non-linear explicit time-step method
    P_nl, Vdw_nl, phi_nl, L_nl, T_nl = predict_forward(
        P_init, Vdw_init, phi_init, m_w, Q, valve_opening, duration=duration, dt=1.0)
    
    # 2. Linearized exact analytical matrix exponentiation jump
    P_lin, Vdw_lin, phi_lin, L_lin, T_lin = predict_linear_jump(
        P_init, Vdw_init, phi_init, op_state, op_inputs, duration=duration)
        
    print(f"\n--- After {duration}s ---")
    print("Non-Linear (dt=1.0s):")
    print(f"P: {P_nl/1e5:.3f} bar | Vdw: {Vdw_nl:.3f} m3 | phi: {phi_nl:.5f}")
    
    print("\nLinear Matrix Expm:")
    print(f"P: {P_lin/1e5:.3f} bar | Vdw: {Vdw_lin:.3f} m3 | phi: {phi_lin:.5f}")
    
    P_err = abs(P_lin - P_nl) / P_nl * 100
    Vdw_err = abs(Vdw_lin - Vdw_nl) / Vdw_nl * 100
    phi_err = abs(phi_lin - phi_nl) / phi_nl * 100
    
    print("\n--- Deviation / Approximation Error ---")
    print(f"P Error:   {P_err:.4f}%")
    print(f"Vdw Error: {Vdw_err:.4f}%")
    print(f"phi Error: {phi_err:.4f}%")
    
    if P_err < 1.0 and Vdw_err < 1.0 and phi_err < 1.0:
        print("\n[SUCCESS] Linearized model closely tracks non-linear model locally!")
    else:
        print("\n[WARNING] Linearized approximation drifts too far from non-linear physics.")

if __name__ == "__main__":
    run_test()
