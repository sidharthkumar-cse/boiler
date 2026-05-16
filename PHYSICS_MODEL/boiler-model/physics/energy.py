"""
Energy Conservation Equation (First Law)

Formulates the global energy conservation for the entire boiler volume,
using pure internal energy (u) instead of enthalpy (h), satisfying the First Law 
of Thermodynamics for a constant-volume system.

U_total = U_liquid + U_steam_below + U_steam_dome
U_total = (rho_w * u_w) * V_dw * (1 - phi) + 
          (rho_s * u_s) * V_dw * phi + 
          (rho_s * u_s) * (V_T - V_dw)

Differentiating U_total via product rule:
dU/dt = C1 * dP/dt + C2 * dV_dw/dt + C3 * dphi/dt
"""

def get_energy_coefficients(V_dw, alpha, da_dphi, da_dP, rho_w, rho_s, u_w, u_s, 
                            d_rho_u_w_dP, d_rho_u_s_dP, V_T):
    """
    Returns the coefficients for the C matrix corresponding to the
    global energy conservation equation (water region + steam dome).

    The state vector formulation is assumed to be: X = [dP/dt, dV_dw/dt, dphi/dt, m_g]^T

    U_total = V_dw * [rho_w*u_w + alpha*(rho_s*u_s - rho_w*u_w)] + (V_T - V_dw)*(rho_s*u_s)
    
    dU_total/dt = C31*dP/dt + C32*dV_dw/dt + C33*dphi/dt
    """
    e_w = rho_w * u_w
    e_s = rho_s * u_s
    de_w_dP = d_rho_u_w_dP
    de_s_dP = d_rho_u_s_dP
    
    # C31: Coefficient for dP/dt
    # accumulation = dU/dP * dP/dt
    C31 = V_dw * (de_w_dP + alpha * (de_s_dP - de_w_dP) + (e_s - e_w) * da_dP) + (V_T - V_dw) * de_s_dP
    
    # C32: Coefficient for dV_dw/dt
    # accumulation = dU/dV_dw * dV_dw/dt
    C32 = (1.0 - alpha) * (e_w - e_s)
    
    # C33: Coefficient for dphi/dt
    # accumulation = dU/dphi * dphi/dt
    C33 = V_dw * (e_s - e_w) * da_dphi
    
    # C34: Coefficient for m_g (generation)
    C34 = 0.0

    C_coeffs = [C31, C32, C33, C34]
    
    return C_coeffs

