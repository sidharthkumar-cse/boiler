"""
Steam Mass Conservation Equation (Above Water Level)

Formulates the mass conservation for the steam phase in the steam dome,
i.e., the steam volume above the water level.

Starting point:
Accumulation = Steam Inflow (from water region) - Steam Outflow (ms)
d(M_steam_above)/dt = m_i - m_s

Where:
M_steam_above = rho_g * V_ds
V_ds = V_T - V_dw
So M_steam_above = rho_g * (V_T - V_dw)

Differentiating using the product rule:
d[rho_g * (V_T - V_dw)]/dt = m_i - m_s
(V_T - V_dw) * (d(rho_g)/dP) * dP/dt - rho_g * dV_dw/dt = m_i - m_s
"""

def get_steam_above_coefficients(V_T, V_dw, rho_g, drho_g_dp):
    """
    Returns the coefficients for the C matrix corresponding to the
    steam mass conservation equation (above water level).

    The state vector formulation is assumed to be: X = [dP/dt, dV_dw/dt, dphi/dt, m_g]^T

    Accumulation = (V_T - V_dw) * drho_g_dp * dP/dt - rho_g * dV_dw/dt
    
    Accumulation = m_i - m_s
    (m_g does not appear directly here; m_i is the steam transferred from below)
    
    Rearranging for CX = D:
    ((V_T - V_dw) * drho_g_dp)*dP/dt + (-rho_g)*dV_dw/dt + (0)*dphi/dt + (0)*m_g = m_i - m_s

    Args:
        V_T (float): Total boiler volume.
        V_dw (float): Volume of water/steam mixture below water level.
        rho_g (float): Saturated steam density.
        drho_g_dp (float): Partial derivative of steam density w.r.t pressure.

    Returns:
        tuple: (list of C coefficients [C11, C12, C13, C14])
            - C_coeffs: List of 4 floats for the C matrix row.
    """
    
    # C1: Coefficient for dP/dt
    C1 = (V_T - V_dw) * drho_g_dp
    
    # C2: Coefficient for dV_dw/dt
    C2 = -rho_g
    
    # C3: Coefficient for dphi/dt
    C3 = 0.0
    
    # C4: Coefficient for m_g (generation)
    C4 = 0.0

    C_coeffs = [C1, C2, C3, C4]
    
    return C_coeffs
