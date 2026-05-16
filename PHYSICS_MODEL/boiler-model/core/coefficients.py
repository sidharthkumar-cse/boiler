import numpy as np
from physics import thermo_relations as thermo
from physics import void_fraction as void
from physics import water_mass
from physics import steam_below
from physics import steam_above
from physics import energy
from config import constants as const
from iapws import IAPWS97

def calculate_matrix_C(P, V_dw, phi):
    """
    Calculate the 4x4 matrix C for the system CX = D.
    X = [dP/dt, dV_dw/dt, dphi/dt, m_g]^T
    """
    # Thermo properties
    rho_w = thermo.get_rho_w(P)
    rho_s = thermo.get_rho_s(P)
    drho_w_dP = thermo.get_drho_w_dP(P)
    drho_s_dP = thermo.get_drho_s_dP(P)
    
    h_w = thermo.get_h_w(P)
    h_s = thermo.get_h_s(P)
    u_w = thermo.get_u_w(P)
    u_s = thermo.get_u_s(P)
    
    d_rho_u_w_dP = thermo.get_d_rho_u_w_dP(P)
    d_rho_u_s_dP = thermo.get_d_rho_u_s_dP(P)
    dT_s_dP = thermo.get_dT_sat_dP(P)
    
    dh_w_dP = thermo.get_dh_w_dP(P)
    dh_s_dP = thermo.get_dh_s_dP(P)
    
    # Void fraction properties
    alpha_r = void.get_void_fraction(phi, P)
    da_dphi = void.get_d_alpha_d_phi(phi, P)
    da_dP = void.get_d_alpha_d_P(phi, P)
    
    C = np.zeros((4, 4))
    
    # Row 1: Liquid Mass Balance
    C[0, :] = water_mass.get_water_mass_coefficients(V_dw, alpha_r, da_dphi, da_dP, rho_w, drho_w_dP)
    
    # Row 2: Steam Mass Balance (below water level)
    C[1, :] = steam_below.get_steam_below_coefficients(V_dw, alpha_r, da_dphi, da_dP, rho_s, drho_s_dP)
    
    # Row 3: Global Energy Balance (whole drum, internal energy)
    C[2, :] = energy.get_energy_coefficients(
        V_dw, alpha_r, da_dphi, da_dP, rho_w, rho_s, u_w, u_s, 
        d_rho_u_w_dP, d_rho_u_s_dP, const.V_T
    )

    
    # Row 4: Steam Mass Balance (above water level)
    C[3, :] = steam_above.get_steam_above_coefficients(const.V_T, V_dw, rho_s, drho_s_dP)
    
    return C

def calculate_vector_D(P, V_dw, phi, m_w, Q_fluid, valve_opening):
    """
    Calculate the 4x1 vector D for the system CX = D.
    Inputs:
    - m_w: inlet water flow (kg/s)
    - Q_fluid: heat transfer from metal to water (W)
    - valve_opening: scale for steam exit flow
    """
    # ── Compressible Steam Flow (Orifice Equation with Choking) ──
    A_orifice = np.pi / 4.0 * const.D_PIPE**2
    rho_s = thermo.get_rho_s(P)
    
    # Isentropic expansion factor for steam
    k = 1.3
    P_up = max(P, const.P_DOWNSTREAM + 1.0) # Ensure slightly positive delta
    r = const.P_DOWNSTREAM / P_up
    
    # Critical pressure ratio
    r_c = (2.0 / (k + 1.0)) ** (k / (k - 1.0))
    
    if r <= r_c:
        # Choked Flow
        r = r_c
        
    # Compressible mass flow equation
    term = (k / (k - 1.0)) * (r**(2.0/k) - r**((k+1.0)/k))
    term = max(term, 0.0) # Safety clamp
    
    m_s = const.C_D_VALVE * A_orifice * valve_opening * np.sqrt(2.0 * P_up * rho_s * term)
    
    # ── Parasitic Leak: fitting/PRV seat leakage ──
    # Real boilers are never perfectly sealed. Small leaks through fittings,
    # gaskets, and the PRV seat allow steam to escape proportional to gauge pressure.
    # Without this, the sealed-vessel model over-predicts pressure by 3-4x.
    P_gauge_bar = max(0, (P - const.P_DOWNSTREAM)) / 1e5
    m_leak = const.K_LEAK * P_gauge_bar
    m_s = m_s + m_leak
    
    # Feed water enthalpy — IAPWS-97 subcooled liquid at T_feed and system pressure
    try:
        _fw = IAPWS97(T=const.T_FEED + 273.15, P=max(P, 101325.0) / 1e6)
        h_feed = _fw.h * 1000.0  # kJ/kg → J/kg
    except Exception:
        h_feed = 4186.0 * const.T_FEED  # Fallback: Cp approximation
    
    h_s = thermo.get_h_s(P)
    
    D = np.zeros(4)
    
    # Inter-region steam transfer (m_i for dome, output from below)
    # New mechanistic bubble rise velocity formula:
    # mi = A_drum * phi * rho_s * v_rise
    # v_rise = 1.41 * ( (sigma * g * (rho_w - rho_s)) / rho_w^2 )^0.25
    g = 9.81
    sigma = thermo.get_sigma(P)
    rho_w = thermo.get_rho_w(P)
    A_drum = np.pi / 4.0 * const.D_DRUM**2
    
    v_rise = 1.41 * ( (sigma * g * (rho_w - rho_s)) / (rho_w**2) )**0.25
    alpha_exit = void.get_exit_void_fraction(phi, P)
    transfer = A_drum * alpha_exit * rho_s * v_rise
    
    # D1: Liquid Mass Balance
    D[0] = m_w
    
    # D2: Steam Mass Balance (below water level) - Transfer term
    D[1] = - transfer
    
    # D3: Energy Balance
    # Calculate environmental heat loss
    T_water = thermo.get_T_sat(P) - 273.15
    Q_loss = const.U_LOSS * const.A_VESSEL * max(T_water - const.T_AMB, 0.0)
    
    D[2] = Q_fluid - Q_loss + m_w * h_feed - m_s * h_s
    
    # D4: Steam Mass Balance (above water level)
    # Includes m_s outflow here natively.
    D[3] = transfer - m_s
    
    return D
