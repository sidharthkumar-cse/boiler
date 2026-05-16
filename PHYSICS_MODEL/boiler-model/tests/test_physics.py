import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.matrix_form import solve_system
P = 1.013e5 + 0.16e5
V_dw = 0.0044
phi = 0.005
m_w = 0.0
Q = 1000.0

# With valve closed
dP_dt_closed = solve_system(P, V_dw, phi, m_w, Q, 0.0)[0]
# With valve open
dP_dt_open = solve_system(P, V_dw, phi, m_w, Q, 1.0)[0]

print(f"dP/dt (Closed) = {dP_dt_closed} Pa/s")
print(f"dP/dt (Open)   = {dP_dt_open} Pa/s")
