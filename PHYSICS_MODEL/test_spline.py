import numpy as np
from iapws import IAPWS97
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'boiler-model'))
from physics import thermo_relations as thermo

for P_bar in [1.0, 1.5, 2.0, 2.5, 3.0, 5.0, 10.0]:
    P_pa = P_bar * 1e5
    exact = IAPWS97(P=P_pa/1e6, x=0).T - 273.15
    spline = thermo.get_T_sat(P_pa) - 273.15
    print(f"P={P_bar} bar | Exact T={exact:.3f} C | Spline T={spline:.3f} C | Error={spline-exact:.3f} C")
