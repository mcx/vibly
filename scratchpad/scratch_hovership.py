import numpy as np
import matplotlib.pyplot as plt
import slippy.hovership as sys
from slippy.hovership import p_map
import slippy.viability as vibly

p = {'n_states': 1,
     'gravity': 0.6,
     'thrust': 0,
     'ground_height': 1}
x0 = np.array([0.5, 0])

# poincare_map.p = p
# poincare_map.x = x0
# poincare_map.sa2xp = mapSA2xp_height_angle
# poincare_map.xp2s = map2s
p_map.p = p
p_map.x = x0  # do we still need these? I don't think so...
p_map.sa2xp = sys.sa2xp
p_map.xp2s = sys.xp2s

s_grid = (np.linspace(-0.05, 1.1*p['ground_height'], 101),)

a_grid = (np.linspace(0.0, 0.5, 51),)

grids = {'states': s_grid, 'actions': a_grid}
Q_map, Q_F, Q_on_grid = vibly.compute_Q_map(grids, p_map, check_grid=True)
Q_V, S_V = vibly.compute_QV(Q_map, grids, ~Q_F, Q_on_grid=Q_on_grid)
S_M = vibly.project_Q2S(Q_V, grids, np.mean)
Q_M = vibly.map_S2Q(Q_map, S_M, Q_V)
# save file
# data2save = {"s_grid": s_grid, "a_grid": a_grid, "Q_map": Q_map, "Q_F": Q_F,
#             "poincare_map":poincare_map, "p":p}
# np.savez('test.npz', **data2save)

# S_M = vibly.project_Q2S(Q_V, grids, proj_opt=np.mean)

plt.imshow(Q_M)
plt.show()
# plt.imshow(Q_V)
# plt.show()