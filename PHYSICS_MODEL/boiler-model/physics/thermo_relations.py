import numpy as np
from scipy.interpolate import CubicSpline
from iapws import IAPWS97

# ============================================================
# Thermodynamic Property Functions using Splines
# Greatly accelerates SciPy's solve_ivp ODE solvers.
# Valid Range: 0.05 bar (5000 Pa) to 30 bar (3,000,000 Pa)
# Units: P in Pa, T in K, rho in kg/m^3, h in J/kg
# ============================================================

# --- Precompute Tables on Import ---
_P_MIN = 4000.0  # 4 kPa
_P_MAX = 3500000.0  # 35 bar
_N_POINTS = 500
_P_nodes = np.linspace(_P_MIN, _P_MAX, _N_POINTS)

_T_sat_arr = np.zeros(_N_POINTS)
_rho_w_arr = np.zeros(_N_POINTS)
_rho_s_arr = np.zeros(_N_POINTS)
_h_w_arr = np.zeros(_N_POINTS)
_h_s_arr = np.zeros(_N_POINTS)

for i, P in enumerate(_P_nodes):
    s_l = IAPWS97(P=P/1e6, x=0)
    s_v = IAPWS97(P=P/1e6, x=1)
    _T_sat_arr[i] = s_l.T
    _rho_w_arr[i] = s_l.rho
    _rho_s_arr[i] = s_v.rho
    _h_w_arr[i] = s_l.h * 1000.0
    _h_s_arr[i] = s_v.h * 1000.0

# Create Splines
_spline_T_sat = CubicSpline(_P_nodes, _T_sat_arr, bc_type='natural', extrapolate=True)
_spline_rho_w = CubicSpline(_P_nodes, _rho_w_arr, bc_type='natural', extrapolate=True)
_spline_rho_s = CubicSpline(_P_nodes, _rho_s_arr, bc_type='natural', extrapolate=True)
_spline_h_w   = CubicSpline(_P_nodes, _h_w_arr, bc_type='natural', extrapolate=True)
_spline_h_s   = CubicSpline(_P_nodes, _h_s_arr, bc_type='natural', extrapolate=True)

# Derivatives (Exact from splines)
_deriv_T_sat = _spline_T_sat.derivative(1)
_deriv_rho_w = _spline_rho_w.derivative(1)
_deriv_rho_s = _spline_rho_s.derivative(1)
_deriv_h_w   = _spline_h_w.derivative(1)
_deriv_h_s   = _spline_h_s.derivative(1)

# Reverse spline: P_sat(T) — saturation pressure from temperature
# Built from the same data but with T as the independent variable
_spline_P_sat = CubicSpline(_T_sat_arr, _P_nodes, bc_type='natural', extrapolate=True)


# --- Saturation Temperature ---

def get_T_sat(P):
    """Saturation temperature (K) at pressure P (Pa)."""
    return float(_spline_T_sat(P))

def get_dT_sat_dP(P):
    """dT_sat/dP via exact spline derivative."""
    return float(_deriv_T_sat(P))

def get_P_sat(T_K):
    """Saturation pressure (Pa) at temperature T (K). Inverse of get_T_sat."""
    return float(_spline_P_sat(T_K))


# --- Liquid Density ---

def get_rho_w(P):
    """Saturated liquid density (kg/m^3) at pressure P (Pa)."""
    return float(_spline_rho_w(P))

def get_drho_w_dP(P):
    """d(rho_w)/dP via exact spline derivative."""
    return float(_deriv_rho_w(P))

def get_rho_w_subcooled(P_pa, T_C):
    """Accurate liquid density (kg/m^3) at any pressure and temperature."""
    T_K = T_C + 273.15
    P_MPa = P_pa / 1e6
    try:
        # Prevent EKF noise from crossing the saturation line and returning steam density
        T_sat = get_T_sat(P_pa)
        if T_K >= T_sat:
            return get_rho_w(P_pa)
            
        water = IAPWS97(T=T_K, P=P_MPa)
        if water.rho < 500.0: # Safeguard against returning vapor density
            return get_rho_w(P_pa)
        return float(water.rho)
    except Exception:
        # Fallback to saturated density if T_K is somehow out of bounds
        return get_rho_w(P_pa)



# --- Steam Density ---

def get_rho_s(P):
    """Saturated steam density (kg/m^3) at pressure P (Pa)."""
    return float(_spline_rho_s(P))

def get_drho_s_dP(P):
    """d(rho_s)/dP via exact spline derivative."""
    return float(_deriv_rho_s(P))


# --- Liquid Enthalpy ---

def get_h_w(P):
    """Saturated liquid enthalpy (J/kg) at pressure P (Pa)."""
    return float(_spline_h_w(P))

def get_dh_w_dP(P):
    """d(h_w)/dP via exact spline derivative."""
    return float(_deriv_h_w(P))


# --- Steam Enthalpy ---

def get_h_s(P):
    """Saturated steam enthalpy (J/kg) at pressure P (Pa)."""
    return float(_spline_h_s(P))

def get_dh_s_dP(P):
    """d(h_s)/dP via exact spline derivative."""
    return float(_deriv_h_s(P))


# --- Internal Energy ---

def get_u_w(P):
    """Saturated liquid specific internal energy (J/kg)."""
    rho = get_rho_w(P)
    h = get_h_w(P)
    return h - P / rho

def get_u_s(P):
    """Saturated steam specific internal energy (J/kg)."""
    rho = get_rho_s(P)
    h = get_h_s(P)
    return h - P / rho

def get_d_rho_u_w_dP(P):
    """d(rho_w * u_w)/dP = d(rho_w * h_w - P)/dP = rho*dh/dP + h*drho/dP - 1"""
    rho = get_rho_w(P)
    h = get_h_w(P)
    drho = get_drho_w_dP(P)
    dh = get_dh_w_dP(P)
    return rho * dh + h * drho - 1.0

def get_d_rho_u_s_dP(P):
    """d(rho_s * u_s)/dP = rho*dh/dP + h*drho/dP - 1"""
    rho = get_rho_s(P)
    h = get_h_s(P)
    drho = get_drho_s_dP(P)
    dh = get_dh_s_dP(P)
    return rho * dh + h * drho - 1.0

# --- Latent Heat ---

def get_h_fg(P):
    """Latent heat of vaporization (J/kg) at pressure P (Pa)."""
    return get_h_s(P) - get_h_w(P)

# --- Surface Tension (Water) ---

def get_sigma(P):
    """
    Surface tension of water (N/m) at saturation pressure P (Pa).
    Uses the IAPWS standard formulation.
    """
    T = get_T_sat(P)
    T_crit = 647.096 # K
    tau = 1.0 - T / T_crit
    # IAPWS Release on Surface Tension (1994)
    sigma = 0.2358 * tau**1.256 * (1.0 - 0.625 * tau)
    return max(1e-6, float(sigma))

# --- Thermal Conductivity (Liquid Water) ---

def get_k_l(P, T_C):
    """
    Thermal conductivity of liquid water (W/(m·K)) at T_C (°C) and P (Pa).
    Simple accurate fit for the operational range.
    """
    T = float(T_C) + 273.15
    return 0.6065 + 0.0012 * T_C - 0.000008 * T_C**2
