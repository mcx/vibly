import numpy as np
import matplotlib.pyplot as plt

import models.daslip as model
import viability as vibly

# * First, solve for the operating point to get an open-loop force traj
if __name__ == "__main__":
    p = {
        "mass": 80,  # kg
        "stiffness": 8200,  # K : N/m  just a guess, this will be fit
        "resting_length": 0.9,  # m
        "gravity": 9.81,  # N/kg
        "angle_of_attack": 1 / 5 * np.pi,  # rad
        "actuator_resting_length": 0.1,  # m
        "actuator_force": [],  # * 2 x M matrix of time and force
        "actuator_force_period": 10,  # * s
        "activation_delay": 0.0,  # * a delay for when to start activation
        "activation_amplification": 1.0,  # 1 for no amplification
        "constant_normalized_damping": 0.75,  # * s : D/K : [N/m/s]/[N/m]
        "linear_normalized_damping": 3.5,  # * A: s/m : D/F : [N/m/s]/N
        "linear_minimum_normalized_damping": 0.05,  # for numerical stability)
        "swing_velocity": 0,  # rad/s (set by calculation)
        "angle_of_attack_offset": 0,  # rad   (set by calculation)
        "swing_extension_velocity": 0,  # m/s
        "swing_leg_length_offset": 0,
    }  # m (set by calculation)

    x0 = np.array(
        [
            0,
            1.00,  # x_com , y_com
            5.5,
            0,  # vx_com, vy_com
            0,
            0,  # foot x, foot y (set below)
            p["actuator_resting_length"],  # actuator initial length
            0,
            0,  # work actuator, work damper
            0,
        ]
    )  # ground height h

    x0 = model.reset_leg(x0, p)
    p["total_energy"] = model.compute_total_energy(x0, p)
    legStiffnessSearchWidth = p["stiffness"] * 0.5
    limit_cycle_options = {
        "search_initial_state": False,
        "state_index": 2,  # not used
        "state_search_width": 2.0,  # not used
        "search_parameter": True,
        "parameter_name": "stiffness",
        "parameter_search_width": legStiffnessSearchWidth,
    }

    print(p["stiffness"], " N/m :Leg stiffness prior to fitting")
    x0, p = model.create_open_loop_trajectories(x0, p, limit_cycle_options)
    print(p["stiffness"], " N/m :Leg stiffness after fitting")

    p["x0"] = x0
    # initialize default x0_daslip
    p_map = model.poincare_map
    p_map.p = p
    p_map.x = x0
    p_map.sa2xp = model.sa2xp_y_xdot_timedaoa
    p_map.xp2s = model.xp2s_y_xdot

    s_grid_height = np.linspace(0.5, 1.5, 26)
    s_grid_velocity = np.linspace(1, 6, 26)
    s_grid = (s_grid_height, s_grid_velocity)
    a_grid = (np.linspace(20 / 180 * np.pi, 60 / 180 * np.pi, 25),)

    grids = {"states": s_grid, "actions": a_grid}
    Q_map, Q_F = vibly.parcompute_Q_map(grids, p_map, verbose=2)
    Q_V, S_V = vibly.compute_QV(Q_map, grids)
    S_M = vibly.project_Q2S(Q_V, grids, proj_opt=np.mean)
    Q_M = vibly.map_S2Q(Q_map, S_M, s_grid=s_grid, Q_V=Q_V)
    print("non-failing portion of Q: " + str(np.sum(~Q_F) / Q_F.size))
    print("viable portion of Q: " + str(np.sum(Q_V) / Q_V.size))

    ###############################################################################
    # save data as pickle
    ###############################################################################
    # import pickle
    # filename = 'daslip.pickle'
    # data2save = {"grids": grids, "Q_map": Q_map, "Q_F": Q_F, "Q_V": Q_V,
    #              "Q_M": Q_M, "S_M": S_M, "p": p, "x0": x0}
    # outfile = open(filename, 'wb')
    # pickle.dump(data2save, outfile)
    # outfile.close()
    # to load this data, do:
    # infile = open(filename, 'rb')
    # data = pickle.load(infile)
    # infile.close()

    plt.imshow(S_V, origin="lower")
    plt.show()

    plt.imshow(S_M, origin="lower")
    plt.show()
