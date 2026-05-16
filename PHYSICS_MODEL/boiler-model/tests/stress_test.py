import sys
import os
import numpy as np

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.solver_logic import predict_timeline, compute_initial_state
from physics import thermo_relations as thermo
from config import constants as const

def run_stress_test(name, P, Vdw, phi, T, mw, Q, valve):
    print(f"\n--- Scenario: {name} ---")
    print(f"Inputs: P={P/1e5:.2f}bar, Vdw={Vdw*1000:.1f}L, phi={phi:.3f}, T={T:.1f}C, Q={Q}W, valve={valve}")
    
    try:
        results = predict_timeline(P, Vdw, phi, mw, Q, valve, T_init=T, n_points=10, step_seconds=60)
        final = results[-1]
        print(f"Final State (t+10m): P={final['P']/1e5:.2f}bar, T={final['T']:.1f}C, L={final['L']*100:.1f}cm, phi={final['phi']:.3f}")
        print("[SUCCESS] Solver remained stable.")
        return True
    except Exception as e:
        print(f"[FAILED] Solver crashed: {e}")
        return False

def main():
    print("====================================================")
    print("   BOILER PHYSICS ENGINE - EXTREME STRESS TEST     ")
    print("====================================================")

    # 1. HEATER SURGE (10x Nominal Power)
    run_stress_test(
        "HEATER_SURGE (10kW)",
        P=1.013e5, Vdw=0.004, phi=0.0, T=95.0,
        mw=0.0, Q=10000.0, valve=0.0
    )

    # 2. DRY RUN (Critically Low Water)
    run_stress_test(
        "DRY_RUN (100ml Water)",
        P=1.013e5, Vdw=0.0001, phi=0.0, T=90.0,
        mw=0.0, Q=1000.0, valve=0.0
    )

    # 3. HIGH PRESSURE FLASHING
    run_stress_test(
        "FLASH_STEAM (10 bar -> Valve Open)",
        P=10e5, Vdw=0.004, phi=0.1, T=180.0,
        mw=0.0, Q=0.0, valve=1.0
    )

    # 4. OVERFILLED BOILER
    run_stress_test(
        "OVERFILLED (Drum at 98% Capacity)",
        P=1.013e5, Vdw=const.V_T * 0.98, phi=0.0, T=99.0,
        mw=0.0, Q=2000.0, valve=0.0
    )

    # 5. VACUUM START
    run_stress_test(
        "VACUUM_START (0.2 bar)",
        P=0.2e5, Vdw=0.004, phi=0.0, T=20.0,
        mw=0.0, Q=1000.0, valve=0.0
    )

if __name__ == "__main__":
    main()
