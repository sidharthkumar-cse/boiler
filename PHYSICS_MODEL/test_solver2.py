import sys
sys.path.append('boiler-model')
from engine.solver_logic import predict_forward
import numpy as np

P_init = 1.697e5
Vdw_init = 0.004199
phi_init = 0.001
m_w = 0.03 / 60.0
Q = 1000.0
valve_opening = 0.0
T_init = 117.91

res = predict_forward(P_init, Vdw_init, phi_init, m_w, Q, valve_opening, T_init=T_init, duration=60.0)
print(f"Final Vdw: {res[1]}")
print(f"Final P: {res[0]}")
