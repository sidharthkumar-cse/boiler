import sys
sys.path.append("/Users/aryanchauhan/Developer/Physics-based-model/boiler-model")
from engine.solver_logic import predict_forward, compute_initial_state
from physics import thermo_relations as thermo

V_cur_L = 4.5
T_cur = 25.0
P_init_pa = 1.013e5

rho_w_curr = thermo.get_rho_w_subcooled(P_init_pa, T_cur)
print(f"rho_w_curr = {rho_w_curr}")
water_mass_kg = max(0.5, V_cur_L * (rho_w_curr / 1000.0))
print(f"water_mass_kg = {water_mass_kg}")

Vdw, phi, L = compute_initial_state(T_cur, P_init_pa, water_mass_kg)
print(f"Vdw = {Vdw}, phi = {phi}, L = {L}")

P_f, Vdw_f, phi_f, L_f, T_f, _ = predict_forward(
    P_init=P_init_pa,
    Vdw_init=Vdw,
    phi_init=phi,
    m_w=0.0,
    Q=0.0,
    valve_opening=0.0,
    T_init=T_cur,
    duration=2.0
)
print(f"Vdw_f = {Vdw_f}")
print(f"Vdw_f * 1000.0 = {Vdw_f * 1000.0}")
