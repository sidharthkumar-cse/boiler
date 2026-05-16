import sys, os
sys.path.append(os.path.join(os.getcwd(), 'boiler-model'))
from engine.solver_logic import predict_timeline
import json

# Boiler initial state 
P_abs = 2.05 * 100000.0  # 1.04 bar gauge
Vdw_init = 0.00435       # 4.35 Liters
phi_init = 0.0           
m_w = 0.0
Q = 1000.0               # 1 kW heater
valve = 0.0              # Valve closed
T_init = 108.6           # Subcooled state

print("==== 10-Minute Predictive Forecast ====")
results = predict_timeline(
    P_init=P_abs,
    Vdw_init=Vdw_init,
    phi_init=phi_init,
    m_w=m_w,
    Q=Q,
    valve_opening=valve,
    T_init=T_init,
    n_points=10,
    step_seconds=60.0
)

from physics import thermo_relations as thermo

# Print nice table format
print(f"{'Time (m)':<10} | {'T (°C)':<10} | {'P (bar abs)':<15} | {'Phase'}")
print("-" * 55)

T_prev = T_init
for r in results:
    dt_val = r['T'] - T_prev
    p_bar = r['P'] / 100000.0
    
    # Dynamically determine phase
    T_sat = thermo.get_T_sat(r['P']) - 273.15
    phase = "Saturated Boiling" if r['T'] >= T_sat - 0.1 else "Subcooled Liquid"
    
    print(f"t={r['t_min']}{'m':<7} | {r['T']:.1f}{' (+'+str(round(dt_val, 1))+')' if dt_val > 0 else '':<5} | {p_bar:.3f} bar        | {phase}")
    T_prev = r['T']

