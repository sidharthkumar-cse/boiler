import sys
import os

# Add parent directory to path to allow imports
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
from scipy.integrate import solve_ivp
from core import matrix_form as model
from config import constants as const
from engine.solver_logic import system_derivatives

def run_simulation(duration=500, dt=1.0):
    """
    Run a dynamic simulation of the boiler using Scipy integrate.
    Scenario: Step increase in heat input Q at t=50.
    """
    # Time vector
    t_eval = np.arange(0, duration, dt)
    n = len(t_eval)
    
    # Store results precisely aligned with t_eval
    P_hist = np.zeros(n)
    L_hist = np.zeros(n)
    T_hist = np.zeros(n)
    phi_hist = np.zeros(n)
    Vdw_hist = np.zeros(n)
    mg_hist = np.zeros(n)
    
    # Initial State
    P0 = 50e5
    m_s_target = 10.0
    phi0 = m_s_target / const.M_DC
    V_dw0 = 1.0 * const.A_D
    
    # Inputs
    m_w = 10.0
    valve_opening = 1.0
    from physics import thermo_relations as thermo
    h_s = thermo.get_h_s(P0)
    h_feed = 4186.0 * const.T_FEED
    Q = m_s_target * h_s - m_w * h_feed
    
    # Simulate first 50 seconds (pre-step)
    t_span1 = (0, 50)
    t_eval1 = t_eval[t_eval <= 50]
    
    sol1 = solve_ivp(
        fun=lambda t, y: system_derivatives(t, y, m_w, Q, valve_opening),
        t_span=t_span1,
        y0=[P0, V_dw0, phi0],
        method='Radau',
        t_eval=t_eval1
    )
    
    # Extract results and populate arrays
    idx1 = len(t_eval1)
    
    P_hist[:idx1] = sol1.y[0]
    Vdw_hist[:idx1] = sol1.y[1]
    phi_hist[:idx1] = sol1.y[2]
    
    # Simulate remaining time (post-step)
    Q_applied = Q * 1.1 # 10% step increase
    t_span2 = (50, duration)
    t_eval2 = t_eval[t_eval > 50]
    
    if len(t_eval2) > 0:
        y0_2 = sol1.y[:, -1] # Last state of segment 1 safely passed
        sol2 = solve_ivp(
            fun=lambda t, y: system_derivatives(t, y, m_w, Q_applied, valve_opening),
            t_span=t_span2,
            y0=y0_2,
            method='Radau',
            t_eval=t_eval2
        )
        P_hist[idx1:] = sol2.y[0]
        Vdw_hist[idx1:] = sol2.y[1]
        phi_hist[idx1:] = sol2.y[2]
        
    # Boundary clamps applied to history arrays for physics consistency before calculating dependents
    P_hist = np.maximum(P_hist, 1.0)
    Vdw_hist = np.maximum(Vdw_hist, 0.0)
    phi_hist = np.clip(phi_hist, 0.0, 1.0)
    
    # Map back output states (L, T, mg) over the time series
    for i in range(n):
        P = P_hist[i]
        V_dw = Vdw_hist[i]
        phi = phi_hist[i]
        
        Q_current = Q_applied if t_eval[i] > 50 else Q
        
        L_hist[i] = model.calculate_drum_level(V_dw, phi, P)
        T_hist[i] = model.calculate_temperature(P)
        
        # Recalculating dX simply to grab m_g
        X = model.solve_system(P, V_dw, phi, m_w, Q_current, valve_opening)
        mg_hist[i] = X[3]
        
    return t_eval, P_hist, L_hist, T_hist, mg_hist

def plot_results(t, P, L, T, mg):
    fig, axs = plt.subplots(2, 2, figsize=(12, 8))
    
    axs[0, 0].plot(t, P / 1e5)
    axs[0, 0].set_title('Drum Pressure (bar)')
    axs[0, 0].grid(True)
    
    axs[0, 1].plot(t, L)
    axs[0, 1].set_title('Water Level (m)')
    axs[0, 1].grid(True)
    
    axs[1, 0].plot(t, T)
    axs[1, 0].set_title('Saturation Temperature (C)')
    axs[1, 0].grid(True)
    
    axs[1, 1].plot(t, mg)
    axs[1, 1].set_title('Evaporation Rate (kg/s)')
    axs[1, 1].grid(True)
    
    plt.tight_layout()
    plt.savefig('results/simulation_results.png')
    print("Simulation results saved to results/simulation_results.png")

if __name__ == "__main__":
    t, P, L, T, mg = run_simulation()
    plot_results(t, P, L, T, mg)
