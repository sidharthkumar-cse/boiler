import csv
from pathlib import Path

def analyze():
    log_dir = Path("boiler-dashboard/session_logs")
    files = sorted(log_dir.glob("session_*.csv"))
    path = files[-1]
    
    with open(path, newline="") as f:
        rows = list(csv.DictReader(f))
        
    print(f"File: {path.name}")
    bins = {}
    for row in rows:
        try:
            P_act = float(row["P_actual_gauge"])
            T_act = float(row["T_actual"])
            T_pred = float(row["T_predicted"])
            P_pred = float(row["P_predicted"])
            error = T_pred - T_act
            
            p_bin = round(P_act * 10) / 10 # nearest 0.1 bar
            if p_bin not in bins: bins[p_bin] = []
            bins[p_bin].append(error)
        except (ValueError, TypeError):
            pass
            
    for b in sorted(bins.keys()):
        errs = bins[b]
        print(f"P ≈ {b:.1f} bar : avg T_error = {sum(errs)/len(errs):+5.2f} C (n={len(errs)})")

analyze()
