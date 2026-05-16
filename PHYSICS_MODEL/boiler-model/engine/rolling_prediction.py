import numpy as np
import sys
import os

# Ensure model packages can be imported
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.solver_logic import run_continuous, predict_forward

def rolling_prediction_sim(duration=20, dt=1.0, horizon=300.0):
    print("==================================================")
    print(" CONTINUOUS BOILER SIMULATION: ROLLING PREDICTION ")
    print("==================================================\n")
    
    # Base Inputs
    m_w = 10.0
    Q = 20e6
    valve_opening = 1.0
    
    # Initialize the baseline physics engine for realtime rolling state
    boiler_twin = run_continuous(P_init=50e5, Vdw_init=10.0, phi_init=0.1, 
                                 m_w=m_w, Q=Q, valve_opening=valve_opening, dt=dt)
    
    # 1. State at t=0
    P, Vdw, phi, L, T = next(boiler_twin)
    
    t = 0.0
    while t <= duration:
        print("-" * 50)
        print(f"Time t = {t:.1f} s")
        print("-" * 50)
        
        # 2. FUTURE PREDICTION (Horizon = 300s)
        # Using current states (P, Vdw, phi) as `P*, Vdw*, phi*`
        # Simulating forward for 300 seconds using the same physics model
        P_pred, Vdw_pred, phi_pred, L_pred, T_pred = predict_forward(
            P, Vdw, phi, m_w, Q, valve_opening, duration=horizon, dt=dt
        )
        
        # 3. OUTPUT BOTH (Current and Predicted)
        print("Current:")
        print(f"P({t:.0f})    = {P/1e5:.2f} bar")
        print(f"L({t:.0f})    = {L:.3f} m")
        print(f"T({t:.0f})    = {T:.1f} °C")
        
        print(f"\nPredicted (t + {horizon:.0f}s):")
        print(f"P_pred({t+horizon:.0f}) = {P_pred/1e5:.2f} bar")
        print(f"L_pred({t+horizon:.0f}) = {L_pred:.3f} m")
        print(f"T_pred({t+horizon:.0f}) = {T_pred:.1f} °C\n")
        
        # 1. CURRENT STATE UPDATE (Physics Engine)
        # Advance physics model by +dt
        t += dt
        P, Vdw, phi, L, T = boiler_twin.send((m_w, Q, valve_opening))

if __name__ == '__main__':
    # Run for a short duration to demonstrate the loop continuously
    rolling_prediction_sim(duration=5, dt=1.0, horizon=300.0)
