from engine.solver_logic import run_continuous
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

boiler_twin = run_continuous(P_init=50e5, Vdw_init=10.0, phi_init=0.1, 
                             m_w=10.0, Q=2e7, valve_opening=1.0, dt=1.0)

print("--- Testing Continuous Boiler Engine ---")
for step in range(15):
    P_live, Vdw_live, phi_live, L_live, T_live = next(boiler_twin)
    print(f"Time {step:02d}s | Pressure: {P_live/1e5:5.2f} bar | Level: {L_live:4.2f} m | Temp: {T_live:5.1f} C")
print("--- Test Complete ---")
