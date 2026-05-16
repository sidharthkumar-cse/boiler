"""Calibrate ETA_VAPOR sigmoid from latest session data."""
import csv, numpy as np
from scipy.optimize import minimize

files = [
    'boiler-dashboard/session_logs/session_20260501_025826.csv',
    'boiler-dashboard/session_logs/session_20260501_022834.csv',
    'boiler-dashboard/session_logs/session_20260501_013346.csv',
]

rows = []
for f in files:
    with open(f, 'r') as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            try:
                t = float(row['T_actual'])
                p_act = float(row['P_actual_gauge'])
                p_pred = float(row['P_predicted'])
                q = float(row['Q_watts'])
                if q > 0 and p_act > 0.01:
                    rows.append((t, p_act, p_pred))
            except:
                pass

print(f"Loaded {len(rows)} data points with P_act > 0.01 bar")

# Current error analysis
errors = [p - a for t, a, p in rows]
bias = np.mean(errors)
rmse = np.sqrt(np.mean(np.array(errors)**2))
mean_act = np.mean([a for _, a, _ in rows])
print(f"\nCurrent model performance:")
print(f"  Mean bias: {bias:+.4f} bar (positive = overpredicts)")
print(f"  RMSE: {rmse:.4f} bar")
print(f"  Mean P_act: {mean_act:.4f} bar")
print(f"  Accuracy: {(1 - rmse/mean_act)*100:.1f}%")

# Breakdown by temperature
print(f"\n{'T Range':>12} {'N':>5} {'P_act':>8} {'P_pred':>8} {'Bias':>8} {'MAPE%':>7}")
print("-" * 55)
for t_lo in range(60, 115, 5):
    sub = [(t, a, p) for t, a, p in rows if t_lo <= t < t_lo + 5]
    if sub:
        bias_sub = np.mean([p - a for _, a, p in sub])
        mape = np.mean([abs(p - a) / a * 100 for _, a, p in sub])
        print(f"{t_lo:>5}-{t_lo+4}°C {len(sub):>5} {np.mean([a for _, a, _ in sub]):>8.4f} "
              f"{np.mean([p for _, _, p in sub]):>8.4f} {bias_sub:>+8.4f} {mape:>7.1f}")

# The sigmoid: eta(T) = ETA_MIN + (ETA_MAX - ETA_MIN) / (1 + exp(-K*(T - T_MID)))
# Current: ETA_MIN=0.42, ETA_MAX=0.78, T_MID=78, K=0.08
# 
# The pressure prediction scales roughly linearly with ETA_VAPOR in the subcooled regime.
# If pred/act ratio is R at temperature T, then:
#   ideal_eta(T) = current_eta(T) * (act/pred) = current_eta(T) / R

def current_eta(T):
    return 0.42 + (0.78 - 0.42) / (1.0 + np.exp(-0.08 * (T - 78.0)))

# Compute what ETA should be at each point
print("\n=== Optimal ETA_VAPOR by temperature ===")
for t_lo in range(70, 115, 5):
    sub = [(t, a, p) for t, a, p in rows if t_lo <= t < t_lo + 5 and p > 0.005]
    if sub:
        ratios = [a / p for _, a, p in sub]
        mean_ratio = np.mean(ratios)
        mean_t = np.mean([t for t, _, _ in sub])
        ideal = current_eta(mean_t) * mean_ratio
        print(f"  T={mean_t:5.1f}°C: act/pred={mean_ratio:.4f}, current_eta={current_eta(mean_t):.4f}, ideal_eta={ideal:.4f}")

# Fit optimal sigmoid parameters
# We want: pred_new = pred_old * (new_eta / old_eta) ≈ actual
# So: new_eta(T) = old_eta(T) * (actual / pred_old)
target_eta = []
for t, a, p in rows:
    if p > 0.005:
        ratio = a / p
        ideal = current_eta(t) * ratio
        target_eta.append((t, ideal))

if target_eta:
    def sigmoid(T, params):
        eta_min, eta_max, t_mid, k = params
        return eta_min + (eta_max - eta_min) / (1.0 + np.exp(-k * (T - t_mid)))
    
    def cost(params):
        eta_min, eta_max, t_mid, k = params
        if eta_min < 0.1 or eta_max > 1.0 or eta_min > eta_max or k < 0.01:
            return 1e6
        err = 0
        for t, target in target_eta:
            pred = sigmoid(t, params)
            err += (pred - target) ** 2
        return err / len(target_eta)
    
    result = minimize(cost, [0.42, 0.78, 78.0, 0.08], method='Nelder-Mead')
    eta_min, eta_max, t_mid, k = result.x
    
    print(f"\n=== OPTIMIZED SIGMOID PARAMETERS ===")
    print(f"  ETA_MIN  = {eta_min:.4f}  (was 0.42)")
    print(f"  ETA_MAX  = {eta_max:.4f}  (was 0.78)")
    print(f"  T_MID    = {t_mid:.1f}°C  (was 78.0)")
    print(f"  K_SLOPE  = {k:.4f}    (was 0.08)")
    
    # Verify
    print(f"\n  Verification:")
    for T in [70, 80, 85, 90, 95, 100, 105, 110]:
        print(f"    T={T}°C: old={current_eta(T):.4f}, new={sigmoid(T, result.x):.4f}")
