import numpy as np
from scipy.linalg import expm
from core import matrix_form as model

def get_state_derivatives(P, V_dw, phi, m_w, Q, valve_opening):
    """ Helper to get [dP/dt, dVdw/dt, dphi/dt] from the solver. """
    X = model.solve_system(P, V_dw, phi, m_w, Q, valve_opening)
    return np.array(X[:3])

def compute_jacobian(P_op, Vdw_op, phi_op, m_w, Q, valve_opening):
    """
    Computes the 3x3 Jacobian matrix A = df/dx evaluated at x_op.
    x = [P, V_dw, phi]^T
    Uses central numerical finite differences.
    """
    # Small perturbations designed for the relative scale of each state
    eps_P = 1e3     # 0.01 bar (nominal P is 50e5)
    eps_V = 1e-3    # 1 liter (nominal volume ~ 10.0)
    eps_phi = 1e-4  # 0.01% (nominal phi ~ 0.1)
    
    epsilons = [eps_P, eps_V, eps_phi]
    x_op = np.array([P_op, Vdw_op, phi_op])
    
    A = np.zeros((3, 3))
    
    # df/dx_j using central differences
    for j in range(3):
        x_plus = x_op.copy()
        x_minus = x_op.copy()
        
        x_plus[j] += epsilons[j]
        x_minus[j] -= epsilons[j]
        
        f_plus = get_state_derivatives(x_plus[0], x_plus[1], x_plus[2], m_w, Q, valve_opening)
        f_minus = get_state_derivatives(x_minus[0], x_minus[1], x_minus[2], m_w, Q, valve_opening)
        
        A[:, j] = (f_plus - f_minus) / (2.0 * epsilons[j])
        
    return A

def predict_linear_jump(P_init, Vdw_init, phi_init, op_state, op_inputs, duration=300.0):
    """
    Predicts the future state at t+duration using the analytical matrix exponential transition.
    Equation: x(t + dt) = x_op + exp(A * dt) * (x_init - x_op)
    
    op_state: tuple (P_op, Vdw_op, phi_op) representing the equilibrium center point.
    op_inputs: tuple (m_w, Q, valve_opening) representing constant inputs.
    duration: Prediction horizon in seconds.
    """
    P_op, Vdw_op, phi_op = op_state
    m_w, Q, valve_opening = op_inputs
    
    # 1. Compute Jacobian A-matrix at op
    A = compute_jacobian(P_op, Vdw_op, phi_op, m_w, Q, valve_opening)
    
    # 2. Extract initial state deviations
    x_init = np.array([P_init, Vdw_init, phi_init])
    x_op = np.array([P_op, Vdw_op, phi_op])
    dx_0 = x_init - x_op
    
    # 3. Compute continuous transition matrix exp(A * t)
    T = expm(A * duration)
    
    # 4. Project deviation forward: dx_t = T * dx_0
    dx_f = T @ dx_0
    
    # 5. Recover absolute final projected state
    x_f = x_op + dx_f
    
    P_f = x_f[0]
    Vdw_f = x_f[1]
    phi_f = x_f[2]
    
    # Defend boundaries
    if P_f < 1.0: P_f = 1.0
    if Vdw_f < 0.0: Vdw_f = 0.0
    if phi_f < 0.0: phi_f = 0.0
    elif phi_f > 1.0: phi_f = 1.0
        
    # Convert outputs at final step
    L_f = model.calculate_drum_level(Vdw_f, phi_f, P_f)
    T_f = model.calculate_temperature(P_f)
    
    return P_f, Vdw_f, phi_f, L_f, T_f
