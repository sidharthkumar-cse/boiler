import time
from iapws import IAPWS97
import numpy as np

start = time.time()
print("building table")
P_range = np.linspace(1000.0, 1e6, 1000)
for P in P_range:
    s = IAPWS97(P=P/1e6, x=1)
    k = s.rho
print(f"Time taken: {time.time() - start:.3f} s")
