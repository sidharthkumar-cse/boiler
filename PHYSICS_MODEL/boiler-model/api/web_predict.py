import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sys
import json
import numpy as np
from scipy.integrate import solve_ivp
from engine.solver_logic import system_derivatives, calculate_dynamic_temperature
from core import matrix_form as model
from config import constants as const

def generate_timeseries(P_start, Vdw_start, phi_start, m_w, Q, valve, T_start=None, horizon=300.0, step=5.0):
    """
    Run prediction and capture states every 'step' seconds using scipy solve_ivp.
    """
    P = P_start
    V_dw = Vdw_start
    phi = phi_start
    
    # Track current temperature if subcooled logic is needed
    current_T = T_start
    
    results = []
    # Simple PI Level Controller for realistic transients
    Kp = 5.0 # Feedwater proportional gain
    
    # Initial state
    L_initial = model.calculate_drum_level(V_dw, phi, P)
    T_disp = current_T if current_T is not None else model.calculate_temperature(P)
    results.append({
        "time": 0,
        "P": round(P / 1e5, 2), # bar
        "L": round(L_initial, 3),        # m
        "T": round(T_disp, 1),         # C
        "mw": round(m_w, 2)      # kg/s
    })

    total_records = int(horizon / step)
    current_time = 0.0
    current_mw = m_w
    
    y = [P, V_dw, phi]
    
    for i in range(1, total_records + 1):
        # Update Feedwater based on level error (simple P-control)
        P_current = max(y[0], 1.0)
        Vdw_current = max(y[1], 0.0)
        phi_current = max(0.0, min(1.0, y[2]))
        
        L_current = model.calculate_drum_level(Vdw_current, phi_current, P_current)
        current_mw = m_w + Kp * (1.0 - L_current)
        current_mw = max(0.0, min(50.0, current_mw)) # Saturate flow
        
        # Integrate forward by 'step' seconds
        t_span = (current_time, current_time + step)
        
        sol = solve_ivp(
            fun=lambda t, y_state: system_derivatives(t, y_state, current_mw, Q, valve),
            t_span=t_span,
            y0=y,
            method='Radau',
            t_eval=[current_time + step]
        )
        
        # Extract the last time step safely
        y = sol.y[:, -1]
        
        # Evaluate for JSON output with clamps
        P_safe = max(y[0], 1.0)
        Vdw_safe = max(y[1], 0.0)
        phi_safe = max(0.0, min(1.0, y[2]))
        
        L = model.calculate_drum_level(Vdw_safe, phi_safe, P_safe)
        
        # Calculate next temperature using subcooled-aware helper
        current_T = calculate_dynamic_temperature(P_safe, Vdw_safe, Q, step, current_T)
        
        results.append({
            "time": i * step,
            "P": round(P_safe / 1e5, 2),
            "L": round(L, 3),
            "T": round(current_T, 1),
            "mw": round(current_mw, 2)
        })
        
        current_time += step
        
    return results

if __name__ == "__main__":
    try:
        # Expected args: P, Vdw, phi, mw, Q, valve, (optional) T_init
        if len(sys.argv) < 7:
            print(json.dumps({"error": "Insufficient arguments"}))
            sys.exit(1)
            
        args = [float(x) for x in sys.argv[1:7]]
        T_init = float(sys.argv[7]) if len(sys.argv) > 7 else None
        
        data = generate_timeseries(*args, T_init)
        print(json.dumps(data))
    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
