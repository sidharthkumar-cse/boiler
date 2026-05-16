import re

with open('boiler-model/simulation/solver_logic.py', 'r') as f:
    content = f.read()

# Fix predict_timeline
content = content.replace("boiling_active = cur_T >= T_sat_atm", 
                          "boiling_active = cur_T >= (thermo.get_T_sat(cur_P) - 273.15)")

# Replace T_sat_atm with T_sat_curr inside predict_timeline loop (except the T_sat_atm assignment)
def process_predict_timeline(text):
    start_idx = text.find("def predict_timeline")
    end_idx = text.find("def run_continuous")
    
    predict_timeline_body = text[start_idx:end_idx]
    
    # We want to keep P_atm and T_sat_atm definitions
    # But inside the loop, we should define T_sat_currP and use it.
    
    # At the start of the loop, define T_sat_currP
    predict_timeline_body = predict_timeline_body.replace(
        "        if not boiling_active:",
        "        T_sat_currP = thermo.get_T_sat(cur_P) - 273.15\n        if not boiling_active:"
    )
    
    # Replace T_sat_atm with T_sat_currP in all logic inside the loop!
    # Specifically where it says: T_sat_K = T_sat_atm + 273.15
    predict_timeline_body = predict_timeline_body.replace(
        "T_sat_K = T_sat_atm + 273.15",
        "T_sat_K = T_sat_currP + 273.15"
    )
    predict_timeline_body = predict_timeline_body.replace(
        "T_ONB_i = T_sat_atm - (max(5.0, min(superheat_ONB, 25.0)))",
        "T_ONB_i = T_sat_currP - (max(5.0, min(superheat_ONB, 25.0)))"
    )
    predict_timeline_body = predict_timeline_body.replace(
        "Z = (cur_T - T_ONB_i) / (T_sat_atm - T_ONB_i)",
        "Z = (cur_T - T_ONB_i) / (T_sat_currP - T_ONB_i)"
    )
    predict_timeline_body = predict_timeline_body.replace(
        "if new_T >= T_sat_atm:",
        "if new_T >= T_sat_currP:"
    )
    predict_timeline_body = predict_timeline_body.replace(
        "t_to_boil    = (T_sat_atm - cur_T) * thermal_mass / Q_sensible",
        "t_to_boil    = (T_sat_currP - cur_T) * thermal_mass / Q_sensible"
    )
    predict_timeline_body = predict_timeline_body.replace(
        "cur_T   = T_sat_atm",
        "cur_T   = T_sat_currP"
    )
    
    # Fix the identical issue in predict_forward
    predict_forward_body = text[:start_idx]
    
    predict_forward_body = predict_forward_body.replace(
        "if cur_T < T_sat_atm and Q > 0:",
        "T_sat_currP = thermo.get_T_sat(P_init) - 273.15\n    if cur_T < T_sat_currP and Q > 0:"
    )
    predict_forward_body = predict_forward_body.replace(
        "T_sat_K = T_sat_atm + 273.15",
        "T_sat_K = T_sat_currP + 273.15"
    )
    predict_forward_body = predict_forward_body.replace(
        "T_ONB = T_sat_atm - (max(5.0, min(superheat_ONB, 25.0)))",
        "T_ONB = T_sat_currP - (max(5.0, min(superheat_ONB, 25.0)))"
    )
    predict_forward_body = predict_forward_body.replace(
        "Z = (cur_T - T_ONB) / (T_sat_atm - T_ONB)",
        "Z = (cur_T - T_ONB) / (T_sat_currP - T_ONB)"
    )
    predict_forward_body = predict_forward_body.replace(
        "t_to_boil = (T_sat_atm - cur_T) * thermal_mass / Q_sensible",
        "t_to_boil = (T_sat_currP - cur_T) * thermal_mass / Q_sensible"
    )
    predict_forward_body = predict_forward_body.replace(
        "sf = (T_final - T_ONB) / (T_sat_atm - T_ONB)",
        "sf = (T_final - T_ONB) / (T_sat_currP - T_ONB)"
    )
    
    return predict_forward_body + predict_timeline_body + text[end_idx:]

new_content = process_predict_timeline(content)
with open('boiler-model/simulation/solver_logic.py', 'w') as f:
    f.write(new_content)
print("Applied dynamic saturation temperature fixes!")
