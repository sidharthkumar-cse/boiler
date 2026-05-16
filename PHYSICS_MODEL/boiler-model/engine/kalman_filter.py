"""
Extended Kalman Filter (EKF) for Boiler Sensor-Model Fusion

Fuses noisy ESP32 sensor readings with physics model predictions
to produce an optimal state estimate. This replaces the raw
sensor → ODE init pipeline with a persistent, recursive estimator.

State vector:  x = [T (°C), P_abs (bar), V_water (L)]
Measurement:   z = [T_sensor, P_sensor, V_flow_integrated]

The process model uses the boiler physics engine's predict_forward()
as the nonlinear state transition function, making this a true EKF.

Theory:
  PREDICT:  x̂⁻ = f(x̂, u)          (physics model propagation)
            P⁻  = F·P·Fᵀ + Q       (covariance propagation)
  UPDATE:   K   = P⁻·Hᵀ·(H·P⁻·Hᵀ + R)⁻¹   (Kalman gain)
            x̂   = x̂⁻ + K·(z − H·x̂⁻)          (fused state)
            P   = (I − K·H)·P⁻                (updated covariance)

Reference: Welch & Bishop, "An Introduction to the Kalman Filter", UNC-CH TR 95-041
"""

import numpy as np
import time
import threading
import math
import physics.thermo_relations as thermo


class BoilerEKF:
    """
    3-State Extended Kalman Filter for real-time boiler state estimation.

    States:
      x[0] = T       — Water temperature (°C)
      x[1] = P_abs   — Absolute pressure (bar)
      x[2] = V_water — Water volume in boiler (Liters)

    Design philosophy:
      - The PREDICT step uses the physics model to propagate the state
        forward by dt seconds, given current inputs (Q, m_w, valve).
      - The UPDATE step fuses the prediction with the sensor measurement.
      - If the filter diverges or errors, it resets gracefully to raw sensors.
    """

    def __init__(self):
        # ── State vector: [T (°C), P_abs (bar), V_water (L)] ──
        self.x = np.array([25.0, 1.013, 4.5])   # Initial estimate
        self.n = 3                                # State dimension

        # ── Error Covariance P (initial uncertainty) ──
        # Diagonal: we start uncertain about all states
        self.P = np.diag([
            4.0,     # ±2°C initial temperature uncertainty
            0.01,    # ±0.1 bar initial pressure uncertainty
            0.25,    # ±0.5 L initial volume uncertainty
        ])

        # ── Process Noise Q (model uncertainty per second) ──
        # How much the physics model could be wrong per timestep.
        # Tuned for a 1-2 second update cycle.
        self.Q_noise = np.diag([
            0.05,    # T: model could drift ~0.2°C/s due to unmodeled losses
            0.0001,  # P: pressure model is highly accurate
            0.001,   # V: flow integration could drift ~0.03 L/s
        ])

        # ── Measurement Noise R (sensor uncertainty) ──
        # From sensor datasheets and empirical observation.
        self.R = np.diag([
            0.25,    # PT100/thermocouple: ±0.5°C (σ² = 0.25)
            0.0004,  # ADS1115 pressure: ±0.02 bar after smoothing (σ² = 0.0004)
            0.04,    # Flow integration: ±0.2 L cumulative (σ² = 0.04)
        ])

        # ── Observation matrix H (identity — we directly observe all states) ──
        self.H = np.eye(self.n)

        # ── Timing ──
        self.last_update_time = None
        self.initialized = False

        # ── Diagnostics ──
        self.innovation = np.zeros(self.n)       # z − Hx̂⁻ (prediction error)
        self.kalman_gain_norms = np.zeros(self.n) # Diagonal of K (trust ratio)
        self.covariance_trace = 0.0               # tr(P) — overall uncertainty
        self.n_updates = 0
        self.n_resets = 0
        self.lock = threading.Lock()

        # ── Physics model reference (set externally) ──
        self._predict_fn = None
        self._compute_init_fn = None

    def set_physics_model(self, predict_forward_fn, compute_initial_state_fn):
        """
        Inject the physics model functions for the predict step.
        Called once during initialization in serial_proxy.py.
        """
        self._predict_fn = predict_forward_fn
        self._compute_init_fn = compute_initial_state_fn

    def predict(self, Q_watts, m_w_kgs, valve_opening, water_mass_kg, dt):
        """
        EKF PREDICT step: propagate state forward using the physics model.

        Uses predict_forward() for a short dt-second horizon.
        The Jacobian F is computed via finite differences (since the
        physics model is a complex nonlinear system).
        """
        if self._predict_fn is None or self._compute_init_fn is None:
            return  # No physics model attached — skip predict

        if dt <= 0 or dt > 30:
            return  # Invalid timestep

        T_cur, P_abs_bar, V_cur_L = self.x

        try:
            # ── Propagate state through physics model ──
            P_init_pa = P_abs_bar * 1e5

            # Derive ODE initial conditions from current Kalman state
            # Convert V(L) to mass(kg) using actual density at T_cur, NOT saturation density at P_init
            rho_w_curr = thermo.get_rho_w_subcooled(P_init_pa, T_cur)
                
            Vdw, phi, _ = self._compute_init_fn(
                T_celsius=T_cur,
                P_pa=P_init_pa,
                water_mass_kg=max(0.5, V_cur_L * (rho_w_curr / 1000.0))  # V(L) → mass(kg)
            )

            P_f, Vdw_f, phi_f, L_f, T_f, _ = self._predict_fn(
                P_init=P_init_pa,
                Vdw_init=Vdw,
                phi_init=phi,
                m_w=m_w_kgs,
                Q=Q_watts,
                valve_opening=valve_opening,
                T_init=T_cur,
                duration=dt
            )

            # Convert back to state units
            x_predicted = np.array([
                T_f,                           # °C
                max(P_f / 1e5, 0.5),           # Pa → bar (floor at 0.5 bar)
                max(Vdw_f * 1000.0, 0.1),      # m³ → Liters (floor at 0.1 L)
            ])

            # ── Numerical Jacobian F via finite differences ──
            # F[i,j] = ∂f_i/∂x_j ≈ (f(x+δe_j) − f(x−δe_j)) / (2δ)
            eps = np.array([0.1, 0.001, 0.01])  # Perturbation per state
            F = np.eye(self.n)
            for j in range(self.n):
                x_plus = self.x.copy()
                x_plus[j] += eps[j]
                x_minus = self.x.copy()
                x_minus[j] -= eps[j]

                # Forward perturbed
                rho_w_plus = thermo.get_rho_w_subcooled(x_plus[1] * 1e5, x_plus[0])
                Vdw_p, phi_p, _ = self._compute_init_fn(
                    T_celsius=x_plus[0], P_pa=x_plus[1]*1e5,
                    water_mass_kg=max(0.5, x_plus[2] * (rho_w_plus / 1000.0))
                )
                P_fp, Vdw_fp, _, _, T_fp, _ = self._predict_fn(
                    P_init=x_plus[1]*1e5, Vdw_init=Vdw_p, phi_init=phi_p,
                    m_w=m_w_kgs, Q=Q_watts, valve_opening=valve_opening,
                    T_init=x_plus[0], duration=dt
                )
                f_plus = np.array([T_fp, max(P_fp/1e5, 0.5), max(Vdw_fp * 1000.0, 0.1)])

                # Backward perturbed
                rho_w_minus = thermo.get_rho_w_subcooled(x_minus[1] * 1e5, x_minus[0])
                Vdw_m, phi_m, _ = self._compute_init_fn(
                    T_celsius=x_minus[0], P_pa=x_minus[1]*1e5,
                    water_mass_kg=max(0.5, x_minus[2] * (rho_w_minus / 1000.0))
                )
                P_fm, Vdw_fm, _, _, T_fm, _ = self._predict_fn(
                    P_init=x_minus[1]*1e5, Vdw_init=Vdw_m, phi_init=phi_m,
                    m_w=m_w_kgs, Q=Q_watts, valve_opening=valve_opening,
                    T_init=x_minus[0], duration=dt
                )
                f_minus = np.array([T_fm, max(P_fm/1e5, 0.5), max(Vdw_fm * 1000.0, 0.1)])

                F[:, j] = (f_plus - f_minus) / (2.0 * eps[j])

            # ── Covariance propagation ──
            # Scale process noise by dt (longer steps = more uncertainty)
            Q_scaled = self.Q_noise * dt
            self.P = F @ self.P @ F.T + Q_scaled

            # ── State propagation ──
            self.x = x_predicted

        except Exception as e:
            # Physics model failed — fall back to identity propagation
            # (state stays the same, covariance grows)
            self.P += self.Q_noise * dt

    def update(self, z):
        """
        EKF UPDATE step: fuse sensor measurement z with predicted state.

        z = [T_sensor (°C), P_abs_sensor (bar), V_water_sensor (L)]

        The Kalman gain K determines how much to trust the sensor vs model:
          K ≈ 0 → trust the model (sensor is noisy)
          K ≈ 1 → trust the sensor (model is uncertain)
        """
        z = np.array(z, dtype=float)

        # ── Innovation (measurement residual) ──
        y = z - self.H @ self.x   # z − Hx̂⁻

        # ── Innovation covariance ──
        S = self.H @ self.P @ self.H.T + self.R

        # ── Kalman gain ──
        try:
            K = self.P @ self.H.T @ np.linalg.inv(S)
        except np.linalg.LinAlgError:
            # Singular S — skip this update
            return

        # ── State update ──
        self.x = self.x + K @ y

        # ── Covariance update (Joseph form for numerical stability) ──
        I_KH = np.eye(self.n) - K @ self.H
        self.P = I_KH @ self.P @ I_KH.T + K @ self.R @ K.T

        # ── Physical sanity clamps ──
        from config import constants as const
        self.x[0] = max(0.0, min(self.x[0], 200.0))    # T: 0–200 °C
        self.x[1] = max(0.5, min(self.x[1], 12.0))     # P: 0.5–12 bar
        self.x[2] = max(2.0, min(self.x[2], const.V_T * 1000.0)) # V: 2L floor — boiler always has water

        # ── Store diagnostics ──
        self.innovation = y
        self.kalman_gain_norms = np.diag(K)
        self.covariance_trace = np.trace(self.P)
        self.n_updates += 1

    def predict_and_update(self, z_T, z_P_abs, z_V_L, Q_watts, m_w_kgs,
                           valve_opening, water_mass_kg):
        """
        Combined predict-update cycle. Called every sensor reading (~1 Hz).

        Args:
            z_T:            Sensor temperature (°C)
            z_P_abs:        Sensor absolute pressure (bar)
            z_V_L:          Tracked water volume (Liters)
            Q_watts:        Current heater power (W)
            m_w_kgs:        Current feedwater flow (kg/s)
            valve_opening:  Valve opening fraction (0–1)
            water_mass_kg:  Current water mass (kg)
        """
        with self.lock:
            now = time.time()

            if not self.initialized:
                # First call — seed the filter with sensor values
                self.x = np.array([z_T, z_P_abs, z_V_L])
                self.initialized = True
                self.last_update_time = now
                self.n_updates = 1
                return

            dt = now - self.last_update_time
            self.last_update_time = now

            if dt <= 0 or dt > 30:
                dt = 2.0  # Default to 2s if timestamp is bad

            # ── Divergence detection ──
            # If the innovation is absurdly large, reset the filter
            z = np.array([z_T, z_P_abs, z_V_L])
            pre_innovation = z - self.x
            if (abs(pre_innovation[0]) > 50.0 or   # >50°C temp jump
                abs(pre_innovation[1]) > 2.0 or     # >2 bar pressure jump
                abs(pre_innovation[2]) > 3.0):       # >3 L volume jump
                # Filter has diverged — hard reset
                self.x = z.copy()
                self.P = np.diag([4.0, 0.01, 0.25])
                self.n_resets += 1
                return

            # ── EKF cycle ──
            try:
                self.predict(Q_watts, m_w_kgs, valve_opening, water_mass_kg, dt)
                self.update(z)
            except Exception as e:
                # Any failure — fall back to raw sensors
                self.x = z.copy()
                self.n_resets += 1

    def get_fused_state(self):
        """
        Return the current fused state estimate.

        Returns:
            dict with:
              T_fused:  Optimal temperature estimate (°C)
              P_fused:  Optimal absolute pressure estimate (bar)
              V_fused:  Optimal water volume estimate (L)
        """
        with self.lock:
            return {
                "T_fused": round(float(self.x[0]), 2),
                "P_fused": round(float(self.x[1]), 4),
                "V_fused": round(float(self.x[2]), 3),
            }

    def get_metrics(self):
        """
        Return diagnostic metrics for the dashboard.
        """
        with self.lock:
            return {
                "enabled": self.initialized,
                "n_updates": self.n_updates,
                "n_resets": self.n_resets,
                "fused_T": round(float(self.x[0]), 2),
                "fused_P": round(float(self.x[1]), 4),
                "fused_V": round(float(self.x[2]), 3),
                "innovation_T": round(float(self.innovation[0]), 3),
                "innovation_P": round(float(self.innovation[1]), 4),
                "innovation_V": round(float(self.innovation[2]), 3),
                "gain_T": round(float(self.kalman_gain_norms[0]), 3),
                "gain_P": round(float(self.kalman_gain_norms[1]), 3),
                "gain_V": round(float(self.kalman_gain_norms[2]), 3),
                "covariance_trace": round(float(self.covariance_trace), 4),
                "uncertainty_T": round(float(math.sqrt(max(0, self.P[0, 0]))), 3),
                "uncertainty_P": round(float(math.sqrt(max(0, self.P[1, 1]))), 4),
                "uncertainty_V": round(float(math.sqrt(max(0, self.P[2, 2]))), 3),
            }
