import sys, os
sys.path.append(os.path.join(os.getcwd(), 'boiler-model'))
from simulation.solver_logic import predict_timeline
import json

P_abs = 1.01325 * 100000.0  # 0.0 bar gauge
Vdw_init = 0.00451       # 4.51 Liters
phi_init = 0.0           
m_w = 0.0
Q = 1000.0               # 1 kW heater
valve = 0.0              # Valve closed
T_init = 95.4           # Subcooled state

results = predict_timeline(
    P_init=P_abs, Vdw_init=Vdw_init, phi_init=phi_init,
    m_w=m_w, Q=Q, valve_opening=valve, T_init=T_init,
    n_points=10, step_seconds=60.0
)

print(f"{'Time (m)':<10} | {'T (°C)':<10} | {'P (bar abs)':<15}")
for r in results:
    p_bar = r['P'] / 100000.0
    print(f"t={r['t_min']}m      | {r['T']:.1f}      | {p_bar:.3f} bar")

