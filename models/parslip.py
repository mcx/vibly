import numpy as np
import scipy.integrate as integrate
import models.slip as slip


def feasible(x, p):
    """
    check if state is at all feasible (body/foot underground)
    returns a boolean
    """
    if x[5] < x[-1] or x[1] < x[-1]:
        return False
    return True


def poincare_map(x, p):
    """
    Wrapper function for step function, returning only x_next, and -1 if failed
    Essentially, the Poincare map.
    """
    if type(p) is dict:
        if not feasible(x, p):
            return x, True  # return failed if foot starts underground
        sol = step(x, p)
        return sol.y[:, -1], check_failure(sol.y[:, -1])
    elif type(p) is tuple:
        vector_of_x = np.zeros(x.shape)  # initialize result array
        vector_of_fail = np.zeros(x.shape[1])
        # TODO: for shorthand, allow just a single tuple to be passed in
        # this can be done easily with itertools
        for idx, p0 in enumerate(p):
            if not feasible(x, p):
                vector_of_x[:, idx] = x[:, idx]
                vector_of_fail[idx] = True
            else:
                sol = step(x[:, idx], p0)  # p0 = p[idx]
                vector_of_x[:, idx] = sol.y[:, -1]
                vector_of_fail[idx] = check_failure(sol.y[:, -1])
        return (vector_of_x, vector_of_fail)
    else:
        print("WARNING: I got a parameter type that I don't understand.")
        return x, True


def step(x0, p, prev_sol=None):
    """
    Take one step from apex to apex/failure.
    returns a sol object from integrate.solve_ivp, with all phases
    """

    # * nested functions - scroll down to step code * #
    # unpacking constants
    MAX_TIME = 1

    # assert(len(x0) == 10)

    # TODO: test what isn't being used
    GRAVITY = p["gravity"]
    MASS = p["mass"]
    SPRING_RESTING_LENGTH = p["resting_length"]
    STIFFNESS = p["stiffness"]
    ACTUATOR_PERIOD = p["actuator_force_period"]
    DAMPING = compute_damping_coefficient(p)
    DELAY = p["activation_delay"]  # can also be negative
    AMPLI = p["activation_amplification"]

    # @jit(nopython=True)
    def flight_dynamics(t, x):
        return np.array([x[2], x[3], 0, -GRAVITY, x[2], x[3], 0])

    def compute_leg_forces(t, x, p):
        """
        Computes the forces developed by the leg spring, and the damper
        and actuator, all of which are parallel.
        """

        # * actuator_force
        if np.shape(p["actuator_force"])[0] > 0:
            act_force = np.interp(
                t,
                p["actuator_force"][0, :] + DELAY,
                p["actuator_force"][1, :],  # force
                period=ACTUATOR_PERIOD,
            )
            act_force *= AMPLI
        else:
            act_force = 0

        # * spring-damper force
        # For numerical stability, we use a huntley-cross model
        # see A COMPUTATIONALLY EFFICIENT MUSCLE MODEL (Millard & Delp 2012)
        # For this, DAMPING * velocity should result in a dimensionless number

        spring_compression = SPRING_RESTING_LENGTH - compute_spring_length(x, p)
        r_dot = compute_spring_velocity(x, p)
        sd_force = STIFFNESS * (spring_compression) * (1 + DAMPING * r_dot)

        return act_force + sd_force

    #    @jit(nopython=True)
    def stance_dynamics(t, x):
        # stance dynamics
        alpha = np.arctan2(x[1] - x[5], x[0] - x[4]) - np.pi / 2.0
        leg_force = compute_leg_forces(t, x, p) / MASS
        xdotdot = -leg_force * np.sin(alpha)
        ydotdot = leg_force * np.cos(alpha) - GRAVITY

        return np.array([x[2], x[3], xdotdot, ydotdot, 0, 0, 0])

    #    @jit(nopython=True)
    def fall_event(t, x):
        """
        Event function to detect the body hitting the floor (failure)
        """
        return x[1]

    fall_event.terminal = True
    fall_event.terminal = -1

    #    @jit(nopython=True)
    def touchdown_event(t, x):
        """
        Event function for foot touchdown (transition to stance)
        """
        # x[1]- np.cos(p['angle_of_attack'])*SPRING_RESTING_LENGTH
        # (which is = x[5])
        return x[5] - x[-1]  # final state is ground height

    touchdown_event.terminal = True  # no longer actually necessary...
    touchdown_event.direction = -1

    #    @jit(nopython=True)
    def liftoff_event(t, x):
        """
        Event function to reach maximum spring extension (transition to flight)
        """
        spring_length = compute_spring_length(x, p)
        event_val = spring_length - SPRING_RESTING_LENGTH
        return event_val

    liftoff_event.terminal = True
    liftoff_event.direction = 1

    #    @jit(nopython=True)
    def apex_event(t, x):
        """
        Event function to reach apex
        """
        return x[3]

    apex_event.terminal = True

    def reversal_event(t, x):
        """
        Event function for direction reversal
        """
        return x[2] + 1e-5  # for numerics, allow for "straight up"

    reversal_event.terminal = True
    reversal_event.direction = -1

    # * Start of step code * #

    # TODO: properly update sol object with all info, not just the trajectories

    # take one step (apex to apex)
    # the "step" function in MATLAB
    # x is the state vector, a list or np.array
    # p is a dict with all the parameters

    # set integration options

    if prev_sol is not None:
        t0 = prev_sol.t[-1]
    else:
        t0 = 0  # starting time

    # * FLIGHT: simulate till touchdown
    events = [fall_event, touchdown_event]
    sol = integrate.solve_ivp(
        flight_dynamics, t_span=[t0, t0 + MAX_TIME], y0=x0, events=events, max_step=0.01
    )

    # TODO Put each part of the step into a list, so you can concat them
    # TODO programmatically, and reduce code length.
    # if you fell, stop now
    if sol.t_events[0].size != 0:  # if empty
        if prev_sol is not None:
            sol.t = np.concatenate((prev_sol.t, sol.t))
            sol.y = np.concatenate((prev_sol.y, sol.y), axis=1)
            sol.t_events = prev_sol.t_events + sol.t_events
        return sol

    # * STANCE: simulate till liftoff
    events = [fall_event, liftoff_event, reversal_event]
    x0 = sol.y[:, -1]
    sol2 = integrate.solve_ivp(
        stance_dynamics,
        t_span=[sol.t[-1], sol.t[-1] + MAX_TIME],
        y0=x0,
        events=events,
        max_step=0.001,
    )

    # if you fell, stop now
    if sol2.t_events[0].size != 0:  # if empty
        # concatenate all solutions
        sol.t = np.concatenate((sol.t, sol2.t))
        sol.y = np.concatenate((sol.y, sol2.y), axis=1)
        sol.t_events += sol2.t_events
        if prev_sol is not None:  # concatenate to previous solution
            sol.t = np.concatenate((prev_sol.t, sol.t))
            sol.y = np.concatenate((prev_sol.y, sol.y), axis=1)
            sol.t_events = prev_sol.t_events + sol.t_events
        return sol

    # * FLIGHT: simulate till apex
    events = [fall_event, apex_event]
    x0 = reset_leg(sol2.y[:, -1], p)
    sol3 = integrate.solve_ivp(
        flight_dynamics,
        t_span=[sol2.t[-1], sol2.t[-1] + MAX_TIME],
        y0=x0,
        events=events,
        max_step=0.01,
    )

    # concatenate all solutions
    sol.t = np.concatenate((sol.t, sol2.t, sol3.t))
    sol.y = np.concatenate((sol.y, sol2.y, sol3.y), axis=1)
    sol.t_events += sol2.t_events + sol3.t_events

    if prev_sol is not None:
        sol.t = np.concatenate((prev_sol.t, sol.t))
        sol.y = np.concatenate((prev_sol.y, sol.y), axis=1)
        sol.t_events = prev_sol.t_events + sol.t_events

    return sol


def check_failure(x):
    """
    Check if a state is in the failure set.
    """

    if np.less_equal(x[1], 0):
        return True
    if np.isclose(x[1], 0):
        return True
    if np.less_equal(x[2], 0):  # check for direction reversal
        return True
    return False


def compute_leg_length(x, p):
    return np.hypot(x[0] - x[4], x[1] - x[5])


def compute_spring_length(x, p):
    return np.hypot(x[0] - x[4], x[1] - x[5]) - p["actuator_resting_length"]


def compute_spring_velocity(x, p):
    beta = np.arctan2(x[5] - x[1], x[4] - x[0])  # aoa
    delta = np.arctan2(x[3], x[2])
    gamma = beta - delta  # + np.pi/2
    return np.hypot(x[2], x[3]) * np.cos(gamma)


def compute_damping_coefficient(p):
    """
    Compute a normalized damping coefficient from the damping ratio.
    This coefficient should have units [s/m], since we are using the
    hunt-crossley model, where total force of the spring-damper is
    F = k*x*(1 + d*xdot)
    We start from a damping ratio, and get the actual damping through critical
    d_a = d_r * d_c = d_r * 2*sqrt(k*m), with units [kg/s].
    We can normalize this either with stiffness and resting length:
    d = d_a / (k * l0)
    or with mass and gravity
    d = d_a / (m * g)
    """
    # * option 2 (normalize with mass and gravity)
    # return p['damping']*2*np.sqrt(p['stiffness']/p['mass'])/p['gravity']
    # * option 1 (normalize with stiffness and resting length)
    return p["damping"] * 2 * np.sqrt(p["mass"] / p["stiffness"]) / p["resting_length"]


def create_force_trajectory(step_sol, p):
    actuator_time_force = np.zeros(shape=(2, len(step_sol.t)))

    # DAMPING = p['damping']*2*np.sqrt(p['stiffness']/p['mass'])/p['gravity']
    DAMPING = compute_damping_coefficient(p)
    for i in range(0, len(step_sol.t)):
        spring_length = slip.compute_spring_length(step_sol.y[:, i], p)
        spring_force = -p["stiffness"] * (spring_length - p["resting_length"])
        spring_velocity = compute_spring_velocity(step_sol.y[:, i], p)
        actuator_time_force[0, i] = step_sol.t[i]  # first column: time
        actuator_time_force[1, i] = -spring_force * DAMPING * spring_velocity
        # force: -b*k*x*xdot: Hunt-Crossley model
    return actuator_time_force


def create_open_loop_trajectories(x0, p, options):
    """
    Create a nominal trajectory based on a SLIP model
    """
    p_slip = p.copy()
    x0_slip = np.concatenate([x0[0:6], x0[-1:]])
    x0_slip = slip.reset_leg(x0_slip, p_slip)
    p_slip["total_energy"] = slip.compute_total_energy(x0_slip, p_slip)
    val, success = slip.find_limit_cycle(x0_slip, p_slip, options)
    if not success:
        print("WARNING: no limit-cycles found")
        return (x0, p)

    searchP = options["search_parameter"]
    if searchP:  # searching over a specific parameter
        p_slip[options["parameter_name"]] = val
        p[options["parameter_name"]] = val
    else:  # searching over state
        x0_slip[options["state_index"]] = val
        x0[options["state_index"]] = val

    p_slip["total_energy"] = slip.compute_total_energy(x0_slip, p_slip)
    p["total_energy"] = compute_total_energy(x0, p)
    sol_slip = slip.step(x0_slip, p_slip)

    # compute open-loop force trajectory from nominal slip traj
    actuator_time_force = create_force_trajectory(sol_slip, p)
    p["actuator_force"] = actuator_time_force
    p["actuator_force_period"] = np.max(actuator_time_force[0, :])

    # t_contact = sol_slip.t_events[1][0]
    # p['angle_of_attack_offset'] = -t_contact*p['swing_velocity']
    # p['swing_leg_length_offset'] = -t_contact*p['swing_extension_velocity']

    # Update the model.step solution
    x0 = reset_leg(x0, p)
    p["total_energy"] = compute_total_energy(x0, p)

    return (x0, p)


def reset_leg(x, p):
    leg_length = p["resting_length"] + p["actuator_resting_length"]
    x[4] = x[0] + np.sin(p["angle_of_attack"]) * leg_length
    x[5] = x[1] - np.cos(p["angle_of_attack"]) * leg_length

    return x


def compute_total_energy(x, p):
    # TODO: make this accept a trajectory, and output parts as well
    if len(x.shape) == 1:
        spring_length = compute_spring_length(x, p)
        energy = (
            p["mass"] / 2 * (x[2] ** 2 + x[3] ** 2)
            + p["gravity"] * p["mass"] * (x[1])
            + p["stiffness"] / 2 * (spring_length - p["resting_length"]) ** 2
        )
        return energy

    energy = np.zeros(x.shape[1])
    for idx in range(energy.size):
        spring_length = compute_spring_length(x[:, idx], p)
        energy[idx] = (
            p["mass"] / 2 * (x[2, idx] ** 2 + x[3, idx] ** 2)
            + p["gravity"] * p["mass"] * (x[1, idx])
            + p["stiffness"] / 2 * (spring_length - p["resting_length"]) ** 2
        )

    return energy


# # TODO refactor this to return ([Kin, Pot_g, Pot_s], [work_a, work_d])
# def compute_potential_kinetic_work_total(state_traj, p):
#     '''
#     Compute potential and kinetic energy, work, and total energy
#     state_traj: trajectory of states (e.g. sol.y)
#     '''
#     cols = np.shape(state_traj)[1]
#     pkwt = np.zeros((5, cols))
#     for i in range(0, cols):
#         spring_length = compute_spring_length(state_traj[:, i])
#         work_actuator = 0
#         work_damper = 0

#         work_actuator = state_traj[7, i]
#         work_damper = state_traj[8, i]

#         spring_energy = 0.5*p['stiffness']*(spring_length
#                                             - p['resting_length'])**2

#         pkwt[0, i] = p['mass']/2*(state_traj[2, i]**2+state_traj[3, i]**2)
#         pkwt[1, i] = p['gravity']*p['mass']*(state_traj[1, i]) + spring_energy
#         pkwt[2, i] = work_actuator
#         pkwt[3, i] = work_damper
#         pkwt[4, i] = pkwt[0, i]+pkwt[1, i]

#     return pkwt

# * Functions for Viability


# TODO: update this to generic names
def map2s_y_xdot_aoa(x, p):
    """
    map an apex state to the low-dim state used for the viability comp
    TODO: make this accept trajectories
    """
    print("TODO: implement this with ground height")
    return np.array([x[1], x[2]])


# def map2x(x, p, s):
#     '''
#     map a desired dimensionless height `s` to it's state-vector
#     '''
#     assert s.size == 2
#     x[1] = s[0]
#     x[2] = s[1]
#     x = reset_leg(x, p)
#     return x


def sa2xp_y_xdot_aoa(state_action, p_def):
    """
    Specifically map state_actions to x and p
    """
    assert len(state_action) == 3
    p = p_def.copy()
    p["angle_of_attack"] = state_action[2]
    x = p["x0"]
    x[1] = state_action[0]  # TODO: reimplement with ground height
    x[2] = state_action[1]
    x = reset_leg(x, p).copy()
    return x, p


def sa2xp_y_xdot_timedaoa(state_action, p_def):
    """
    Specifically map state_actions to x and p
    """
    assert len(state_action) == 3
    p = p_def.copy()
    p["angle_of_attack"] = state_action[2]
    x = p["x0"]
    x[1] = state_action[0]
    x[2] = state_action[1]
    x = reset_leg(x, p).copy()

    # time till foot touches down
    if feasible(x, p):
        time_to_touchdown = np.sqrt(2 * (x[5] - x[-1]) / p["gravity"])
        start_idx = np.argwhere(~np.isclose(p["actuator_force"][1], 0))[0]
        time_to_activation = p["actuator_force"][0, start_idx]
        p["activation_delay"] = time_to_touchdown - time_to_activation

    return x, p


def sa2xp_amp(state_action, p_def):
    """
    Specifically map state_actions to x and p
    """
    assert len(state_action) == 4
    p = p_def.copy()
    p["angle_of_attack"] = state_action[2]
    x = p["x0"]
    x[1] = state_action[0]
    x[2] = state_action[1]
    x = reset_leg(x, p).copy()
    p["activation_amplification"] = state_action[3]

    # time till foot touches down
    if feasible(x, p):
        time_to_touchdown = np.sqrt(2 * (x[5] - x[-1]) / p["gravity"])
        start_idx = np.argwhere(~np.isclose(p["actuator_force"][1], 0))[0]
        time_to_activation = p["actuator_force"][0, start_idx]
        p["activation_delay"] = time_to_touchdown - time_to_activation

    return x, p


def xp2s_y_xdot(x, p):
    return np.array((x[1], x[2]))


def map2s_energy_normalizedheight_aoa(x, p):
    """
    map an apex state to the low-dim state used for the viability comp
    TODO: make this accept trajectories
    """
    potential_energy = p["mass"] * p["gravity"] * x[1]
    total_energy = potential_energy + p["mass"] / 2 * x[2] ** 2
    return np.array([total_energy, potential_energy / total_energy])


def mapSA2xp_energy_normalizedheight_aoa(state_action, p):
    """
    state_action[0]: total energy
    state_action[1]: potential energy / total energy
    state_action[2]: angle of attack
    """
    p["angle_of_attack"] = state_action[2]
    total_energy = state_action[0]
    potential_energy = state_action[1] * total_energy
    kinetic_energy = (1 - state_action[1]) * total_energy
    x = p["x0"]
    x[1] = potential_energy / p["mass"] / p["gravity"]
    x[2] = np.sqrt(2 * kinetic_energy / p["mass"])

    x = reset_leg(x, p)

    return x, p
