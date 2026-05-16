import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'boiler-model'))
from simulation.solver_logic import predict_timeline

timeline = predict_timeline(
    P_init=2.05e5, # 1.04 bar gauge
    Vdw_init=0.00435, # 4.35 L
    phi_init=0.0, 
    m_w=0.0, 
    Q=1000.0, 
    valve_opening=0.0, 
    T_init=108.6, 
    n_points=3, 
    step_seconds=60.0
)
for p in timeline:
    print(f"t={p['t_min']}m: P={p['P']/1e5:.3f} bar_abs, T={p['T']:.2f} C")
