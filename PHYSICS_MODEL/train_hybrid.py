import pandas as pd
from sklearn.ensemble import RandomForestRegressor
import joblib
import os
import glob
import sys

# 1. Load session logs from arguments, or fallback to the 4 most recent
if len(sys.argv) > 1:
    # Use exact files provided by the user via command line
    all_files = sys.argv[1:]
    # Remove duplicates just in case
    all_files = list(dict.fromkeys(all_files))
else:
    log_dir = 'boiler-dashboard/session_logs'
    all_files = sorted(glob.glob(os.path.join(log_dir, "*.csv")), reverse=True)[:12]

df_list = []
horizon_rows = 60

for file in all_files:
    try:
        temp_df = pd.read_csv(file)
        if len(temp_df) > 10:  # Ignore empty or tiny logs
            # Ensure required columns exist
            required_columns = ['T_actual', 'P_actual_gauge', 'T_predicted', 'P_predicted', 'Q_watts', 'flow_lpm', 'water_L']
            if not all(col in temp_df.columns for col in required_columns):
                print(f"Skipping {file}: Missing required columns")
                continue
                
            # Filter out rows where predictions haven't populated yet
            temp_df = temp_df.dropna(subset=['T_predicted', 'P_predicted'])
            
            # Align the time-series PER FILE using exact timestamps!
            # The logging rate is ~4Hz, so shift(-60) was only 15 seconds!
            temp_df['timestamp'] = pd.to_datetime(temp_df['timestamp'])
            
            # Create a copy for the future lookup
            future_df = temp_df[['timestamp', 'T_actual', 'P_actual_gauge']].copy()
            future_df = future_df.rename(columns={
                'timestamp': 'future_ts', 
                'T_actual': 'T_actual_future', 
                'P_actual_gauge': 'P_actual_future'
            })
            future_df = future_df.sort_values('future_ts')
            temp_df = temp_df.sort_values('timestamp')
            
            # The target timestamp is exactly 60 seconds from 'timestamp'
            temp_df['target_ts'] = temp_df['timestamp'] + pd.Timedelta(seconds=60)
            
            # Merge to find the closest future actual values
            merged = pd.merge_asof(
                temp_df, future_df, 
                left_on='target_ts', 
                right_on='future_ts',
                direction='nearest',
                tolerance=pd.Timedelta(seconds=2) # Must be within 2 seconds
            )
            
            # Drop rows at the end that didn't find a future match
            temp_df = merged.dropna(subset=['T_actual_future', 'P_actual_future'])
            
            if len(temp_df) > 0:
                df_list.append(temp_df)
    except Exception as e:
        print(f"Skipping {file}: {e}")

if not df_list:
    print("Error: No valid session data found after processing.")
    exit(1)

print(f"Loading data from the {len(df_list)} session logs...")
df = pd.concat(df_list, ignore_index=True)

# Calculate the TRUE Error of the physics model (Actual Future - Predicted Future)
df['error_T'] = df['T_actual_future'] - df['T_predicted']
df['error_P'] = df['P_actual_future'] - df['P_predicted']

# 4. Define the Features (The Inputs the AI gets to see at time `i`)
features = ['T_actual', 'P_actual_gauge', 'Q_watts', 'flow_lpm', 'water_L']
X = df[features]

# The Targets
y_T = df['error_T']
y_P = df['error_P']

# Initialize models
ml_model_T = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
ml_model_P = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)

print(f"Training Hybrid AI on {len(df)} rows...")
ml_model_T.fit(X, y_T)
ml_model_P.fit(X, y_P)

# Save the trained AI models to disk so serial_proxy can use them later
# Save them inside boiler-dashboard directory where serial_proxy.py lives
os.makedirs('boiler-dashboard/models', exist_ok=True)
joblib.dump(ml_model_T, 'boiler-dashboard/models/residual_model_T.pkl')
joblib.dump(ml_model_P, 'boiler-dashboard/models/residual_model_P.pkl')
print("Models saved successfully to boiler-dashboard/models/ !")
