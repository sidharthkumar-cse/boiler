import sys
import os
from pathlib import Path
repo_root = Path(__file__).parent.absolute()
sys.path.append(str(repo_root / "boiler-model"))
from engine.solver_logic import predict_timeline, compute_initial_state
import physics.thermo_relations as thermo

P_init_pa = 1.2e5
water_mass_kg = 4.2 * (997 / 1000.0)
T_init = thermo.get_T_sat(P_init_pa) - 273.15 + 0.1 # slightly above saturation to trigger boiling
Q = 1000.0
valve_opening = 0.0
m_w = 0.0

Vdw_init, phi_init, L_init = compute_initial_state(T_init, P_init_pa, water_mass_kg)
print(f"Vdw_init={Vdw_init}, phi_init={phi_init}, L_init={L_init}, T_init={T_init}")

timeline = predict_timeline(
    P_init=P_init_pa,
    Vdw_init=Vdw_init,
    phi_init=phi_init,
    m_w=m_w,
    Q=Q,
    valve_opening=valve_opening,
    T_init=T_init,
    n_points=5,
    step_seconds=60.0
)

for pt in timeline:
    print(pt)
