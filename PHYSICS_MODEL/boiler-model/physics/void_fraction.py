import numpy as np
from physics import thermo_relations as thermo

# ═══════════════════════════════════════════════════════════════════
#  Zuber-Findlay Drift-Flux Void Fraction Model
#
#  Standard homogeneous models assume gas and liquid travel at the
#  same velocity (slip ratio S = 1). In reality, steam bubbles
#  concentrate in the faster-flowing center of the channel and rise
#  faster than the surrounding liquid.
#
#  The Zuber-Findlay drift-flux model corrects for this:
#    α_DF = α_homogeneous / C₀
#
#  where C₀ is the concentration/distribution parameter:
#    C₀ = 1.0   → homogeneous (no correction)
#    C₀ = 1.2   → standard for large vertical pipes
#    C₀ = 1.13  → validated for small-diameter vessels (D < 20cm)
#
#  Reference: Zuber, N. & Findlay, J.A. (1965), "Average Volumetric
#  Concentration in Two-Phase Flow Systems", J. Heat Transfer, 87(4).
# ═══════════════════════════════════════════════════════════════════

# Distribution parameter for small vertical vessel (D = 18cm)
# C₀ = 1.13 accounts for the radial void profile (bubbles
# concentrate at the center where velocity is highest).
# Range: 1.0 (uniform) to 1.2 (fully developed pipe flow).
C_0 = 1.13


def _alpha_homogeneous(phi, P):
    """
    Homogeneous void fraction from analytically integrated linear quality profile.
    This is the base model before drift-flux correction.
    """
    rho_w = thermo.get_rho_w(P)
    rho_s = thermo.get_rho_s(P)

    if phi < 1e-8:
        return phi * rho_w / (2.0 * rho_s)

    gamma = (rho_w - rho_s) / rho_s
    x = phi * gamma
    return (rho_w / (rho_w - rho_s)) * (1.0 - np.log(1.0 + x) / x)


def get_void_fraction(phi, P):
    """
    Calculate average void fraction α using the Zuber-Findlay drift-flux model.

    α_DF = α_homogeneous / C₀

    The C₀ correction reduces the effective void fraction because bubbles
    concentrate in the high-velocity center, meaning the cross-section-averaged
    void fraction is lower than the homogeneous assumption predicts.
    """
    alpha_h = _alpha_homogeneous(phi, P)
    # Drift-flux correction: α_DF = α_h / C₀, clamped to [0, 1)
    return min(alpha_h / C_0, 0.999)


def get_d_alpha_d_phi(phi, P):
    """
    Partial derivative of drift-flux void fraction with respect to quality phi.
    Since α_DF = α_h / C₀, the derivative is simply dα_h/dφ / C₀.
    """
    rho_w = thermo.get_rho_w(P)
    rho_s = thermo.get_rho_s(P)
    gamma = (rho_w - rho_s) / rho_s

    if phi < 1e-8:
        return rho_w / (2.0 * rho_s * C_0)

    x = phi * gamma
    # f(x) = 1 - ln(1+x)/x
    # df/dx = ln(1+x)/x^2 - 1/(x(1+x))
    df_dx = np.log(1.0 + x) / (x**2) - 1.0 / (x * (1.0 + x))

    # dα_h/dφ = (ρ_w / (ρ_w − ρ_s)) · df/dx · γ
    da_h_dphi = (rho_w / (rho_w - rho_s)) * df_dx * gamma
    return da_h_dphi / C_0


def get_d_alpha_d_P(phi, P):
    """
    Analytical partial derivative of drift-flux void fraction w.r.t. pressure P.
    Since α_DF = α_h / C₀, we have dα_DF/dP = (dα_h/dP) / C₀.

    dα_h/dP is computed via exact chain rule through ρ_w(P) and ρ_s(P).
    """
    rho_w = thermo.get_rho_w(P)
    rho_s = thermo.get_rho_s(P)
    drho_w_dP = thermo.get_drho_w_dP(P)
    drho_s_dP = thermo.get_drho_s_dP(P)

    if phi < 1e-8:
        # Taylor limit: α_h ≈ φ·ρ_w/(2·ρ_s)
        da_h_dP = phi / 2.0 * (drho_w_dP * rho_s - rho_w * drho_s_dP) / (rho_s**2)
        return da_h_dP / C_0

    delta_rho = rho_w - rho_s
    gamma = delta_rho / rho_s
    x = phi * gamma

    # f(x) = 1 − ln(1+x)/x  and  df/dx = ln(1+x)/x² − 1/(x·(1+x))
    f_x = 1.0 - np.log(1.0 + x) / x
    df_dx = np.log(1.0 + x) / (x**2) - 1.0 / (x * (1.0 + x))

    # Full chain-rule expansion for dα_h/dP
    d_delta_rho_dP = drho_w_dP - drho_s_dP
    d_ratio_dP = (drho_w_dP * delta_rho - rho_w * d_delta_rho_dP) / (delta_rho**2)
    d_gamma_dP = (drho_w_dP * rho_s - delta_rho * drho_s_dP) / (rho_s**2)
    dx_dP = phi * d_gamma_dP

    da_h_dP = f_x * d_ratio_dP + (rho_w / delta_rho) * df_dx * dx_dP
    return da_h_dP / C_0


def get_exit_void_fraction(phi, P):
    """
    Calculate the void fraction at the surface (exit) given mass quality phi.
    
    alpha_exit = (phi * rho_w) / (phi * rho_w + (1 - phi) * rho_s)
    """
    rho_w = thermo.get_rho_w(P)
    rho_s = thermo.get_rho_s(P)
    
    denom = phi * rho_w + (1.0 - phi) * rho_s
    if denom < 1e-10:
        return 0.0
    return (phi * rho_w) / denom
