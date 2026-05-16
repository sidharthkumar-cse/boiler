from engine.solver_logic import predict_forward
from config import constants as const
from utils.hardware import get_live_snapshot

# 1. Grab LIVE results from Arduino (with fallback to defaults)
live = get_live_snapshot()

# 2. Define initial states (Synchronized with hardware)
P_init = live["P"] * 1e5  # convert bar to Pa
Vdw_init = 0.003         # 3 Liters (Tabletop scale)
phi_init = 0.1           # 10% void fraction

# 3. Define inputs (Synchronized with hardware)
m_w = live["mw"]         # feed water (kg/s)
valve_opening = live["Kv"] 
Q = live["Q"]            # Heat (Watts)

# Prediction horizon
horizon = 300.0 # 5 minutes
dt = 1.0

print(f"Initial State: P={P_init/1e5:.2f} bar, L={Vdw_init/const.A_D:.2f} m")
print(f"Predicting {horizon}s into the future...")

# Run prediction model
P_final, Vdw_final, phi_final, L_final, T_final, T_wall_final = predict_forward(
    P_init, Vdw_init, phi_init, m_w, Q, valve_opening, T_init=live["T"], duration=horizon, dt=dt
)

# Output requested predictions
print("\nOutput Prediction (t+Δt):")
print(f"P({horizon}s): {P_final/1e5:.2f} bar")
print(f"L({horizon}s): {L_final:.2f} m")
print(f"T({horizon}s): {T_final:.1f} °C")
print(f"T_wall({horizon}s): {T_wall_final:.1f} °C")
