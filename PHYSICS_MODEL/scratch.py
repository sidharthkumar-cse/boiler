import sys
import os
import math
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), 'boiler-model')))

from core.coefficients import calculate_matrix_C, calculate_vector_D
from core.matrix_form import solve_system
import physics.void_fraction as void
import physics.thermo_relations as thermo
from config import constants as const
from engine.solver_logic import compute_initial_state

P_pa = 1.0884 * 1e5
T_cur = 66.85
V_cur_L = 4.199

rho_w_curr = thermo.get_rho_w_subcooled(P_pa, T_cur)
water_mass_kg = max(0.5, V_cur_L * (rho_w_curr / 1000.0))

Vdw, phi, _ = compute_initial_state(T_cur, P_pa, water_mass_kg)
m_w = 0.0
Q_w = 1000.0
valve_op = 0.0

C_mat = calculate_matrix_C(P_pa, Vdw, phi)
D_vec = calculate_vector_D(P_pa, Vdw, phi, m_w, Q_w, valve_op)
X = solve_system(P_pa, Vdw, phi, m_w, Q_w, valve_op)
print("X:", X)
