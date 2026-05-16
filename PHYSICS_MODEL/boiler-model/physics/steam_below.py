"""
Steam Mass Conservation Equation (Below Water Level)

Formulates the mass conservation for the steam phase in the water region,
i.e., the steam bubbles present below the water level.

Starting point:
Accumulation = Generation - Transfer
d(M_steam)/dt = m_g - transfer

Where M_steam is expressed as:
M_steam = rho_g * V_dw * phi

Differentiating using the product rule:
d[rho_g * V_dw * phi]/dt = m_g - transfer

Applying product rule (with rho_g dependent on Pressure P):
V_dw * phi * (d(rho_g)/dP) * dP/dt
+ rho_g * phi * dV_dw/dt
+ rho_g * V_dw * dphi/dt
= m_g - transfer
"""

def get_steam_below_coefficients(V_dw, alpha, da_dphi, da_dP, rho_g, drho_g_dp):
    """
    Returns the coefficients for the C matrix corresponding to the
    steam mass conservation equation (below water level).

    The state vector formulation is assumed to be: X = [dP/dt, dV_dw/dt, dphi/dt, m_g]^T

    M_steam_below = rho_g * V_dw * alpha
    dM_steam_below/dt = (V_dw * alpha * drho_g_dp + rho_g * V_dw * da_dP) * dP/dt
                      + (rho_g * alpha) * dV_dw/dt
                      + (rho_g * V_dw * da_dphi) * dphi/dt

    Accumulation = Generation (m_g) - Transfer (m_t)
    
    Rearranging for CX = D:
    C21*dP/dt + C22*dV_dw/dt + C23*dphi/dt - 1.0*m_g = -transfer
    """
    
    # C21: Coefficient for dP/dt
    C21 = V_dw * alpha * drho_g_dp + rho_g * V_dw * da_dP
    
    # C22: Coefficient for dV_dw/dt
    C22 = rho_g * alpha
    
    # C23: Coefficient for dphi/dt
    C23 = rho_g * V_dw * da_dphi
    
    # C24: Coefficient for m_g (generation)
    C24 = -1.0

    C_coeffs = [C21, C22, C23, C24]
    
    return C_coeffs

