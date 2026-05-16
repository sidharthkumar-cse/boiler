import sys
import time
from pathlib import Path
repo_root = Path(__file__).parent.parent
sys.path.append(str(repo_root / "boiler-model"))
from simulation.solver_logic import predict_timeline, compute_initial_state

t0 = time.time()
Vdw_init, phi_init, L_init = compute_initial_state(25.0, 1.013e5, 1.5)
timeline = predict_timeline(
    P_init=1.013e5,
    Vdw_init=Vdw_init,
    phi_init=phi_init,
    m_w=0.0,
    Q=1000.0,
    valve_opening=0.0,
    T_init=25.0,
    n_points=10,
    step_seconds=60.0
)
t1 = time.time()

print(f"Time taken: {t1-t0:.3f} s")
print(f"Final temp: {timeline[-1]['T']:.1f}")
print("Timeline:", timeline)
