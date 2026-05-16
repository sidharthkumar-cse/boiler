# Boiler Digital Twin — Technical Documentation
## Thermax InnoMax Innovation Challenge 2026

> **Author:** Aryan Chauhan  
> **Date:** April 2026  
> **Project:** Physics-Based Digital Twin for Industrial Boiler Monitoring and Predictive Control

---

## 1. Executive Summary

This project implements a **first-principles physics-based digital twin** of an industrial boiler that predicts temperature, pressure, and water level in real-time. Unlike machine learning approaches, the system solves the actual thermodynamic conservation equations (mass, energy, momentum) using a 4-equation Index-1 Differential-Algebraic Equation (DAE) system.

### Key Results

| Metric | Value |
|--------|-------|
| Temperature RMSE | 2.01 °C |
| Temperature MAPE | 0.46% |
| Pressure MAPE | 1.16% |
| Mass Conservation | 100% (proven) |
| Second Law Compliance | 100% (proven) |
| Model Consistency | 1000/1000 tests passed |
| Prediction Speed | 12.6 ms per evaluation |

---

## 2. System Architecture

```
┌─────────────────┐     Serial      ┌──────────────────┐     HTTP      ┌────────────────────┐
│   ESP32 MCU     │ ──────────────> │  Serial Proxy    │ ──────────> │   Next.js Dashboard  │
│  (Hardware)     │    115200 baud  │  (Python)        │   REST API  │   (TypeScript)       │
│                 │                 │                  │             │                      │
│ • PT100 (RTD)   │                 │ • Median/MAD     │             │ • Real-time charts   │
│ • ADS1115 (ADC) │                 │   filtering      │             │ • 3D heatmaps        │
│ • Flow meter    │                 │ • Physics engine  │             │ • Predictive forecast│
│ • SSR (heater)  │                 │ • Kalman filter   │             │ • Autopilot control  │
│ • Float switch  │                 │ • CSV logging     │             │ • Live validation    │
└─────────────────┘                 └──────────────────┘             └────────────────────┘
```

### Data Flow

```
Sensor Reading → Firmware EMA → Serial TX → Median/MAD Filter → EKF Fusion → Physics Model → Dashboard
     (1 Hz)       (α=0.15)      (115200)     (5-sample)        (Kalman)     (Radau ODE)     (React)
```

---

## 3. Governing Equations

### 3.1 State Variables

The DAE system tracks 4 state variables:

| Symbol | Variable | Unit | Description |
|--------|----------|------|-------------|
| P | Pressure | Pa | Absolute pressure in the drum |
| V_dw | Downcomer volume | m³ | Total liquid+bubble mixture volume |
| φ | Exit quality | — | Mass fraction of steam (0–1) |
| T_wall | Wall temperature | °C | Metal heating element temperature |

### 3.2 Conservation Laws

The core physics are derived from three fundamental conservation laws applied to a control volume (the boiler drum):

#### Mass Conservation (First Law of Thermodynamics — Mass)

$$\frac{dM_{total}}{dt} = \dot{m}_{fw} - \dot{m}_s$$

Where total mass $M = ρ_w V_{dw}(1-α) + ρ_s V_{dw} α + ρ_s(V_T - V_{dw})$ 

Expanding via the product rule gives the first three rows of the C·X = D matrix system.

#### Energy Conservation (First Law — Energy)

$$\frac{dE_{total}}{dt} = Q_{heater} - Q_{loss} - \dot{m}_s h_s + \dot{m}_{fw} h_{fw}$$

#### Metal Wall Energy Balance

$$M_m C_m \frac{dT_{wall}}{dt} = Q_{heater} - Q_{transfer} - Q_{wall\_loss}$$

Where:
- $Q_{transfer} = U_{eff} \cdot A_{heater} \cdot (T_{wall} - T_{water})$ — wall-to-water heat transfer
- $U_{eff} = 1/(1/H_{total} + R_{fouling})$ — effective heat transfer coefficient
- $H_{total} = H_{conv} + H_{boil}$ — combined convection + boiling coefficient

### 3.3 Matrix Formulation: C · X = D

The DAE system is cast in matrix form where:

$$C \cdot \begin{bmatrix} dP/dt \\ dV_{dw}/dt \\ dφ/dt \\ \dot{m}_g \end{bmatrix} = D$$

**C matrix (4×4):**

Row 1: Liquid mass conservation  
Row 2: Steam mass conservation (below swell level)  
Row 3: Energy conservation  
Row 4: Steam mass conservation (above swell level)  

**Row Scaling:** Each row is normalized by its largest element to reduce the condition number from O(10¹⁴) to O(10⁶), addressing the extreme density ratio ρ_w/ρ_s ≈ 1600.

### 3.4 Constitutive Correlations

| Correlation | Application | Reference |
|-------------|-------------|-----------|
| **Thom (1966)** | Nucleate boiling heat flux | $\Delta T = 22.65 (q''/10^6)^{0.5} \exp(-P/8.7 \times 10^6)$ |
| **Zuber (1959)** | Critical heat flux limit | $q''_{CHF} = 0.131 \cdot h_{fg} \cdot ρ_s \cdot [σg(ρ_w-ρ_s)/ρ_s²]^{0.25}$ |
| **Davis-Anderson** | Onset of nucleate boiling | $\Delta T_{ONB} = \sqrt{8σT_{sat}q''/(k_l ρ_s h_{fg})}$ |
| **Zuber-Findlay** | Drift-flux void fraction | $α_{DF} = α_{homogeneous} / C_0$ where $C_0 = 1.13$ |
| **IAPWS-97** | Steam/water properties | International standard for all thermodynamic properties |

### 3.5 Void Fraction Model

The volume void fraction α is computed from the Zuber-Findlay drift-flux model:

$$α_{homogeneous} = \frac{ρ_w}{ρ_w - ρ_s}\left(1 - \frac{\ln(1 + φγ)}{φγ}\right)$$

where $γ = (ρ_w - ρ_s)/ρ_s$

All analytical derivatives (∂α/∂φ, ∂α/∂P) are computed exactly via chain rule — no numerical differencing.

---

## 4. Solver Implementation

### 4.1 ODE Solver

- **Method:** `scipy.integrate.solve_ivp` with Radau (implicit Runge-Kutta)
- **Why Radau:** The DAE system is stiff (density ratio ~1600×, eigenvalue spread >10⁶). Explicit methods (RK45) diverge.
- **Regime handling:**
  - **Subcooled (T < T_sat):** Analytical sensible heating with sealed-vessel pressure model
  - **Transition (T = T_sat):** Smooth handoff to full ODE with φ₀ = 0.005
  - **Boiling (T ≥ T_sat):** Full 4-equation DAE, T tracks saturation curve

### 4.2 Thermodynamic Property Lookup

All steam table properties use **cubic spline interpolation** of IAPWS-97 data:
- Pre-computed at 500 pressure points (5 kPa – 1 MPa)
- Analytically exact derivatives from spline coefficients
- ~100× faster than calling IAPWS97() per evaluation

### 4.3 Safety Systems

| Protection Layer | Implementation |
|-----------------|----------------|
| CHF guard | Zuber correlation caps heat flux at critical value |
| Pressure relief | dP/dt = 0 if P ≥ 10 bar (simulates SRV) |
| State clamps | P ∈ [5 kPa, 10 bar], φ ∈ [0, 0.99], V_dw ≥ 1 mL |
| Solver fallback | Returns last known state if solve_ivp fails |

---

## 5. Extended Kalman Filter (Sensor-Model Fusion)

### 5.1 Purpose

Raw sensor data contains noise (PT100: ±0.3°C, pressure transducer: ±0.01 bar). Re-initializing the ODE solver with noisy data causes prediction "jumps." The EKF provides optimal, persistent state estimation.

### 5.2 Filter Design

**State vector:** x = [T (°C), P_abs (bar), V_water (L)]

**Process model:** Uses `predict_forward()` as the nonlinear state transition f(x, u)

**Jacobian:** Computed via central finite differences (numerical):

$$F_{ij} = \frac{f_i(x + δe_j) - f_i(x - δe_j)}{2δ}$$

**Noise matrices (tuned empirically):**

| Matrix | T | P | V |
|--------|---|---|---|
| Q (process) | 0.05 °C²/s | 0.0001 bar²/s | 0.001 L²/s |
| R (measurement) | 0.25 °C² | 0.0004 bar² | 0.04 L² |

### 5.3 Convergence Performance

| Metric | Cycle 1 | Cycle 5 (converged) |
|--------|---------|---------------------|
| K_T (Kalman gain) | 0.94 | 0.25 |
| σ_T (uncertainty) | ±2.0 °C | ±0.25 °C |
| Resets | 0 | 0 |

---

## 6. Validation Results

### 6.1 Automated Test Suite (1000 Tests)

| Category | Tests | Pass Rate |
|----------|-------|-----------|
| Matrix solver (C·X=D) | 250 | 100% |
| Second Law (Clausius) | 150 | 100% |
| predict_forward() | 250 | 100% |
| predict_timeline() | 150 | 100% |
| Void fraction α(φ,P) | 100 | 100% |
| Energy direction | 100 | 100% |
| **TOTAL** | **1000** | **100%** |

Parameter ranges swept: T ∈ [25, 150]°C, P ∈ [1, 8] bar, water ∈ [1, 5.5] kg, Q ∈ [0, 2000] W

### 6.2 Field Validation (45-Minute Heating Cycle)

A complete cold-start → boiling → pressure-rise cycle was simulated using IAPWS-97 as ground truth with realistic sensor noise.

| Metric | Temperature | Pressure |
|--------|-------------|----------|
| **RMSE** | 2.01 °C | 0.208 bar |
| **MAPE** | 0.46% | 1.16% |
| **Max Error** | 21.5 °C* | 1.54 bar* |

*Max errors occur only at extreme high pressures (>5 bar) where the model's sealed-vessel thermal expansion model transitions to the ODE. In the normal operating range (1–3 bar), max error is <3°C and <0.05 bar.

**Conservation Law Compliance:**
- Mass conservation: **100%** (all 270 timesteps)
- Entropy production Ṡ_irr ≥ 0: **100%** (all 270 timesteps)

### 6.3 Validation CSV Data

The complete timestep-by-timestep comparison is exported as `results/field_validation.csv` with columns:
`t_min, regime, T_ref, T_pred, T_error, P_ref, P_pred, P_error, mass_ok, entropy_ok`

---

## 7. Hardware Specifications

| Component | Specification | Purpose |
|-----------|---------------|---------|
| ESP32 DevKit | Dual-core 240 MHz | Sensor acquisition, heater control |
| MAX31865 + PT100 | ±0.15°C accuracy | Water temperature measurement |
| ADS1115 | 16-bit, I2C | Pressure transducer ADC |
| Pressure transducer | 0–1.2 MPa, 0.5–4.5V | Absolute pressure sensing |
| Flow meter | Hall-effect, pulse | Feedwater volume tracking |
| SSR (Solid State Relay) | 25A, zero-cross | Heater power switching |
| Float switches | 2× (high/low) | Water level safety interlock |

### Boiler Dimensions

| Parameter | Value | Measured |
|-----------|-------|----------|
| Drum diameter | 18 cm | ✓ |
| Drum height | 24 cm | ✓ |
| Total volume | 6.1 L | ✓ |
| Water capacity | 4.2 L | ✓ |
| Metal mass | 6.5 kg | Calibrated |
| Heater power | 1 kW | ✓ |
| Heater area | 0.01 m² | ✓ |

---

## 8. Technology Stack

| Layer | Technology |
|-------|-----------|
| Firmware | C++ (Arduino framework) |
| Physics Engine | Python 3 (NumPy, SciPy, IAPWS) |
| Sensor Fusion | Python (Custom EKF) |
| Serial Bridge | Python (pyserial, HTTP server) |
| Dashboard | Next.js 16 (TypeScript, React) |
| Visualization | Recharts, Custom 3D heatmaps |

---

## 9. Industrial Relevance to Thermax

### 9.1 Value Proposition

Every Thermax boiler sold could ship with a digital twin. This enables:

1. **Predictive Maintenance:** The model detects anomalies (efficiency drop, scaling buildup) before physical failure
2. **Virtual Commissioning:** Test control strategies on the digital twin before field deployment
3. **Operator Training:** New operators can practice on the twin without risk to equipment
4. **SaaS Revenue:** Cloud-deployed twins enable recurring monitoring subscription revenue

### 9.2 Scalability Path

The physics engine is parameterized by `constants.py`. Adapting to a different boiler requires only:
- Updating drum geometry (D_DRUM, H_DRUM)
- Updating metal mass (M_M)
- Updating heater specifications (A_HEATER, Q_max)

The conservation equations, correlations, and solver remain unchanged.

---

## 10. File Structure

```
Physics-based-model/
├── boiler-model/
│   ├── config/constants.py          ← Boiler hardware dimensions
│   ├── core/
│   │   ├── coefficients.py          ← C matrix and D vector assembly
│   │   └── matrix_form.py           ← C·X=D solver + audit functions
│   ├── physics/
│   │   ├── thermo_relations.py      ← IAPWS-97 spline interpolation
│   │   └── void_fraction.py         ← Zuber-Findlay drift-flux model
│   ├── engine/
│   │   ├── solver_logic.py          ← ODE solver + regime handling
│   │   └── kalman_filter.py         ← Extended Kalman Filter (EKF)
│   ├── tests/
│   │   ├── test_1000_consistency.py ← 1000-test validation suite
│   │   └── field_validation.py      ← Full heating cycle validation
│   └── results/
│       └── field_validation.csv     ← Timestep-by-timestep comparison
├── boiler-dashboard/
│   ├── serial_proxy.py              ← Hardware bridge + physics engine
│   ├── esp32_boiler.ino             ← ESP32 firmware
│   └── app/page.tsx                 ← React dashboard
```

---

*Document generated: April 2026*  
*Total lines of physics code: ~2,500*  
*Total lines of infrastructure: ~3,500*
