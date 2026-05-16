import numpy as np
from model import coefficients as coef
P = 1.013e5 + 0.16e5
V_dw = 0.0044
for phi in [0.0, 0.005, 0.5, 0.99]:
    C = coef.calculate_matrix_C(P, V_dw, phi)
    det = np.linalg.det(C)
    print(f"phi={phi:5.3f}, det(C)={det:10.3e}")
