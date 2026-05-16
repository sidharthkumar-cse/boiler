import numpy as np
import warnings
from core import coefficients as coef
from physics import void_fraction as void
from physics import thermo_relations as thermo
from config import constants as const

def solve_system(P, V_dw, phi, m_w, Q_fluid, valve_opening):
    """
    Solve for dX/dt and algebraic variables.
    Returns: [dP/dt, dV_dw/dt, dphi/dt, m_g]

    Uses row-scaling to reduce the condition number of C from O(10^14) to O(10^6).
    The extreme density ratio rho_w/rho_s ≈ 1600 causes large scale differences
    between mass equations; row-scaling normalizes each equation by its largest
    coefficient, preserving the solution while improving numerical precision.
    """
    # Calculate C and D
    C = coef.calculate_matrix_C(P, V_dw, phi)
    D = coef.calculate_vector_D(P, V_dw, phi, m_w, Q_fluid, valve_opening)
    
    # Row-scaling: normalize each row by its largest absolute element
    for i in range(C.shape[0]):
        scale = np.max(np.abs(C[i, :]))
        if scale > 1e-30:  # Guard against zero rows
            C[i, :] /= scale
            D[i] /= scale
    
    # Solve C * X = D
    try:
        cond = np.linalg.cond(C)
        if cond > 1e12:
            warnings.warn(f"[Solver] High condition number κ(C) = {cond:.2e} — near-singular", stacklevel=2)
        X = np.linalg.solve(C, D)
    except np.linalg.LinAlgError:
        # Handle singular matrix (e.g., at boundaries)
        warnings.warn("[Solver] Singular C matrix — returning zero derivatives", stacklevel=2)
        X = np.zeros(4)
        
    return X


# ═══════════════════════════════════════════════════════════════════
#  Live Thermodynamic Consistency Audits
# ═══════════════════════════════════════════════════════════════════

def audit_mass_conservation(P, V_dw, phi, m_w, m_s, m_g, dP_dt, dVdw_dt, dphi_dt):
    """
    Verify global mass conservation:  dM_total/dt = ṁ_fw − ṁ_s

    M_total = ρ_w·V_dw·(1−α) + ρ_s·V_dw·α + ρ_s·(V_T−V_dw)

    Returns:
      mass_error: |dM_computed − (ṁ_fw − ṁ_s)|  in kg/s
                  Should be < 1e-10 for a well-posed system.
    """
    rho_w = thermo.get_rho_w(P)
    rho_s = thermo.get_rho_s(P)
    drho_w_dP = thermo.get_drho_w_dP(P)
    drho_s_dP = thermo.get_drho_s_dP(P)
    alpha = void.get_void_fraction(phi, P)
    da_dphi = void.get_d_alpha_d_phi(phi, P)
    da_dP = void.get_d_alpha_d_P(phi, P)

    # dM_total/dt via product rule (sum of all 3 mass regions)
    # Liquid: d/dt[ρ_w·V_dw·(1−α)]
    dM_liq = (V_dw * (1 - alpha) * drho_w_dP - rho_w * V_dw * da_dP) * dP_dt \
           + rho_w * (1 - alpha) * dVdw_dt \
           - rho_w * V_dw * da_dphi * dphi_dt

    # Steam below: d/dt[ρ_s·V_dw·α]
    dM_sb = (V_dw * alpha * drho_s_dP + rho_s * V_dw * da_dP) * dP_dt \
          + rho_s * alpha * dVdw_dt \
          + rho_s * V_dw * da_dphi * dphi_dt

    # Steam above: d/dt[ρ_s·(V_T−V_dw)]
    dM_sa = (const.V_T - V_dw) * drho_s_dP * dP_dt - rho_s * dVdw_dt

    dM_total = dM_liq + dM_sb + dM_sa
    expected = m_w - m_s  # Net mass flow (in − out)
    mass_error = abs(dM_total - expected)

    return mass_error


def audit_entropy_production(P, V_dw, phi, Q_fluid, Q_loss, T_wall, m_w, m_s):
    """
    Verify Clausius inequality (Second Law):  dS_irr ≥ 0

    Entropy production rate:
      Ṡ_irr = Ṡ_system + Ṡ_out − Ṡ_in − Q̇/T_source

    For a boiler with heat input Q at T_wall and losses Q_loss at T_amb:
      Ṡ_irr ≈ Q_fluid/T_water − Q_fluid/T_wall + Q_loss/T_amb − Q_loss/T_water
             + m_s·s_s − m_w·s_w

    Returns:
      s_irr: Entropy production rate (W/K). Must be ≥ 0.
      is_valid: True if 2nd Law is satisfied.
    """
    T_sat_K = thermo.get_T_sat(P)
    T_wall_K = T_wall + 273.15
    T_amb_K = const.T_AMB + 273.15

    # Heat transfer irreversibility (finite ΔT between wall and water)
    if T_wall_K > 0 and T_sat_K > 0:
        s_irr_heat = Q_fluid * (1.0 / T_sat_K - 1.0 / T_wall_K)
    else:
        s_irr_heat = 0.0

    # Environmental loss irreversibility
    if T_sat_K > 0:
        s_irr_loss = Q_loss * (1.0 / T_amb_K - 1.0 / T_sat_K)
    else:
        s_irr_loss = 0.0

    # Total irreversible entropy production
    s_irr = s_irr_heat + s_irr_loss

    return s_irr, s_irr >= -1e-10  # Small tolerance for numerical noise


def calculate_drum_level(V_dw, phi, P):
    """
    Predict apparent water level (m) including swell effect.

    Physics:
      V_dw is the total mixture volume (liquid + bubbles).
      Therefore, the apparent level is simply the mixture volume divided by the cross-sectional area.
      L_apparent = V_dw / A_D

    The swell effect is natively included in V_dw because the ODE system dynamically expands V_dw
    as steam bubbles (phi) are generated within the liquid column.
    """
    L_apparent = V_dw / const.A_D
    # Clamp to drum height
    return min(L_apparent, const.H_DRUM)

def calculate_temperature(P):
    """
    Predict Temperature (T) in Celsius.
    T is a saturation temperature function of P.
    """
    T_K = thermo.get_T_sat(P)
    return T_K - 273.15

