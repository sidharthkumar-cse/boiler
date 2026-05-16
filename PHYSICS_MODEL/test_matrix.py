import sys, os
sys.path.append(os.path.join(os.getcwd(), 'boiler-model'))
from model.matrix_form import solve_system
import numpy as np

P = 2.0e5 # 2.0 bar absolute
V_dw = 0.005 # 5 Liters
phi = 0.1 # 10% void fraction
m_w = 0.0 # No feed water
Q_fluid = 1000.0 # 1kW heater
valve_opening = 0.0 # Valve fully closed

# Solve 
X = solve_system(P, V_dw, phi, m_w, Q_fluid, valve_opening)

print("dP/dt (Pa/s):", X[0])
print("dV_dw/dt (m^3/s):", X[1])
print("dphi/dt (1/s):", X[2])
print("m_g (kg/s):", X[3])
