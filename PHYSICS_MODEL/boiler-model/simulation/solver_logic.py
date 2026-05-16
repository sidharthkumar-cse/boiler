import numpy as np
from scipy.integrate import solve_ivp
from model import matrix_form as model
from equations import thermo_relations as thermo
from inputs import constants as const
from iapws import IAPWS97


# ═══════════════════════════════════════════════════════════════════
#  Initial State Computation from Live Sensor Data
# ═══════════════════════════════════════════════════════════════════

# Maximum void fraction during subcooled boiling before transition to saturated boiling
PHI_MAX_SUBCOOLED = 0.005

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
      │  IAPWS-97:  ρ_w = ρ(T_sensor, P_sensor)               │
      │       ↓                                               │
      │  V_dw = water_mass_kg / ρ_w                           │
      │       ↓                                              v │
      │  L = V_dw / A_D    (A_D = π/4 × 19.05² cm²)        v   │
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
    T_K = T_celsius + 273.15
    P_MPa = P_pa / 1e6

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
        try:
            water = IAPWS97(T=T_K, P=P_MPa)
            rho_w = water.rho
        except Exception:
            # Fallback: empirical correlation for liquid water (0–100 °C)
            rho_w = (999.84 + 16.945 * T_celsius
                     - 7.987e-3 * T_celsius**2
                     - 46.17e-6 * T_celsius**3)
    else:
        # At or above saturation — use saturated liquid density
        rho_w = thermo.get_rho_w(P_pa)

    # ── Void fraction (steam quality) ──
    if T_celsius >= T_sat_C:
        # At saturation: steady-state void fraction from bubble rise dynamics
        # phi = m_g / (rho_s * A_D * v_rise)
        m_g_est = Q_avg / h_fg
        v_rise = 1.41 * ( (sigma * 9.81 * (rho_w - rho_s)) / (rho_w**2) )**0.25
        phi_ss = m_g_est / (rho_s * const.A_D * v_rise)
        phi = min(max(phi_ss, 0.005), 0.95)
    elif T_celsius > T_ONB:
        # Subcooled nucleate boiling: small bubbles on heated wall
        subcool_frac = (T_celsius - T_ONB) / (T_sat_C - T_ONB)
        phi = 0.005 * subcool_frac ** 2
    else:
        # Pure subcooled liquid — no bubbles
        phi = 0.0

    # ── Downcomer mixture volume (from pure liquid mass and void fraction) ──
    # Pure liquid volume
    V_liquid = water_mass_kg / rho_w
    # Total mixture volume (liquid + bubbles)
    Vdw = V_liquid / (1.0 - min(phi, 0.95))

    # ── Apparent Water level  =  mixture volume / cross-section area ──
    # Clamp to drum height to prevent overflow in calculations
    L = min(Vdw / const.A_D, const.H_DRUM)

    return Vdw, phi, L

def system_derivatives(t, y, m_w, Q, valve_opening):
    """
    State wrapper for scipy integrate.
    y = [P, Vdw, phi, T_wall]
    """
    if len(y) == 4:
        P, V_dw, phi, T_wall = y
    else:
        P, V_dw, phi = y
        T_wall = thermo.get_T_sat(P) - 273.15 + 5.0 # fallback
    
    # Boundary clamps to prevent solver from evaluating unphysical states
    # which could domain error in square roots or steam tables computation
    P_safe = min(max(P, 5000.0), 3000000.0)
    V_dw_safe = max(V_dw, 0.0)
    phi_safe = max(0.0, min(1.0, phi))
    
    # --- Metal Wall Heat Transfer (Thom Correlation + Natural Convection) ---
    T_water = thermo.get_T_sat(P_safe) - 273.15
    delta_T_sat = max(T_wall - T_water, 0.0)
    
    # Baseline natural convection to liquid water
    H_conv = 500.0  
    
    # Thom correlation for nucleate boiling of water:
    # delta_T = 22.65 * (q'' / 1e6)^0.5 * exp(-P / 8.7e6)
    # => q'' = 1e6 * (delta_T * exp(P / 8.7e6) / 22.65)^2
    if delta_T_sat > 0:
        q_flux_boil = 1e6 * ( (delta_T_sat * np.exp(P_safe / 8.7e6)) / 22.65 )**2
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
    X = model.solve_system(P_safe, V_dw_safe, phi_safe, m_w, Q_transfer, valve_opening)
    
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
        rho_w = thermo.get_rho_w(P_pa)
        M_water = rho_w * V_dw
        
        # Effective thermal mass (Water + Metal)
        CP_WATER = 4186.0 
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
    if cur_T < T_sat_currP and Q > 0:
        rho_w = thermo.get_rho_w(P_atm)
        M_water = rho_w * Vdw_init * (1.0 - phi_init) # kg of pure liquid water
        CP_WATER = 4186.0                    # J/(kg·K)
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
            K_WATER = 2.2e9  # Bulk modulus of water (Pa)
            n_sub = int(max(1, duration / 2.0))
            sub_dt = duration / n_sub
            cur_P_sub = P_init
            cur_Vdw_sub = Vdw_init
            T_accum = cur_T
            for _ in range(n_sub):
                dT_sub = (Q_sensible * sub_dt) / thermal_mass
                T_accum += dT_sub
                # Sealed-vessel pressure rise from thermal expansion
                beta_T = water_thermal_expansion_beta(T_accum)
                V_gas = max(1e-6, const.V_T - cur_Vdw_sub)
                # Effective compressibility: gas cap (ideal gas) + liquid water
                C_gas = V_gas / cur_P_sub   # gas cap compressibility (m³/Pa)
                C_water = cur_Vdw_sub / K_WATER  # water compressibility (m³/Pa)
                dP = (beta_T * dT_sub * cur_Vdw_sub) / (C_gas + C_water)
                cur_P_sub += dP
                # Update water volume (thermal expansion minus compression)
                dV_expand = cur_Vdw_sub * beta_T * dT_sub - C_water * dP
                cur_Vdw_sub += dV_expand

            T_final = T_accum
            L_final = cur_Vdw_sub / const.A_D
            # Compute subcooled phi at final temperature
            if T_final > T_ONB:
                sf = (T_final - T_ONB) / (T_sat_currP - T_ONB)
                phi_final = 0.005 * sf ** 2
            else:
                phi_final = 0.0
            return cur_P_sub, cur_Vdw_sub, phi_final, L_final, T_final, T_final + 2.0

        # ── Transition: boil at t_to_boil, run ODE for the rest ──
        remaining = duration - t_to_boil
        y0 = [P_init, Vdw_init, 0.005, cur_T_wall]       # continuous from subcooled peak
        sol = solve_ivp(
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
    sol = solve_ivp(
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
    rho_w = thermo.get_rho_w(P_atm)
    M_water   = rho_w * Vdw_init * (1.0 - phi_init)  # kg of pure liquid
    CP_WATER  = 4186.0                               # J/(kg·K)
    thermal_mass = (M_water * CP_WATER) + (const.M_M * const.C_M)

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
            if Q > 0:
                # ── Dynamic ONB and Heat Partitioning via Sub-stepping ──
                # Use 1-second internal steps because P rises and immediately suppresses boiling
                sub_steps = int(max(1, dt / 2.0)) # 2-second sub-steps for speed
                sub_dt = dt / sub_steps
                
                q_flux = Q / const.A_HEATER
                sigma = thermo.get_sigma(P_atm)
                k_l = thermo.get_k_l(P_atm, cur_T)
                rho_s = thermo.get_rho_s(P_atm)
                h_fg = thermo.get_h_fg(P_atm)
                
                new_T_accum = cur_T
                
                for _ in range(sub_steps):
                    T_sat_currP_sub = thermo.get_T_sat(cur_P) - 273.15
                    superheat_ONB = np.sqrt((8.0 * sigma * (T_sat_currP_sub+273.15) * q_flux) / (k_l * rho_s * h_fg))
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
    
                    dT = (Q_sensible * sub_dt) / thermal_mass
                    new_T_accum += dT
    
                    # ── Sealed-vessel pressure rise from thermal expansion ──
                    # Combined gas-cap + water compressibility model
                    K_WATER = 2.2e9  # Bulk modulus of water (Pa)
                    beta_T = water_thermal_expansion_beta(new_T_accum)
                    V_gas = max(1e-6, const.V_T - cur_Vdw)
                    C_gas = V_gas / cur_P
                    C_water = cur_Vdw / K_WATER
                    dP_therm = (beta_T * dT * cur_Vdw) / (C_gas + C_water)
                    cur_P += dP_therm
                    dV_expand = cur_Vdw * beta_T * dT - C_water * dP_therm
                    cur_Vdw += dV_expand
                    
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

                    if remaining_dt > 1.0:   # run ODE only if meaningful
                        y0  = [cur_P, cur_Vdw, cur_phi, cur_T_wall]
                        sol = solve_ivp(
                            fun=lambda t, y: system_derivatives(t, y, m_w, Q, valve_opening),
                            t_span=(0.0, remaining_dt),
                            y0=y0,
                            method='Radau',
                            t_eval=[remaining_dt]
                        )
                        cur_P   = max(sol.y[0, -1], P_atm)
                        cur_Vdw = max(sol.y[1, -1], 0.0)
                        cur_phi = max(0.0, min(1.0, sol.y[2, -1]))
                        cur_T_wall = sol.y[3, -1]
                        cur_T   = thermo.get_T_sat(cur_P) - 273.15
                else:
                    cur_T   = new_T
                    cur_T_wall = cur_T + 2.0
                    # Maintain current pressure rather than forcing to P_atm

                    # Subcooled nucleate boiling: small vapor fraction
                    if cur_T > T_ONB_i:
                        Z = (cur_T - T_ONB_i) / (T_sat_currP - T_ONB_i)
                        cur_phi = 0.005 * Z ** 2
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
            sol = solve_ivp(
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
        
        sol = solve_ivp(
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
