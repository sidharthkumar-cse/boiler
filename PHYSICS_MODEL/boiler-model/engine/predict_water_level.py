#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════
  Water Level Prediction During Heating
  ─────────────────────────────────────
  Boiler Specs (from float_switch HIGH state):
    • Water volume:   4.2 L  (at float_high)
    • Water height:   16.5 cm
    • Total height:   24.0 cm
    • Steam space:    7.5 cm  (24 - 16.5)
    • Diameter:       18.0 cm
    • Heater:         1 kW immersion
  
  Three physical effects change the apparent water level:
  
    1. THERMAL EXPANSION (25°C → 100°C):
       Water density drops 997→958 kg/m³ → volume grows ~4%
       → Level rises by ~0.66 cm
  
    2. SWELL EFFECT (bubbles in liquid column):
       Void fraction φ causes apparent level = L / (1−φ)
       → At φ=5%, level rises +0.8 cm on top of expansion
       → At φ=20%, level rises +4 cm (dangerous!)
  
    3. STEAM CONSUMPTION (sustained boiling):
       Water mass is converted to steam and exits through valve
       → Level drops slowly over time (evaporative loss)
═══════════════════════════════════════════════════════════════════════
"""
import sys
import os
import numpy as np

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from config import constants as const
from physics import thermo_relations as thermo
from engine.solver_logic import predict_timeline, compute_initial_state
from iapws import IAPWS97

# ── Boiler Hardware Constants ──
INITIAL_WATER_LITERS = 4.2
INITIAL_TEMP_C = 25.0
HEATER_POWER_W = 1000.0   # 1 kW


def get_water_density(T_celsius, P_pa=101325.0):
    """
    Get LIQUID water density at given temperature and pressure.
    
    Critical fix: At the saturation boundary (e.g. 100°C at 1 atm),
    IAPWS97(T, P) is ambiguous and may return steam density (~0.6 kg/m³)
    instead of liquid density (~958 kg/m³). We detect this and force
    saturated liquid (x=0) when T ≥ T_sat.
    """
    T_K = T_celsius + 273.15
    P_MPa = P_pa / 1e6
    try:
        # Check if we're at or above saturation
        T_sat_K = IAPWS97(P=P_MPa, x=0).T  # Saturation temperature
        if T_celsius >= (T_sat_K - 273.15 - 0.5):
            # At or above saturation — use saturated liquid density explicitly
            sat_liquid = IAPWS97(P=P_MPa, x=0)
            return sat_liquid.rho
        else:
            # Subcooled liquid — safe to use T,P lookup
            water = IAPWS97(T=T_K, P=P_MPa)
            return water.rho
    except:
        # Fallback empirical correlation for liquid water
        return (999.84 + 16.945 * T_celsius
                - 7.987e-3 * T_celsius**2
                - 46.17e-6 * T_celsius**3)


def predict_water_level():
    """
    Full prediction from cold start (25°C) to sustained boiling.
    Uses the real physics engine for the two-phase regime.
    """
    print("═" * 70)
    print("  WATER LEVEL PREDICTION — Float Switch HIGH (4.2L)")
    print("═" * 70)
    print()

    # ── Boiler Geometry Verification ──
    A = const.A_D
    print(f"  Boiler Diameter:     {const.D_DRUM*100:.1f} cm")
    print(f"  Total Height:        {const.H_DRUM*100:.1f} cm")
    print(f"  Cross Section Area:  {A*1e4:.2f} cm²")
    print(f"  Total Volume:        {const.V_T*1000:.2f} L")
    print()
    print(f"  Initial Water:       {INITIAL_WATER_LITERS} L at {INITIAL_TEMP_C}°C")
    print(f"  Water Height:        {const.H_WATER_MAX*100:.1f} cm")
    print(f"  Steam Space:         {const.H_STEAM*100:.1f} cm")
    print(f"  Heater Power:        {HEATER_POWER_W/1000:.1f} kW")
    print()

    # ── Initial mass ──
    rho_init = get_water_density(INITIAL_TEMP_C)
    water_mass = INITIAL_WATER_LITERS / 1000.0 * rho_init  # kg
    print(f"  Initial Water Mass:  {water_mass:.3f} kg")
    print(f"  Initial Density:     {rho_init:.1f} kg/m³")
    print()

    # ══════════════════════════════════════════════════════════════
    #  PHASE 1: Subcooled Heating (25°C → 100°C)
    #  Only thermal expansion — no steam, no swell
    # ══════════════════════════════════════════════════════════════
    print("─" * 70)
    print("  PHASE 1: Subcooled Heating (Thermal Expansion)")
    print("─" * 70)
    print()
    print(f"  {'Time':>8}  {'Temp':>8}  {'ρ_water':>10}  {'Volume':>10}  {'Level':>10}  {'ΔLevel':>10}")
    print(f"  {'(min)':>8}  {'(°C)':>8}  {'(kg/m³)':>10}  {'(L)':>10}  {'(cm)':>10}  {'(cm)':>10}")
    print(f"  {'─'*8}  {'─'*8}  {'─'*10}  {'─'*10}  {'─'*10}  {'─'*10}")

    # Thermal mass: water + metal vessel
    CP_WATER = 4186.0  # J/(kg·K)
    thermal_mass = (water_mass * CP_WATER) + (const.M_M * const.C_M)
    
    L_cold = const.H_WATER_MAX  # 16.5 cm starting level
    T_sat = 100.0  # °C at atmospheric
    
    # Time to reach boiling
    t_to_boil = (T_sat - INITIAL_TEMP_C) * thermal_mass / HEATER_POWER_W
    
    print(f"  Thermal Mass:        {thermal_mass:.0f} J/K")
    print(f"  Time to Boiling:     {t_to_boil:.0f} s = {t_to_boil/60:.1f} min")
    print()
    
    subcooled_data = []
    for t_sec in np.arange(0, t_to_boil + 30, 30):
        t_sec = min(t_sec, t_to_boil)
        T = INITIAL_TEMP_C + (HEATER_POWER_W * t_sec) / thermal_mass
        T = min(T, T_sat)
        rho = get_water_density(T)
        V = water_mass / rho  # m³
        L = V / A             # m
        dL = (L - L_cold) * 100  # cm change
        t_min = t_sec / 60.0
        
        subcooled_data.append({
            't_min': t_min, 'T': T, 'rho': rho,
            'V_L': V * 1000, 'L_cm': L * 100, 'dL_cm': dL
        })
        
        print(f"  {t_min:>8.1f}  {T:>8.1f}  {rho:>10.1f}  {V*1000:>10.3f}  {L*100:>10.2f}  {dL:>+10.2f}")
        
        if T >= T_sat:
            break

    print()
    print(f"  ➜ At boiling point: water expanded from {INITIAL_WATER_LITERS:.3f} L → {subcooled_data[-1]['V_L']:.3f} L")
    print(f"  ➜ Level rose by {subcooled_data[-1]['dL_cm']:.2f} cm (thermal expansion only)")
    print()

    # ══════════════════════════════════════════════════════════════
    #  PHASE 2: Two-Phase Boiling (Steam Production + Swell)
    #  Using the full ODE solver with corrected geometry
    # ══════════════════════════════════════════════════════════════
    print("─" * 70)
    print("  PHASE 2: Boiling — Steam Production & Swell Effect")
    print("─" * 70)
    print()

    # Initial conditions at boiling point
    P_atm = 1.013e5  # Pa
    Vdw_boil = water_mass / get_water_density(T_sat, P_atm)  # m³
    phi_boil = 0.005  # Small initial void from nucleation
    
    print(f"  Starting ODE from: T=100°C, P=1.013 bar, Vdw={Vdw_boil*1000:.3f} L, φ={phi_boil}")
    print()

    # Run 20-minute prediction (valve closed, no inflow)
    try:
        timeline = predict_timeline(
            P_init=P_atm,
            Vdw_init=Vdw_boil,
            phi_init=phi_boil,
            m_w=0.0,          # No inlet water
            Q=HEATER_POWER_W, # 1 kW heater
            valve_opening=0.0, # Valve closed (sealed boiler)
            T_init=T_sat,
            n_points=20,      # 20 minutes
            step_seconds=60.0  # 1-minute steps
        )
    except Exception as e:
        print(f"  ❌ Solver error: {e}")
        return

    print(f"  {'Time':>8}  {'Temp':>8}  {'P_gauge':>10}  {'V_water':>10}  {'φ (void)':>10}  {'Level':>10}  {'ΔLevel':>10}")
    print(f"  {'(min)':>8}  {'(°C)':>8}  {'(bar)':>10}  {'(L)':>10}  {'(%)':>10}  {'(cm)':>10}  {'(cm)':>10}")
    print(f"  {'─'*8}  {'─'*8}  {'─'*10}  {'─'*10}  {'─'*10}  {'─'*10}  {'─'*10}")

    # t=0 boiling start
    L_boil_start = Vdw_boil / A / (1.0 - phi_boil)
    t_offset = t_to_boil / 60.0  # minutes offset from cold start
    print(f"  {t_offset:>8.1f}  {T_sat:>8.1f}  {'0.000':>10}  {Vdw_boil*1000:>10.3f}  {phi_boil*100:>10.2f}  {L_boil_start*100:>10.2f}  {(L_boil_start - L_cold)*100:>+10.2f}")

    for pt in timeline:
        P_gauge = max(0, (pt['P'] / 1e5) - 1.013)
        L_cm = pt['L'] * 100
        dL = L_cm - (L_cold * 100)
        t_total = t_offset + pt['t_min']
        
        print(f"  {t_total:>8.1f}  {pt['T']:>8.1f}  {P_gauge:>10.3f}  {pt['Vdw']*1000:>10.3f}  {pt['phi']*100:>10.2f}  {L_cm:>10.2f}  {dL:>+10.2f}")

    print()
    
    # ══════════════════════════════════════════════════════════════
    #  SUMMARY
    # ══════════════════════════════════════════════════════════════
    final = timeline[-1]
    L_final = final['L'] * 100
    P_final_gauge = max(0, (final['P'] / 1e5) - 1.013)
    
    print("═" * 70)
    print("  SUMMARY — Water Level Changes During Heating")
    print("═" * 70)
    print()
    print(f"  COLD START (float_high):")
    print(f"    Water Level:    {L_cold*100:.1f} cm  ({INITIAL_WATER_LITERS} L)")
    print(f"    Temperature:    {INITIAL_TEMP_C}°C")
    print(f"    Steam Space:    {const.H_STEAM*100:.1f} cm")
    print()
    print(f"  AT BOILING POINT ({t_to_boil/60:.1f} min):")
    print(f"    Water Level:    {subcooled_data[-1]['L_cm']:.2f} cm  (+{subcooled_data[-1]['dL_cm']:.2f} cm from expansion)")
    print(f"    Temperature:    100°C")
    print(f"    Remaining Space: {const.H_DRUM*100 - subcooled_data[-1]['L_cm']:.2f} cm")
    print()
    print(f"  AFTER {int(timeline[-1]['t_min'])} MIN BOILING ({t_offset + timeline[-1]['t_min']:.1f} min total):")
    print(f"    Water Level:    {L_final:.2f} cm  ({L_final - L_cold*100:+.2f} cm from cold start)")
    print(f"    Temperature:    {final['T']:.1f}°C")
    print(f"    Pressure:       {P_final_gauge:.3f} bar (gauge)")
    print(f"    Void Fraction:  {final['phi']*100:.2f}%")
    print(f"    Remaining Space: {const.H_DRUM*100 - L_final:.2f} cm")
    print()
    
    # Safety check
    if L_final > const.H_DRUM * 100:
        print("  ⚠️  WARNING: Water level exceeds drum height — risk of carryover!")
    elif L_final > (const.H_DRUM * 100 - 2):
        print("  ⚠️  CAUTION: Water level within 2 cm of top — monitor closely!")
    else:
        print(f"  ✅  SAFE: {const.H_DRUM*100 - L_final:.1f} cm headroom remaining in steam space")
    
    print()
    print("═" * 70)


if __name__ == "__main__":
    predict_water_level()
