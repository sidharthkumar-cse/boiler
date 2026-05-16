import csv
from pathlib import Path

def analyze():
    log_dir = Path("boiler-dashboard/session_logs")
    files = sorted(log_dir.glob("session_*.csv"))
    path = files[-1]
    
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
        
    high_p = []
    low_p = []
    for row in rows:
        try:
            P_act = float(row["P_actual_gauge"])
            T_act = float(row["T_actual"])
            T_pred = float(row["T_predicted"])
            P_pred = float(row["P_predicted"])
            error = T_pred - T_act
            if P_act > 1.0: # high pressure > 1 bar gauge
                high_p.append(error)
            elif P_act < 0.5:
                low_p.append(error)
        except (ValueError, TypeError):
            pass
            
    print(f"Low pressure (<0.5 bar) average T_error: {sum(low_p)/len(low_p) if low_p else 0:.3f} C")
    print(f"High pressure (>1.0 bar) average T_error: {sum(high_p)/len(high_p) if high_p else 0:.3f} C")

analyze()
