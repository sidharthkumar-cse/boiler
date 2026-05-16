#!/usr/bin/env python3
"""
Analyze real session prediction accuracy.

The serial proxy logs each short-horizon forecast with the future timestamp it
was predicting. This script matches every forecast to the closest actual sensor
row near that target timestamp and prints real field RMSE.
"""
import csv
import math
import sys
from datetime import datetime
from pathlib import Path


MAX_MATCH_ERROR_SECONDS = 3.0


def parse_time(value):
    if not value:
        return None
    return datetime.fromisoformat(value)


def parse_float(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def latest_session_file():
    log_dir = Path(__file__).parent / "session_logs"
    files = sorted(log_dir.glob("session_*.csv"))
    if not files:
        raise FileNotFoundError(f"No session CSV files found in {log_dir}")
    return files[-1]


def load_rows(path):
    rows = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            ts = parse_time(row.get("timestamp"))
            if ts is None:
                continue
            row["_ts"] = ts
            rows.append(row)
    return rows


def closest_actual(rows, target_ts):
    best = None
    best_dt = float("inf")
    for row in rows:
        dt = abs((row["_ts"] - target_ts).total_seconds())
        if dt < best_dt:
            best = row
            best_dt = dt
    if best is None or best_dt > MAX_MATCH_ERROR_SECONDS:
        return None, best_dt
    return best, best_dt


def rmse(errors):
    if not errors:
        return None
    return math.sqrt(sum(e * e for e in errors) / len(errors))


def summarize(path):
    rows = load_rows(path)
    matches = []

    for row in rows:
        target_ts = parse_time(row.get("prediction_target_timestamp"))
        T_pred = parse_float(row.get("T_predicted"))
        P_pred = parse_float(row.get("P_predicted"))
        L_pred = parse_float(row.get("L_predicted"))
        if target_ts is None or T_pred is None or P_pred is None:
            continue

        actual, match_dt = closest_actual(rows, target_ts)
        if actual is None:
            continue

        T_actual = parse_float(actual.get("T_actual"))
        P_actual = parse_float(actual.get("P_actual_gauge"))
        L_actual = parse_float(actual.get("water_L"))
        if T_actual is None or P_actual is None:
            continue

        match = {
            "dt": match_dt,
            "T_error": T_pred - T_actual,
            "P_error": P_pred - P_actual,
        }
        if L_pred is not None and L_actual is not None:
            match["L_error"] = L_pred - L_actual
        matches.append(match)

    T_errors = [m["T_error"] for m in matches]
    P_errors = [m["P_error"] for m in matches]
    L_errors = [m["L_error"] for m in matches if "L_error" in m]

    print(f"Session: {path}")
    print(f"Rows: {len(rows)}")
    print(f"Matched forecasts: {len(matches)}")

    if not matches:
        print("No matched predictions found. Run the serial proxy with the new logger first.")
        return 1

    print()
    print("60-second forecast accuracy")
    print(f"Temperature RMSE: {rmse(T_errors):.3f} C")
    print(f"Pressure RMSE:    {rmse(P_errors):.4f} bar")
    if L_errors:
        print(f"Water RMSE:       {rmse(L_errors):.3f} L")

    print()
    print(f"Temperature bias: {sum(T_errors) / len(T_errors):+.3f} C")
    print(f"Pressure bias:    {sum(P_errors) / len(P_errors):+.4f} bar")
    if L_errors:
        print(f"Water bias:       {sum(L_errors) / len(L_errors):+.3f} L")

    return 0


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_session_file()
    raise SystemExit(summarize(path))


if __name__ == "__main__":
    main()
