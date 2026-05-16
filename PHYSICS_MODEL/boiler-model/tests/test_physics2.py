import numpy as np
from scipy.integrate import solve_ivp
from engine.solver_logic import system_derivatives

P = 1.013e5 + 0.16e5
V_dw = 0.0044
phi = 0.005
cur_T_wall = 104.7 + 2

Q = 1000.0
# run ODE for 180 seconds
y0 = [P, V_dw, phi, cur_T_wall]
sol = solve_ivp(
    fun=lambda t, y: system_derivatives(t, y, 0.0, Q, 0.0),
    t_span=(0.0, 180.0),
    y0=y0,
    method='Radau',
)
print("P_initial =", y0[0])
print("P_final   =", sol.y[0, -1])
print("Delta P   =", sol.y[0, -1] - y0[0])
