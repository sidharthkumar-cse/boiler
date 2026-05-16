# ═══════════════════════════════════════════════════════════════════
# Physical Constants — Real Boiler Hardware Dimensions
# ═══════════════════════════════════════════════════════════════════
import math

# ── Boiler Cylinder Geometry ──
D_DRUM  = 0.18         # Drum diameter  (18 cm — measured)
H_DRUM  = 0.24         # Drum height    (24 cm — measured)
A_D     = math.pi / 4.0 * D_DRUM**2   # Cross-section area  ≈ 0.02545 m²

# ── Water Level Reference (Float Switch Calibration) ──
H_WATER_MAX = 0.165    # Water level at float_high (16.5 cm → 4.2 L)
H_STEAM     = 0.075    # Steam space above water  (7.5 cm → 1.9 L)

# ── Volumes (m³) ──
V_T     = A_D * H_DRUM               # Total internal volume ≈ 0.00611 m³ (~6.1 L)
V_WATER_INIT = A_D * H_WATER_MAX    # Water volume at float_high ≈0.00420 m³ (~4.2 L)

# ── Inlet / Outlet Pipes ──
D_INLET  = 0.0127      # Water inlet diameter   (1.27 cm = ½ inch)
D_PIPE   = 0.0127      # Steam outlet diameter  (1.27 cm = ½ inch)
A_INLET  = math.pi / 4.0 * D_INLET**2   # Inlet area  ≈ 1.267e-4 m²
A_OUTLET = math.pi / 4.0 * D_PIPE**2    # Outlet area ≈ 1.267e-4 m²

# ── Metal Properties ──
M_M     = 3.0           # Thermally-coupled metal mass (kg) - Calibrated from session data: only heater element + inner wall are in thermal equilibrium with water at 10-min timescale
C_M     = 480.0         # Specific heat capacity of steel (J/(kg·K))

# ── Flow Parameters ──
M_DC    = 0.5           # Natural circulation rate (kg/s) — used by test/simulation scripts

# ── Steam Outlet Orifice Parameters ──
C_D_VALVE    = 0.65     # Discharge coefficient (dimensionless)
P_DOWNSTREAM = 1.013e5  # Downstream pressure (Pa) — 1 atm

# ── Operational Parameters ──
A_HEATER  = 0.01        # Heater surface area (m²) — measured for 1kW immersion element
R_FOULING = 0.0         # Thermal resistance of scale buildup (m²·K/W)
P_NOMINAL = 2.0e5       # Nominal operating pressure (2 bar)
T_FEED    = 25.0        # Feed water temperature (°C)

# ── Environmental & Heat Loss Parameters ──
T_AMB     = 25.0        # Ambient temperature (°C)
U_LOSS    = 18.0        # Overall heat loss coefficient (W/m²·K) - calibrated: natural convection + radiation at high T
A_VESSEL  = math.pi * D_DRUM * H_DRUM + 2.0 * A_D # Total exposed surface area of the drum

# ── Parasitic Steam Leak (fitting/PRV seat leakage) ──
# Even when valve is "closed", small leaks exist through fittings and PRV seat.
# We set this to 0.0 so the pure physics engine accurately retains thermal expansion pressure in the subcooled regime!
K_LEAK    = 0.0         # Leak conductance (kg/s per bar of gauge pressure)
