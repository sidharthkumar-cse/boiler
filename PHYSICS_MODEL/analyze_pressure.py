import pandas as pd
import glob, os, numpy as np

log_dir = 'boiler-dashboard/session_logs'
files = sorted(glob.glob(os.path.join(log_dir, '*.csv')), reverse=True)[:12]

df_list = []
for f in files:
    try:
        d = pd.read_csv(f)
        if len(d) > 10 and 'T_actual' in d.columns and 'P_actual_gauge' in d.columns and 'P_predicted' in d.columns:
            d = d.dropna(subset=['P_predicted', 'T_predicted'])
            if len(d) > 0:
                df_list.append(d)
    except:
        pass

df = pd.concat(df_list, ignore_index=True)
df['P_error'] = (df['P_actual_gauge'] - df['P_predicted']).abs()
df['P_signed_error'] = df['P_predicted'] - df['P_actual_gauge']
df['T_error'] = (df['T_actual'] - df['T_predicted']).abs()

bins = [(0, 40, '0-40C'), (40, 60, '40-60C'), (60, 80, '60-80C'), (80, 95, '80-95C'), (95, 120, '95-120C')]

print("Total rows with predictions:", len(df))
print()
header = "{:<12} {:>6} {:>8} {:>8} {:>10} {:>10} {:>10} {:>10}".format(
    "Temp Range", "Rows", "T_MAE", "P_MAE", "P_act_avg", "P_pred_avg", "P_bias", "P_Acc%")
print(header)
print("-" * 85)

for lo, hi, label in bins:
    subset = df[(df['T_actual'] >= lo) & (df['T_actual'] < hi)]
    if len(subset) < 3:
        print("{:<12} {:>6}  -- too few rows --".format(label, len(subset)))
        continue
    t_mae = subset['T_error'].mean()
    p_mae = subset['P_error'].mean()
    p_actual_avg = subset['P_actual_gauge'].mean()
    p_pred_avg = subset['P_predicted'].mean()
    p_bias = subset['P_signed_error'].mean()  # positive = overpredicting

    # Percentage accuracy using absolute error relative to scale
    # For gauge pressure near zero, use a floor of 0.05 bar to avoid MAPE explosion
    denom = subset['P_actual_gauge'].abs().clip(lower=0.05)
    p_mape = 100 * (subset['P_error'] / denom).mean()
    p_acc = max(0, 100 - p_mape)

    print("{:<12} {:>6} {:>8.3f} {:>8.4f} {:>10.4f} {:>10.4f} {:>+10.4f} {:>10.1f}".format(
        label, len(subset), t_mae, p_mae, p_actual_avg, p_pred_avg, p_bias, p_acc))

print()
print("=== LOW TEMPERATURE PRESSURE DETAIL (T < 80C) ===")
low = df[df['T_actual'] < 80]
if len(low) > 5:
    print("P_actual_gauge range: {:.4f} to {:.4f} bar".format(low['P_actual_gauge'].min(), low['P_actual_gauge'].max()))
    print("P_predicted range:    {:.4f} to {:.4f} bar".format(low['P_predicted'].min(), low['P_predicted'].max()))
    print("Mean P_actual_gauge:  {:.4f} bar".format(low['P_actual_gauge'].mean()))
    print("Mean P_predicted:     {:.4f} bar".format(low['P_predicted'].mean()))
    print("Mean absolute error:  {:.4f} bar".format(low['P_error'].mean()))
    print("Mean signed error:    {:+.4f} bar (positive = model overpredicts)".format(low['P_signed_error'].mean()))
    print()
    
    # Show first 10 and last 10 rows at low temp
    print("--- Sample rows at low temp ---")
    sample = low[['T_actual', 'P_actual_gauge', 'P_predicted', 'P_error', 'P_signed_error', 'Q_watts']].head(15)
    print(sample.to_string(index=False))

print()
print("=== HIGH TEMPERATURE PRESSURE DETAIL (T >= 95C) ===")
high = df[df['T_actual'] >= 95]
if len(high) > 5:
    print("P_actual_gauge range: {:.4f} to {:.4f} bar".format(high['P_actual_gauge'].min(), high['P_actual_gauge'].max()))
    print("P_predicted range:    {:.4f} to {:.4f} bar".format(high['P_predicted'].min(), high['P_predicted'].max()))
    print("Mean P_actual_gauge:  {:.4f} bar".format(high['P_actual_gauge'].mean()))
    print("Mean P_predicted:     {:.4f} bar".format(high['P_predicted'].mean()))
    print("Mean absolute error:  {:.4f} bar".format(high['P_error'].mean()))
    print("Mean signed error:    {:+.4f} bar".format(high['P_signed_error'].mean()))
