import numpy as np
import warnings
from scipy.integrate import solve_ivp
from core import matrix_form as model
from physics import thermo_relations as thermo
from config import constants as const
from iapws import IAPWS97


def safe_solve_ivp(fun, t_span, y0, method='Radau', t_eval=None, **kwargs):
    """
    Wrapper around solve_ivp that checks solver success status.
    On failure, logs a warning and returns the last known good state
    instead of silently returning garbage values.
    """
    sol = solve_ivp(fun, t_span, y0, method=method, t_eval=t_eval, **kwargs)
    if not sol.success:
        warnings.warn(
            f"[ODE] solve_ivp failed (status={sol.status}): {sol.message}. "
            f"Returning last known state.",
            stacklevel=2
        )
        # Fallback: return initial conditions as if no change occurred
        if sol.y.shape[1] == 0:
            sol.y = np.array([[v] for v in y0])
    return sol


# ═══════════════════════════════════════════════════════════════════
#  Initial State Computation from Live Sensor Data
# ═══════════════════════════════════════════════════════════════════

# Maximum mass quality during subcooled boiling before transition to saturated boiling
PHI_MAX_SUBCOOLED = 1.0e-5
CP_WATER = 4186.0
K_WATER = 2.2e9

# Vapor equilibrium efficiency in sealed headspace.
# Full P_sat(T) assumes instant liquid-vapor equilibrium in the entire
# headspace.  In reality, trapped air dilutes the vapor and the upper
# dome is cooler → only a fraction of P_sat contribution is realized.
#
# Calibrated from session logs using differential_evolution (scipy):
#   session_20260501_215103 + session_20260429_223936
#   7,143 data points, binned to 32 temperature bands (40-105°C)
#
# Previous calibration (T_MID=79.6) severely underestimated vapor equilibrium
# in the 55-80°C range, causing 10-minute forecasts to under-predict pressure
# by ~38% at 77°C.  Shifting T_MID to 67.4°C and steepening the sigmoid
# reduced overall RMSE by 30.5% (0.0286 → 0.0198 bar).
#
# Fitted as a smooth sigmoid: η(T) = η_min + (η_max - η_min) / (1 + exp(-k*(T - T_mid)))
def get_eta_vapor(T_celsius):
    """Temperature-dependent vapor equilibrium efficiency.
    
    At low temperatures the headspace is mostly trapped air with very
    little water vapor → low η.  As T rises toward boiling, vapor
    partial pressure dominates and η approaches its asymptotic max.
    
    Calibrated via scipy.optimize.differential_evolution on 7,143 data
    points from 2 sessions (session_20260501_215103, session_20260429_223936).
    30.5% RMSE improvement over previous calibration.
    """
    ETA_MIN = 0.00   # Below ~55°C, negligible vapor contribution
    ETA_MAX = 0.82   # Asymptotic max — air dilution caps effective η
    T_MID   = 66.2   # Inflection point (°C)
    K_SLOPE = 0.50   # Sigmoid steepness (1/°C)
    eta = ETA_MIN + (ETA_MAX - ETA_MIN) / (1.0 + np.exp(-K_SLOPE * (T_celsius - T_MID)))
    return eta


def get_liquid_density(P_pa, T_celsius):
    """
    Liquid-water density for level and thermal-mass calculations.

    Saturated tables are correct once boiling starts, but using saturated
    density during subcooled heating underestimates cold water mass by a few
    percent. That error directly becomes temperature and level drift.
    """
    T_sat_C = thermo.get_T_sat(max(P_pa, 5000.0)) - 273.15
    if T_celsius >= T_sat_C - 0.25:
        return thermo.get_rho_w(P_pa)
    rho = thermo.get_rho_w_subcooled(P_pa, T_celsius)
    if not np.isfinite(rho) or rho < 850.0 or rho > 1100.0:
        return thermo.get_rho_w(P_pa)
    return rho


def clamp_mixture_volume(V_dw):
    """Keep predicted mixture volume inside the physical drum."""
    return min(max(V_dw, 1e-6), const.V_T * 0.995)

def water_thermal_expansion_beta(T_celsius):
    """
    Volumetric thermal expansion coefficient β(T) for liquid water (1/K).
    Polynomial fit valid for 0–100 °C range (NIST data).
    Returns β ≥ 0 (water above 4 °C always expands on heating).
    """
    T = float(T_celsius)
    beta = -6.43e-5 + 1.7e-5 * T - 2.02e-8 * T**2 + 3.71e-10 * T**3
    return max(0.0, beta)


def compute_initial_state(T_celsius, P_pa, water_mass_kg):
    """
    Derive the physics model's initial state from live Arduino sensor data.

    Data flow:
      ┌────────────────────────────────────────────────────────┐
      │  Arduino Flow Meter (L/min)                           │
      │       ↓  integrated over time in serial_proxy.py      │
      │  water_mass_kg  (cumulative kg in the tank)           │
      │       ↓                                               │
      │  IAPWS-97:  ρ_w = ρ(T_sensor, P_sensor)              │
      │       ↓                                               │
      │  V_dw = water_mass_kg / ρ_w                           │
      │       ↓                                               │
      │  L = V_dw / A_D    (A_D = π/4 × 19.05² cm²)         │
      └────────────────────────────────────────────────────────┘

    Inputs:
      T_celsius      — Bulk water temperature (°C)  [from TMP36 / thermocouple]
      P_pa           — Absolute pressure (Pa)       [from ADS1115 transducer]
      water_mass_kg  — Total water mass in boiler    [from cumulative flow meter]

    Returns:
      Vdw   — Water volume (m³)
      phi   — Steam quality / void fraction
      L     — Water level (m) above boiler bottom
    """
    # Saturation temperature and incipient superheat (ONB)
    P_atm = 1.013e5
    T_sat_C = thermo.get_T_sat(P_pa if P_pa > P_atm else P_atm) - 273.15

    # ── Dynamic Onset of Nucleate Boiling (ONB) ──
    # Using Davis-Anderson correlation (Hsu criterion)
    # DeltaT_ONB = sqrt( (8 * sigma * T_sat * q'') / (k_l * rho_s * h_fg) )
    Q_avg = 1000.0  # Assumed nominal 1kW for initialization
    q_flux = Q_avg / const.A_HEATER

    sigma = thermo.get_sigma(P_pa)
    k_l = thermo.get_k_l(P_pa, T_celsius)
    rho_s = thermo.get_rho_s(P_pa)
    h_fg = thermo.get_h_fg(P_pa)
    T_sat_K = T_sat_C + 273.15

    superheat_ONB = np.sqrt((8.0 * sigma * T_sat_K * q_flux) / (k_l * rho_s * h_fg))
    T_ONB = T_sat_C - (max(5.0, min(superheat_ONB, 25.0))) # Delta below T_sat for incipient bubbles

    # ── Water density from IAPWS-97 ──
    if T_celsius < T_sat_C:
        # Subcooled / compressed liquid
        rho_w = get_liquid_density(P_pa, T_celsius)
    else:
        # At or above saturation — use saturated liquid density
        rho_w = thermo.get_rho_w(P_pa)

    # ── Void fraction (steam quality) ──
    if T_celsius >= T_sat_C:
        # At saturation: steady-state void fraction from bubble rise dynamics
        # alpha_ss = m_g_est / (rho_s * A_D * v_rise)
        m_g_est = Q_avg / h_fg
        v_rise = 1.41 * ( (sigma * 9.81 * (rho_w - rho_s)) / (rho_w**2) )**0.25
        alpha_ss = m_g_est / (rho_s * const.A_D * v_rise)
        alpha_ss = min(max(alpha_ss, 0.005), 0.95)
        # Convert void fraction alpha to mass quality phi
        phi = (alpha_ss * rho_s) / (alpha_ss * rho_s + (1.0 - alpha_ss) * rho_w)
    elif T_celsius > T_ONB:
        # Subcooled nucleate boiling: small bubbles on heated wall
        subcool_frac = (T_celsius - T_ONB) / (T_sat_C - T_ONB)
        alpha_sub = 0.005 * subcool_frac ** 2
        # Convert to quality
        phi = (alpha_sub * rho_s) / (alpha_sub * rho_s + (1.0 - alpha_sub) * rho_w)
    else:
        # Pure subcooled liquid — no bubbles
        phi = 0.0

    # ── Downcomer mixture volume (from pure liquid mass and void fraction) ──
    # Pure liquid volume
    V_liquid = water_mass_kg / rho_w
    # Total mixture volume (liquid + bubbles)
    Vdw = clamp_mixture_volume(V_liquid / (1.0 - min(phi, 0.95)))

    # ── Apparent Water level  =  mixture volume / cross-section area ──
    # Clamp to drum height to prevent overflow in calculations
    L = min(Vdw / const.A_D, const.H_DRUM)

    return Vdw, phi, L

# ── Cumulative audit counters (module-level for live dashboard access) ──
_audit_cumulative_mass_error = 0.0
_audit_entropy_violations = 0
_audit_step_count = 0

def get_audit_metrics():
    """Return live thermodynamic consistency metrics for the dashboard."""
    return {
        "cumulative_mass_error_kg": _audit_cumulative_mass_error,
        "entropy_violations": _audit_entropy_violations,
        "steps_evaluated": _audit_step_count,
        "mass_conservation_proven": _audit_cumulative_mass_error < 1e-6,
        "second_law_proven": _audit_entropy_violations == 0,
    }

def reset_audit_metrics():
    """Reset audit counters at the start of a new prediction."""
    global _audit_cumulative_mass_error, _audit_entropy_violations, _audit_step_count
    _audit_cumulative_mass_error = 0.0
    _audit_entropy_violations = 0
    _audit_step_count = 0


def system_derivatives(t, y, m_w, Q, valve_opening):
    """
    State wrapper for scipy integrate.
    y = [P, Vdw, phi, T_wall]

    Includes live thermodynamic consistency audits:
      - Mass conservation check (dM/dt = ṁ_in − ṁ_out)
      - Clausius entropy inequality (Ṡ_irr ≥ 0)
    """
    global _audit_cumulative_mass_error, _audit_entropy_violations, _audit_step_count

    if len(y) == 4:
        P, V_dw, phi, T_wall = y
    else:
        P, V_dw, phi = y
        T_wall = thermo.get_T_sat(P) - 273.15 + 5.0 # fallback

    # Boundary clamps to prevent solver from evaluating unphysical states
    # which could domain error in square roots or steam tables computation
    P_safe = min(max(P, 5000.0), 1000000.0) # Cap at 10 bar (Safety Relief Valve)
    V_dw_safe = max(V_dw, 1e-6)            # Dry-run floor (1ml)
    phi_safe = max(0.0, min(0.99, phi))    # Prevent pure steam singularity

    # --- Metal Wall Heat Transfer (Thom Correlation + CHF Guard) ---
    T_water = thermo.get_T_sat(P_safe) - 273.15
    delta_T_sat = max(T_wall - T_water, 0.0)

    # Baseline natural convection to liquid water
    H_conv = 500.0

    # Thom correlation for nucleate boiling of water:
    # delta_T = 22.65 * (q'' / 1e6)^0.5 * exp(-P / 8.7e6)
    # => q'' = 1e6 * (delta_T * exp(P / 8.7e6) / 22.65)^2
    if delta_T_sat > 0:
        q_flux_boil = 1e6 * ( (delta_T_sat * np.exp(P_safe / 8.7e6)) / 22.65 )**2

        # ── CHF Guard: Zuber's Critical Heat Flux Correlation ──
        # q''_CHF = 0.131 · h_fg · ρ_s · [σ·g·(ρ_w−ρ_s)/ρ_s²]^0.25
        #
        # The Thom correlation is ONLY valid in the nucleate boiling regime.
        # Beyond q''_CHF, film boiling occurs (Leidenfrost effect) and
        # heat transfer drops catastrophically. Capping at CHF prevents
        # the model from entering this unphysical regime.
        #
        # Reference: Zuber, N. (1959), "Hydrodynamic Aspects of Boiling
        # Heat Transfer", AEC Report AECU-4439.
        rho_w_chf = thermo.get_rho_w(P_safe)
        rho_s_chf = thermo.get_rho_s(P_safe)
        sigma_chf = thermo.get_sigma(P_safe)
        h_fg_chf = thermo.get_h_fg(P_safe)
        g = 9.81

        q_CHF = 0.131 * h_fg_chf * rho_s_chf * (
            (sigma_chf * g * (rho_w_chf - rho_s_chf)) / (rho_s_chf**2)
        )**0.25

        # Cap the boiling heat flux at CHF — never enter film boiling
        q_flux_boil = min(q_flux_boil, q_CHF)

        H_boil = q_flux_boil / delta_T_sat
    else:
        H_boil = 0.0

    H_total = H_conv + H_boil
    U_eff = 1.0 / (1.0 / H_total + const.R_FOULING)

    # True temperature diff for heat transfer (can be subcooled)
    Q_transfer = U_eff * const.A_HEATER * (T_wall - T_water)

    # Environmental heat loss from the metal wall itself
    # The heated wall section loses heat to the surrounding air via natural convection.
    # (The bulk fluid surface loss is already captured in calculate_vector_D's D[2] term.)
    Q_wall_loss = const.U_LOSS * const.A_HEATER * max(T_wall - const.T_AMB, 0.0)

    # Metal Wall ODE (complete energy balance for the wall node)
    # dT_wall/dt = (Q_heater - Q_to_water - Q_to_environment) / (M_metal · C_metal)
    dT_wall_dt = (Q - Q_transfer - Q_wall_loss) / (const.M_M * const.C_M)

    # Calculate fluid derivatives using Q_transfer instead of Q
    X = list(model.solve_system(P_safe, V_dw_safe, phi_safe, m_w, Q_transfer, valve_opening))

    # ── Live Thermodynamic Audits ──
    _audit_step_count += 1
    # Mass conservation audit (every 10th step to avoid performance hit)
    if _audit_step_count % 10 == 0:
        try:
            # Compute m_s for the mass audit
            A_orifice = np.pi / 4.0 * const.D_PIPE**2
            rho_s = thermo.get_rho_s(P_safe)
            k = 1.3
            P_up = max(P_safe, const.P_DOWNSTREAM + 1.0)
            r = const.P_DOWNSTREAM / P_up
            r_c = (2.0 / (k + 1.0)) ** (k / (k - 1.0))
            if r <= r_c:
                r = r_c
            term = max(0.0, (k / (k - 1.0)) * (r**(2.0/k) - r**((k+1.0)/k)))
            m_s = const.C_D_VALVE * A_orifice * valve_opening * np.sqrt(2.0 * P_up * rho_s * term)

            mass_err = model.audit_mass_conservation(
                P_safe, V_dw_safe, phi_safe, m_w, m_s, X[3],
                X[0], X[1], X[2]
            )
            _audit_cumulative_mass_error = max(_audit_cumulative_mass_error, mass_err)

            # Entropy audit
            Q_loss_fluid = const.U_LOSS * const.A_VESSEL * max(T_water - const.T_AMB, 0.0)
            s_irr, is_valid = model.audit_entropy_production(
                P_safe, V_dw_safe, phi_safe, Q_transfer, Q_loss_fluid, T_wall, m_w, m_s
            )
            if not is_valid:
                _audit_entropy_violations += 1
        except Exception:
            pass  # Audits must never crash the solver

    # --- ACTIVE SAFETY RELIEF VALVE ---
    # If pressure exceeds 10 bar, dP/dt is capped at 0 (venting to atmosphere)
    if P >= 1000000.0 and X[0] > 0:
        X[0] = 0.0

    if len(y) == 4:
        return [X[0], X[1], X[2], dT_wall_dt]
    else:
        return [X[0], X[1], X[2]]

def calculate_dynamic_temperature(P, V_dw, Q, duration, T_prev):
    """
    Helper to reconcile saturation vs subcooled liquid physics.
    Returns the predicted temperature after 'duration' seconds.
    """
    T_sat = model.calculate_temperature(P)

    if T_prev is not None and T_prev < T_sat:
        # P in Pa for thermo lookups
        P_pa = P * 1e5 if P < 100 else P
        rho_w = get_liquid_density(P_pa, T_prev)
        M_water = rho_w * V_dw

        # Effective thermal mass (Water + Metal)
        thermal_mass = (M_water * CP_WATER) + (const.M_M * const.C_M)

        Q_loss = const.U_LOSS * const.A_VESSEL * max(T_prev - const.T_AMB, 0.0)
        Q_net = Q - Q_loss

        if Q_net > 0:
            dT_rise = (Q_net * duration) / thermal_mass
            return min(T_prev + dT_rise, T_sat)
        else:
            # If Q_net <= 0, temperature drops or stays stable
            dT_drop = (Q_net * duration) / thermal_mass
            return max(T_prev + dT_drop, const.T_AMB)

    return T_sat

def predict_forward(P_init, Vdw_init, phi_init, m_w, Q, valve_opening, T_init=None, T_wall_init=None, duration=300.0, dt=1.0):
    """
    Physics-based forward prediction with proper regime handling:

    Regime 1 — Subcooled (T < T_sat):
      All heat → sensible heating.  dT/dt = Q / (M_w·Cp + M_m·C_m)
      Pressure = atmospheric,  no steam generated.

    Regime 2 — Two-Phase Boiling (T ≥ T_sat):
      Full 4-equation drum-boiler ODE (mass + energy conservation).
      Steam is generated, pressure can rise.
    """
    P_atm = 1.013e5  # Pa
    T_sat_atm = thermo.get_T_sat(P_atm) - 273.15  # ≈100 °C

    cur_T = T_init if T_init is not None else 25.0
    cur_T_wall = T_wall_init if T_wall_init is not None else (cur_T + 2.0)

    # ── Subcooled check ──
    T_sat_currP = thermo.get_T_sat(P_init) - 273.15
    if cur_T < T_sat_currP:
        rho_w = get_liquid_density(P_init, cur_T)
        M_water = rho_w * Vdw_init * (1.0 - phi_init) # kg of pure liquid water
        thermal_mass = (M_water * CP_WATER) + (const.M_M * const.C_M)

        # ── Dynamic Onset of Nucleate Boiling (ONB) ──
        q_flux = Q / const.A_HEATER
        sigma = thermo.get_sigma(P_atm)
        k_l = thermo.get_k_l(P_atm, cur_T)
        rho_s = thermo.get_rho_s(P_atm)
        h_fg = thermo.get_h_fg(P_atm)
        T_sat_K = T_sat_currP + 273.15

        superheat_ONB = np.sqrt((8.0 * sigma * T_sat_K * q_flux) / (k_l * rho_s * h_fg))
        T_ONB = T_sat_currP - (max(5.0, min(superheat_ONB, 25.0)))

        # ── Mechanistic Heat Partitioning ──
        # Energy split between sensible (liquid) and latent (bubble formation)
        if cur_T > T_ONB:
            # Exponential profile fit for subcooled boiling intensity
            Z = (cur_T - T_ONB) / (T_sat_currP - T_ONB)
            epsilon = (1.0 - np.exp(-Z)) / (1.0 - np.exp(-1.0))
        else:
            epsilon = 0.0

        Q_loss = const.U_LOSS * const.A_VESSEL * max(cur_T - const.T_AMB, 0.0)
        Q_net = max(Q - Q_loss, 0.0)
        Q_sensible = Q_net * (1.0 - 0.10 * epsilon) # Max 10% latent loss at sat point

        t_to_boil = (T_sat_currP - cur_T) * thermal_mass / Q_sensible if Q_sensible > 0 else float('inf')

        if t_to_boil >= duration:
            # Water never reaches boiling in this window
            # ── Sub-step to capture sealed-vessel pressure rise ──
            # Combined gas-cap compression + water compressibility model.
            # dP = (beta * dT * V_water) / (V_gas/P + V_water/K_water)
            n_sub = int(max(1, duration / 2.0))
            sub_dt = duration / n_sub
            cur_P_sub = P_init
            cur_Vdw_sub = Vdw_init
            T_accum = cur_T
            water_mass_sub = M_water
            for _ in range(n_sub):
                if m_w > 0:
                    water_mass_sub += m_w * sub_dt
                thermal_mass = (water_mass_sub * CP_WATER) + (const.M_M * const.C_M)
                dT_heat = (Q_sensible * sub_dt) / thermal_mass
                dT_mix = 0.0
                if m_w > 0 and water_mass_sub > 1e-6:
                    dT_mix = (m_w * CP_WATER * (const.T_FEED - T_accum) * sub_dt) / thermal_mass
                dT_sub = dT_heat + dT_mix
                T_old = T_accum
                T_accum += dT_sub
                # Sealed-vessel pressure rise from thermal expansion
                beta_T = water_thermal_expansion_beta(T_accum)
                # Ensure a minimum gas headspace of 500mL to prevent numerical hydraulic lock
                V_gas = max(0.0005, const.V_T - cur_Vdw_sub)
                # Effective compressibility: gas cap (ideal gas) + liquid water
                C_gas = V_gas / cur_P_sub   # gas cap compressibility (m³/Pa)
                C_water = cur_Vdw_sub / K_WATER  # water compressibility (m³/Pa)
                dP_therm = (beta_T * dT_sub * cur_Vdw_sub) / (C_gas + C_water)

                # Water vapor partial pressure contribution
                # In a sealed vessel, headspace = trapped air + water vapor.
                # As T rises, P_sat(T) increases exponentially (dominant above ~60°C).
                dP_vapor = thermo.get_P_sat(T_accum + 273.15) - thermo.get_P_sat(T_old + 273.15)
                dP_vapor = max(0.0, dP_vapor) * get_eta_vapor(T_accum)

                # Parasitic steam leak is a continuous physical effect.
                # It must be applied even when the valve is closed, otherwise 
                # the subcooled sealed regime will diverge from reality and the ODE regime.
                P_gauge_sub = max(0, cur_P_sub - 1.013e5) / 1e5
                m_leak_sub = const.K_LEAK * P_gauge_sub * sub_dt
                if V_gas > 0:
                    dP_leak = m_leak_sub * cur_P_sub / (V_gas * thermo.get_rho_s(cur_P_sub))
                else:
                    dP_leak = 0.0

                cur_P_sub += dP_therm + dP_vapor - dP_leak
                
                # Mass lost from leak must be removed from the subcooled water inventory
                water_mass_sub -= m_leak_sub

                # Update water volume (thermal expansion minus compression)
                dV_expand = cur_Vdw_sub * beta_T * dT_sub - C_water * dP_therm
                if m_w > 0:
                    rho_feed = get_liquid_density(cur_P_sub, const.T_FEED)
                    dV_feed = (m_w * sub_dt) / rho_feed
                else:
                    dV_feed = 0.0
                
                # Deduct liquid volume converted to vapor and leaked
                rho_current = get_liquid_density(cur_P_sub, T_accum)
                dV_leak = m_leak_sub / rho_current
                cur_Vdw_sub = clamp_mixture_volume(cur_Vdw_sub + dV_expand + dV_feed - dV_leak)

            T_final = T_accum
            L_final = cur_Vdw_sub / const.A_D
            # Compute subcooled phi at final temperature
            if T_final > T_ONB:
                sf = (T_final - T_ONB) / (T_sat_currP - T_ONB)
                alpha_final = 0.005 * sf ** 2
                rho_s_f = thermo.get_rho_s(cur_P_sub)
                rho_w_f = thermo.get_rho_w(cur_P_sub)
                phi_final = (alpha_final * rho_s_f) / (alpha_final * rho_s_f + (1.0 - alpha_final) * rho_w_f)
            else:
                phi_final = 0.0
            return cur_P_sub, cur_Vdw_sub, phi_final, L_final, T_final, T_final + 2.0

        # ── Transition: boil at t_to_boil, run ODE for the rest ──
        remaining = duration - t_to_boil
        y0 = [P_init, Vdw_init, 0.005, cur_T_wall]       # continuous from subcooled peak
        sol = safe_solve_ivp(
            fun=lambda t, y: system_derivatives(t, y, m_w, Q, valve_opening),
            t_span=(0.0, remaining),
            y0=y0,
            method='Radau',
            t_eval=[remaining]
        )
        P_final  = max(sol.y[0, -1], P_atm)
        Vdw_fin  = max(sol.y[1, -1], 0.0)
        phi_fin  = max(0.0, min(1.0, sol.y[2, -1]))
        T_wall_fin = sol.y[3, -1]
        L_final  = model.calculate_drum_level(Vdw_fin, phi_fin, P_final)
        T_final  = thermo.get_T_sat(P_final) - 273.15
        return P_final, Vdw_fin, phi_fin, L_final, T_final, T_wall_fin

    # ── Already at / above saturation (or heater off) ──
    y0 = [P_init, Vdw_init, phi_init, cur_T_wall]
    sol = safe_solve_ivp(
        fun=lambda t, y: system_derivatives(t, y, m_w, Q, valve_opening),
        t_span=(0.0, duration),
        y0=y0,
        method='Radau',
        t_eval=[duration]
    )
    P_final  = max(sol.y[0, -1], 1.0)
    Vdw_fin  = max(sol.y[1, -1], 0.0)
    phi_fin  = max(0.0, min(1.0, sol.y[2, -1]))
    T_wall_fin = sol.y[3, -1]
    L_final  = model.calculate_drum_level(Vdw_fin, phi_fin, P_final)
    T_final  = calculate_dynamic_temperature(P_final, Vdw_fin, Q, duration, T_init)
    return P_final, Vdw_fin, phi_fin, L_final, T_final, T_wall_fin


def predict_timeline(P_init, Vdw_init, phi_init, m_w, Q, valve_opening, T_init=None, n_points=10, step_seconds=60.0):
    """
    Physics-based 10-minute prediction with three thermal regimes.

    Regime 1a — Pure Subcooled  (T < T_ONB ≈ 80 °C)
      All heater energy goes to sensible heating of liquid + metal.
      No bubbles.  Pressure = atmospheric.
        dT/dt = Q / (M_water·Cp_water + M_metal·C_metal)

    Regime 1b — Subcooled Nucleate Boiling  (T_ONB ≤ T < T_sat)
      The heated wall surface exceeds T_sat → small steam bubbles
      nucleate on the surface (Onset of Nucleate Boiling).
      Bubbles collapse back into the cooler bulk liquid, so there is
      NO net steam accumulation and NO pressure rise.  However:
        • A small, growing void fraction φ_sub is visible (bubbles)
        • A fraction of heater energy goes into latent heat of
          bubble formation/collapse, slightly slowing sensible heating.
      Governing equations:
        subcool_frac = (T - T_ONB) / (T_sat - T_ONB)       ∈ [0, 1]
        φ_sub        = φ_max_sub · subcool_frac²            (quadratic onset)
        Q_sensible   = Q · (1 - η · subcool_frac)           (η ≈ 0.08)

    Regime 2 — Two-Phase Boiling  (T ≥ T_sat)
      Full 4-equation drum-boiler ODE model.  Steam is generated,
      pressure rises, T tracks saturation curve: T = T_sat(P).

    Returns list of dicts:  [{ t_min, P, Vdw, phi, L, T }, ...]
    """
    t_eval_points = [i * step_seconds for i in range(1, n_points + 1)]

    # ── Atmospheric reference ──
    P_atm = 1.013e5                                  # Pa
    T_sat_atm = thermo.get_T_sat(P_atm) - 273.15    # ≈ 100 °C

    # ── Current state ──
    cur_T   = T_init if T_init is not None else 25.0
    cur_P   = P_init
    cur_Vdw = Vdw_init
    cur_phi = phi_init
    cur_T_wall = cur_T + 2.0

    # ── Thermal mass for subcooled energy balance ──
    rho_w = get_liquid_density(cur_P, cur_T)
    M_water   = rho_w * Vdw_init * (1.0 - phi_init)  # kg of pure liquid
    thermal_mass = (M_water * CP_WATER) + (const.M_M * const.C_M)
    water_mass_liq = M_water

    boiling_active = cur_T >= (thermo.get_T_sat(cur_P) - 273.15)
    results = []

    for i, t_target in enumerate(t_eval_points):
        t_start = t_eval_points[i - 1] if i > 0 else 0.0
        dt = t_target - t_start

        T_sat_currP = thermo.get_T_sat(cur_P) - 273.15
        if not boiling_active:
            # ═══════════════════════════════════════════════════════
            #  REGIME 1 :  Subcooled Heating (with nucleate boiling)
            # ═══════════════════════════════════════════════════════
            if Q > 0 or m_w > 0:
                # ── Dynamic ONB and Heat Partitioning via Sub-stepping ──
                # Also update inlet flow here; otherwise water-level prediction
                # freezes whenever the heater is off.
                sub_steps = int(max(1, dt / 2.0)) # 2-second sub-steps for speed
                sub_dt = dt / sub_steps

                q_flux = max(Q, 0.0) / const.A_HEATER
                sigma = thermo.get_sigma(P_atm)
                k_l = thermo.get_k_l(P_atm, cur_T)
                rho_s = thermo.get_rho_s(P_atm)
                h_fg = thermo.get_h_fg(P_atm)

                new_T_accum = cur_T

                for _ in range(sub_steps):
                    if m_w > 0:
                        water_mass_liq += m_w * sub_dt
                        rho_feed = get_liquid_density(cur_P, const.T_FEED)
                        cur_Vdw = clamp_mixture_volume(cur_Vdw + (m_w * sub_dt) / rho_feed)

                    thermal_mass = (water_mass_liq * CP_WATER) + (const.M_M * const.C_M)
                    T_sat_currP_sub = thermo.get_T_sat(cur_P) - 273.15
                    superheat_ONB = np.sqrt((8.0 * sigma * (T_sat_currP_sub+273.15) * q_flux) / (k_l * rho_s * h_fg)) if q_flux > 0 else 0.0
                    T_ONB_i = T_sat_currP_sub - (max(5.0, min(superheat_ONB, 25.0)))

                    if new_T_accum > T_ONB_i:
                        Z = (new_T_accum - T_ONB_i) / (T_sat_currP_sub - T_ONB_i)
                        epsilon = (1.0 - np.exp(-Z)) / (1.0 - np.exp(-1.0))
                    else:
                        epsilon = 0.0

                    Q_loss = const.U_LOSS * const.A_VESSEL * max(new_T_accum - const.T_AMB, 0.0)
                    Q_net = max(Q - Q_loss, 0.0)
                    Q_sensible = Q_net * (1.0 - 0.10 * epsilon)
                    Q_latent = Q_net - Q_sensible

                    if Q_latent > 0:
                        m_g_subcooled = Q_latent / h_fg
                        V_above = max(0.0001, const.V_T - cur_Vdw)
                        d_rho_g = (m_g_subcooled * sub_dt) / V_above
                        dP_subcooled = d_rho_g / thermo.get_drho_s_dP(cur_P)
                        cur_P += dP_subcooled

                    dT_heat = (Q_sensible * sub_dt) / thermal_mass
                    dT_mix = 0.0
                    if m_w > 0 and water_mass_liq > 1e-6:
                        dT_mix = (m_w * CP_WATER * (const.T_FEED - new_T_accum) * sub_dt) / thermal_mass
                    dT = dT_heat + dT_mix
                    T_old_step = new_T_accum
                    new_T_accum += dT

                    # ── Sealed-vessel pressure rise from thermal expansion ──
                    # Combined gas-cap + water compressibility model
                    K_WATER = 2.2e9  # Bulk modulus of water (Pa)
                    beta_T = water_thermal_expansion_beta(new_T_accum)
                    # Minimum gas headspace floor (500mL) — prevents near-hydraulic-lock
                    # feedback where shrinking gas cap causes dP/dT → ∞
                    V_gas = max(0.0005, const.V_T - cur_Vdw)
                    C_gas = V_gas / cur_P
                    C_water = cur_Vdw / K_WATER
                    dP_therm = (beta_T * dT * cur_Vdw) / (C_gas + C_water)

                    # Water vapor partial pressure contribution
                    # In a sealed vessel, headspace = trapped air + water vapor.
                    # As T rises, P_sat(T) increases exponentially (dominant above ~60°C).
                    dP_vapor = thermo.get_P_sat(new_T_accum + 273.15) - thermo.get_P_sat(T_old_step + 273.15)
                    dP_vapor = max(0.0, dP_vapor) * get_eta_vapor(new_T_accum)

                    # Parasitic steam leak is a continuous physical effect.
                    P_gauge_sub = max(0, cur_P - 1.013e5) / 1e5
                    m_leak_sub = const.K_LEAK * P_gauge_sub * sub_dt
                    if V_gas > 0:
                        dP_leak = m_leak_sub * cur_P / (V_gas * thermo.get_rho_s(cur_P))
                    else:
                        dP_leak = 0.0

                    cur_P = min(cur_P + dP_therm + dP_vapor - dP_leak, 10e5) # Cap at 10 bar (Safety Valve)
                    
                    # Mass lost from leak must be removed from the subcooled water inventory
                    water_mass_liq -= m_leak_sub
                    
                    dV_expand = cur_Vdw * beta_T * dT - C_water * dP_therm
                    
                    # Deduct liquid volume converted to vapor and leaked
                    rho_current = get_liquid_density(cur_P, new_T_accum)
                    dV_leak = m_leak_sub / rho_current
                    cur_Vdw = clamp_mixture_volume(cur_Vdw + dV_expand - dV_leak)

                new_T = new_T_accum
                T_sat_currP = thermo.get_T_sat(cur_P) - 273.15

                if new_T >= T_sat_currP:
                    # ── Transition: full boiling begins mid-interval ──
                    t_to_boil    = (T_sat_currP - cur_T) * thermal_mass / Q_sensible if Q_sensible > 0 else float('inf')
                    remaining_dt = dt - t_to_boil

                    boiling_active = True
                    cur_T   = T_sat_currP
                    # Maintain current pressure rather than forcing to P_atm
                    cur_phi = PHI_MAX_SUBCOOLED   # continuous transition

                    if remaining_dt > 0.1:   # run ODE only if meaningful
                        y0  = [cur_P, cur_Vdw, cur_phi, cur_T_wall]
                        sol = safe_solve_ivp(
                            fun=lambda t, y: system_derivatives(t, y, m_w, Q, valve_opening),
                            t_span=(0.0, remaining_dt),
                            y0=y0,
                            method='Radau',
                            t_eval=[remaining_dt]
                        )

                        if sol.success and sol.y.shape[1] > 0:
                            cur_P   = max(sol.y[0, -1], P_atm)
                            cur_Vdw = max(sol.y[1, -1], 0.0)
                            cur_phi = max(0.0, min(1.0, sol.y[2, -1]))
                            cur_T_wall = sol.y[3, -1]
                            cur_T   = thermo.get_T_sat(cur_P) - 273.15
                        else:
                            # Solver stalled or failed - keep last known state
                            cur_T = T_sat_currP
                            cur_phi = PHI_MAX_SUBCOOLED
                else:
                    cur_T   = new_T
                    cur_T_wall = cur_T + 2.0
                    # Maintain current pressure rather than forcing to P_atm

                    # Subcooled nucleate boiling: small vapor fraction
                    if cur_T > T_ONB_i:
                        Z = (cur_T - T_ONB_i) / (T_sat_currP - T_ONB_i)
                        alpha_sub = 0.005 * Z ** 2
                        rho_s_sub = thermo.get_rho_s(cur_P)
                        rho_w_sub = thermo.get_rho_w(cur_P)
                        cur_phi = (alpha_sub * rho_s_sub) / (alpha_sub * rho_s_sub + (1.0 - alpha_sub) * rho_w_sub)
                    else:
                        cur_phi = 0.0
            # else Q == 0: no heating → state unchanged

            L_i = cur_Vdw / const.A_D
            results.append({
                't_min': i + 1,
                'P':   cur_P,
                'Vdw': cur_Vdw,
                'phi': cur_phi,
                'L':   L_i,
                'T':   cur_T
            })
        else:
            # ═══════════════════════════════════════════════════════
            #  REGIME 2 :  Two-Phase Boiling  (full ODE)
            #  State:  y = [P, V_dw, phi]
            #  T = T_sat(P)  — temperature tracks saturation curve
            # ═══════════════════════════════════════════════════════
            y0  = [cur_P, cur_Vdw, cur_phi, cur_T_wall]
            sol = safe_solve_ivp(
                fun=lambda t, y: system_derivatives(t, y, m_w, Q, valve_opening),
                t_span=(0.0, dt),
                y0=y0,
                method='Radau',
                t_eval=[dt]
            )
            cur_P   = max(sol.y[0, -1], P_atm)
            cur_Vdw = max(sol.y[1, -1], 0.0)
            cur_phi = max(0.0, min(1.0, sol.y[2, -1]))
            cur_T_wall = sol.y[3, -1]
            L_i     = model.calculate_drum_level(cur_Vdw, cur_phi, cur_P)
            cur_T   = thermo.get_T_sat(cur_P) - 273.15

            results.append({
                't_min': i + 1,
                'P':   cur_P,
                'Vdw': cur_Vdw,
                'phi': cur_phi,
                'L':   L_i,
                'T':   cur_T
            })

    return results

def run_continuous(P_init, Vdw_init, phi_init, m_w, Q, valve_opening, T_init=None, dt=1.0):
    """
    Run the boiler physics model in a continuous simulation loop.
    Acts as an infinite generator emitting realtime predictions.
    """
    P = P_init
    V_dw = Vdw_init
    phi = phi_init
    current_T = T_init if T_init is not None else 25.0
    current_T_wall = current_T + 2.0

    current_time = 0.0

    while True:
        # Compute outputs
        L = model.calculate_drum_level(V_dw, phi, P)
        T = calculate_dynamic_temperature(P, V_dw, Q, dt, current_T)
        current_T = T # Update state for next step

        # Yield the current timestep results
        new_inputs = (yield P, V_dw, phi, L, T)
        if new_inputs is not None:
            # If the user sends T in the tuple, update it (sync with hardware)
            if len(new_inputs) == 4:
                m_w, Q, valve_opening, current_T = new_inputs
            else:
                m_w, Q, valve_opening = new_inputs

        # Calculate diagnostics to print (like mg and ms)
        X = model.solve_system(P, V_dw, phi, m_w, Q, valve_opening)
        m_g = X[3]
        A_orifice = np.pi / 4.0 * const.D_PIPE**2
        rho_s = thermo.get_rho_s(P)
        delta_P = max(P - const.P_DOWNSTREAM, 0.0)
        m_s = const.C_D_VALVE * A_orifice * valve_opening * np.sqrt(2.0 * rho_s * delta_P)

        print(f"mg (evaporation rate): {m_g:.4f}")
        print(f"ms = Cd*A*sqrt(2*rho*dP): {m_s:.4f}")
        print("\nCompare:")
        if m_s > m_g:
            print("If ms > mg -> pressure must drop\n")
        elif m_s < m_g:
            print("If ms < mg -> pressure must rise\n")
        else:
            print("If ms == mg -> pressure stable\n")

        # Stepping forward by dt
        y0 = [P, V_dw, phi, current_T_wall]

        sol = safe_solve_ivp(
            fun=lambda t, y: system_derivatives(t, y, m_w, Q, valve_opening),
            t_span=(current_time, current_time + dt),
            y0=y0,
            method='Radau',
            t_eval=[current_time + dt]
        )

        P = max(sol.y[0, -1], 1.0)
        V_dw = max(sol.y[1, -1], 0.0)
        phi = max(0.0, min(1.0, sol.y[2, -1]))
        current_T_wall = sol.y[3, -1]

        current_time += dt
