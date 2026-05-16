import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'boiler-model'))
from simulation.solver_logic import predict_timeline

timeline = predict_timeline(
    P_init=1.013e5, 
    Vdw_init=0.0045, 
    phi_init=0.0, 
    m_w=0.0, 
    Q=1000.0, 
    valve_opening=0.0, 
    T_init=25.0, 
    n_points=10, 
    step_seconds=60.0
)
for p in timeline:
    print(f"t={p['t_min']}m: P={p['P']/1e5:.3f} bar_abs, T={p['T']:.2f} C")
