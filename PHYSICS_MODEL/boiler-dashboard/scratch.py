import sys
sys.path.append("/Users/aryanchauhan/Developer/Physics-based-model/boiler-model")
from engine.kalman_filter import BoilerEKF
from engine.solver_logic import predict_forward, compute_initial_state

ekf = BoilerEKF()
ekf.set_physics_model(predict_forward, compute_initial_state)

print(f"Initial: {ekf.x}")
ekf.predict_and_update(z_T=25.0, z_P_abs=1.013, z_V_L=4.5, Q_watts=0.0, m_w_kgs=0.0, valve_opening=0.0, water_mass_kg=4.5)
print(f"Step 1: {ekf.x}")
import time
time.sleep(2)
ekf.predict_and_update(z_T=25.0, z_P_abs=1.013, z_V_L=4.5, Q_watts=0.0, m_w_kgs=0.0, valve_opening=0.0, water_mass_kg=4.5)
print(f"Step 2: {ekf.x}")
