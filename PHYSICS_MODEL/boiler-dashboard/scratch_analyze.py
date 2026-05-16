"""Quick accuracy analysis of post-retraining sessions."""
import pandas as pd
import sys, glob, os

sessions = [
    'session_logs/session_20260429_215447.csv',
    'session_logs/session_20260429_220843.csv',
    'session_logs/session_20260429_221249.csv',
]

for path in sessions:
    try:
        df = pd.read_csv(path)
        if len(df) < 10:
            print(f"\n⏭  {os.path.basename(path)}: Too few rows ({len(df)}), skipping")
            continue
        
        df = df.dropna(subset=['T_predicted', 'P_predicted', 'T_actual'])
        
        # Filter only rows where heater is ON (meaningful predictions)
        df_heat = df[df['Q_watts'] > 0].copy()
        if len(df_heat) < 5:
            df_heat = df.copy()  # Use all rows if heater was barely on
        
        # Temperature accuracy
        df_heat['T_err'] = abs(df_heat['T_actual'] - df_heat['T_predicted'])
        df_heat['T_pct'] = 100.0 * (1.0 - df_heat['T_err'] / df_heat['T_actual'].clip(lower=1))
        
        # Pressure accuracy (only where actual > 0.005 bar to avoid div-by-zero)
        df_p = df_heat[df_heat['P_actual_gauge'] > 0.005].copy()
        
        # Water level accuracy
        df_l = df_heat.dropna(subset=['L_predicted'])
        df_l = df_l[df_l['water_L'] > 0.1].copy()
        
        t_range = f"{df['T_actual'].min():.1f}°C → {df['T_actual'].max():.1f}°C"
        p_range = f"{df['P_actual_gauge'].min():.3f} → {df['P_actual_gauge'].max():.3f} bar"
        
        print(f"\n{'='*60}")
        print(f"📊 {os.path.basename(path)}")
        print(f"   Rows: {len(df)} | Heating rows: {len(df_heat)}")
        print(f"   Range: {t_range} | Pressure: {p_range}")
        print(f"   ─────────────────────────────────────")
        
        # Temperature stats
        mean_T_err = df_heat['T_err'].mean()
        max_T_err = df_heat['T_err'].max()
        mean_T_acc = df_heat['T_pct'].mean()
        print(f"   🌡️  TEMPERATURE:")
        print(f"      Mean error:    {mean_T_err:.2f}°C")
        print(f"      Max error:     {max_T_err:.2f}°C")
        print(f"      Mean accuracy: {mean_T_acc:.1f}%")
        
        # Pressure stats
        if len(df_p) > 5:
            df_p['P_err'] = abs(df_p['P_actual_gauge'] - df_p['P_predicted'])
            df_p['P_pct'] = 100.0 * (1.0 - df_p['P_err'] / df_p['P_actual_gauge'].clip(lower=0.001))
            mean_P_err = df_p['P_err'].mean()
            max_P_err = df_p['P_err'].max()
            mean_P_acc = df_p['P_pct'].mean()
            print(f"   🔵 PRESSURE (where gauge > 0.005 bar):")
            print(f"      Mean error:    {mean_P_err:.4f} bar")
            print(f"      Max error:     {max_P_err:.4f} bar")
            print(f"      Mean accuracy: {mean_P_acc:.1f}%")
        else:
            print(f"   🔵 PRESSURE: Not enough gauge readings (only {len(df_p)} rows > 0.005 bar)")
        
        # Water level stats
        if len(df_l) > 5:
            df_l['L_err'] = abs(df_l['water_L'] - df_l['L_predicted'])
            df_l['L_pct'] = 100.0 * (1.0 - df_l['L_err'] / df_l['water_L'].clip(lower=0.1))
            mean_L_acc = df_l['L_pct'].mean()
            print(f"   💧 WATER LEVEL:")
            print(f"      Mean accuracy: {mean_L_acc:.1f}%")
        
        # Sample some key data points
        print(f"\n   📌 Sample points (every ~25% of data):")
        step = max(1, len(df_heat) // 4)
        for idx in range(0, len(df_heat), step):
            row = df_heat.iloc[idx]
            t_acc = 100 * (1 - abs(row['T_actual'] - row['T_predicted']) / max(row['T_actual'], 1))
            print(f"      T: {row['T_actual']:.1f}→pred {row['T_predicted']:.1f} ({t_acc:.1f}%) | "
                  f"P: {row['P_actual_gauge']:.3f}→pred {row['P_predicted']:.4f}")
        
    except Exception as e:
        print(f"\n❌ {os.path.basename(path)}: {e}")
        import traceback; traceback.print_exc()
