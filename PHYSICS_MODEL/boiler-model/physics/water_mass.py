"""
Water Mass Conservation Equation

Formulates the mass conservation for the liquid water phase in the drum/risers.

Starting point:
Accumulation = Inflow - Evaporation
d(M_liquid)/dt = W_fw - W_ev

Where M_liquid is expressed as:
M_liquid = rho_f * V_dw * (1 - phi)

Differentiating using the product rule:
d[rho_f * V_dw * (1 - phi)]/dt = W_fw - W_ev

Applying product rule (with rho_f dependent on Pressure P):
V_dw * (1 - phi) * d(rho_f)/dP * dP/dt  
+ rho_f * (1 - phi) * dV_dw/dt  
- rho_f * V_dw * dphi/dt  
= W_fw - W_ev
"""

def get_water_mass_coefficients(V_dw, alpha, da_dphi, da_dP, rho_f, drhof_dp):
    """
    Returns the coefficients for the C matrix corresponding to the
    water mass conservation equation and the RHS D matrix value.

    The state vector formulation is assumed to be: X = [dP/dt, dV_dw/dt, dphi/dt, m_g]^T

    M_liquid = rho_f * V_dw * (1 - alpha)
    dM_liquid/dt = d/dt [rho_f * V_dw * (1 - alpha)]
                 = (V_dw * (1 - alpha) * drhof_dp - rho_f * V_dw * da_dP) * dP/dt
                 + (rho_f * (1 - alpha)) * dV_dw/dt
                 - (rho_f * V_dw * da_dphi) * dphi/dt

    Accumulation = Inflow (m_w) - Evaporation (m_g)
    
    Rearranging for CX = D:
    C11*dP/dt + C12*dV_dw/dt + C13*dphi/dt + 1.0*m_g = m_w
    """
    
    # C11: Coefficient for dP/dt
    C11 = V_dw * (1.0 - alpha) * drhof_dp - rho_f * V_dw * da_dP
    
    # C12: Coefficient for dV_dw/dt
    C12 = rho_f * (1.0 - alpha)
    
    # C13: Coefficient for dphi/dt
    C13 = -rho_f * V_dw * da_dphi
    
    # C14: Coefficient for m_g
    C14 = 1.0

    C_coeffs = [C11, C12, C13, C14]
    
    return C_coeffs

