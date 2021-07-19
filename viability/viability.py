import itertools as it
import numpy as np

'''
Tools for computing the viable set (in state-action space) and viability kernel (in state space) of a dynamical system. Note, all methods appended with `_2D` are specific to 2D systems and deprecated. They are left here since they are a lot easier to read, in case you're interested in understanding what the code is doing.

For all practical use, refer to the N-D versions.
'''
def compute_Q_2D(s_grid, a_grid, p_map):
    ''' Compute the transition map of a system with 1D state and 1D action
    NOTES
    - s_grid and a_grid have to be iterable lists of lists
    e.g. if they have only 1 dimension, they should be `s_grid = ([1, 2], )`
    - use p_map to carry parameters
    '''

    # create iterators s_grid, a_grid
    # TODO: pass in iterators/generators instead
    # compute each combination, store result in a huge matrix

    # initialize 1D, reshape later
    Q_map = np.zeros((s_grid.size*a_grid.size, 1))
    Q_F = np.zeros((s_grid.size*a_grid.size, 1))

    # QTransition = Q_map
    n = len(s_grid)*len(a_grid)
    for idx, state_action in enumerate(it.product(s_grid, a_grid)):
        if idx % (n/10) == 0:
            print('.', end=' ')
        x, p = p_map.sa2xp(state_action, p_map.p)
        x_next, failed = p_map(x, p)
        if not failed:
            s_next = p_map.xp2s(x_next, p)
            # note: Q_map is implicitly already excluding transitions that
            # move straight to a failure. While this is not equivalent to the
            # algorithm in the paper, for our systems it is a bit faster
            Q_map[idx] = s_next
        else:
            Q_F[idx] = 1

    return (Q_map.reshape((s_grid.size, a_grid.size)),  # only 2D
            Q_F.reshape((s_grid.size, a_grid.size)))


def project_Q2S_2D(Q):
    S = np.zeros((Q.shape[0], 1))
    for sdx, val in enumerate(S):
        if sum(Q[sdx, :]) > 0:
            S[sdx] = 1
    return S


def is_outside_2D(s, S_V, s_grid):
    '''
    given a level set S, check if s is inside S or not
    '''
    if sum(S_V) <= 1:
        return True

    s_min, s_max = s_grid[S_V > 0][[0, -1]]
    if s > s_max or s < s_min:
        return True
    else:
        return False


def compute_QV_2D(Q_map, grids, Q_V=None):
    ''' Starting from the transition map and set of non-failing state-action
    pairs, compute the viable sets. The input Q_V is referred to as Q_N in the
    paper when passing it in, but since it is immediately copied to Q_V, we
    directly use this naming.
    '''

    # Take Q_map as the non-failing set if Q_N is omitted
    if Q_V is None:
        Q_V = np.copy(Q_map)
        Q_V[Q_V > 0] = 1

    S_old = np.zeros((Q_V.shape[0], 1))
    S_V = project_Q2S_2D(Q_V)
    while np.array_equal(S_V, S_old):
        for qdx, is_viable in enumerate(np.nditer(Q_V)):  # compare w/ np.enum
            if is_viable:  # only check previously viable (s, a)
                if is_outside_2D(Q_map[qdx], S_V, grids['states']):
                    Q_V[qdx] = 0  # remove
        S_old = S_V
        S_V = project_Q2S_2D(Q_V)

    return Q_V, S_V


# ** Reimplement everything as N-D


def get_state_from_ravel(bin_idx, s_grid):
    '''
    Get state from bin id. Ideally, interpolate
    For now, just returning a grid point
    '''
    bin_idx = np.atleast_1d(bin_idx)
    grid_idx = np.zeros(len(s_grid), dtype='int')
    s = np.zeros(len(s_grid))
    for dim, grid in enumerate(s_grid):
        if bin_idx[dim] >= grid.size:
            grid_idx[dim] = grid.size-1  # upper-est entry
            s[dim] = grid[grid_idx[dim]]
        else:
            grid_idx[dim] = bin_idx[dim]  # just put the right-closest grid
            s[dim] = grid[grid_idx[dim]]
    return s


def bin2grid(bin_idx, grids):
    '''
    To replace `get_state_from_ravel`
    receiving a tuple of grids, return the grid-
    '''


def digitize_s(s, s_grid, shape=None, to_bin=True):
    '''
    s_grid is a tuple/list of 1-D grids. digitize_s finds the corresponding
    index of the bin overlaid on the N-dimensional grid S.

    Assumes you wat to bin things by default, turn to_bin to false to return
    closest grid coordinates.

    output:
    - either an array of indices of N dimensions
    - a raveled index
    '''
    # assert type(s_grid) is tuple or type(s_grid) is list
    s = np.atleast_1d(s)  # make this indexable even if scalar
    s_idx = np.zeros((len(s_grid)), dtype=int)
    if to_bin:
        for dim_idx, grid in enumerate(s_grid):  # TODO: can zip this with s
            s_idx[dim_idx] = np.digitize(s[dim_idx], grid)
    else:
        for dim_idx, grid in enumerate(s_grid):
            s_idx[dim_idx] = np.argmin(np.abs(grid - s[dim_idx]))

    if shape is None:
        return s_idx
    else:
        return np.ravel_multi_index(s_idx, shape)


def compute_Q_map(grids, p_map, verbose=0, check_grid=False,
                  keep_coords=False):
    ''' Compute the transition map of a system
    NOTES
    - s_grid and a_grid have to be iterable lists of lists
    e.g. if they have only 1 dimension, they should be `s_grid = ([1, 2], )`
    - use p_map to carry parameters
    - keep_coords: toggle to true to also output an array of actual states
    '''
    # TODO get rid of check_grid, solve the problem permanently

    # initialize 1D, reshape later
    # shape of state-space grid
    s_grid_shape = list(map(np.size, grids['states']))
    s_bin_shape = tuple(dim+1 for dim in s_grid_shape)
    a_grid_shape = list(map(np.size, grids['actions']))
    total_gridpoints = np.prod(s_grid_shape)*np.prod(a_grid_shape)

    if verbose > 0:
        print('computing a total of ' + str(total_gridpoints) + ' points.')

    Q_map = np.zeros((total_gridpoints, 1), dtype=int)
    Q_F = np.zeros((total_gridpoints, 1), dtype=bool)
    if keep_coords:
        Q_reached = np.zeros((len(grids['states']), total_gridpoints))

    if check_grid:
        Q_on_grid = np.copy(Q_F)  # HACK: keep track of wether you are in a bin

    for idx, state_action in enumerate(np.array(list(
            it.product(*grids['states'], *grids['actions'])))):

        if verbose > 1:
            # NOTE: requires running python unbuffered (python -u)
            if idx % (total_gridpoints/10) == 0:
                print('.', end=' ')

        x, p = p_map.sa2xp(state_action, p_map.p)

        x_next, failed = p_map(x, p)

        s_next = p_map.xp2s(x_next, p)
        if keep_coords:
            Q_reached[:, idx] = s_next
        if not failed:
            # note: Q_map is implicitly already excluding transitions that
            # move straight to a failure. While this is not equivalent to the
            # algorithm in the paper, for our systems it is a bit faster
            # bin_idx = np.digitize(state_val, s_grid[state_dx])
            # sbin = np.digitize(s_next, s)
            if check_grid:
                for sdx, sval in enumerate(np.atleast_1d(s_next)):
                    if ~np.isin(sval, grids['states'][sdx]):
                        Q_map[idx] = digitize_s(s_next, grids['states'],
                                                s_bin_shape)
                        break
                else:
                    Q_on_grid[idx] = True
                    Q_map[idx] = digitize_s(s_next, grids['states'],
                                            s_grid_shape, to_bin=False)
            else:
                Q_map[idx] = digitize_s(s_next, grids['states'], s_bin_shape)

            # check if s happens to be right on the grid-point
        else:
            Q_F[idx] = 1

    Q_map = Q_map.reshape(s_grid_shape + a_grid_shape)
    Q_F = Q_F.reshape(s_grid_shape + a_grid_shape)

    deliver = [Q_map, Q_F]

    if check_grid:
        deliver.append(Q_on_grid.reshape(s_grid_shape+a_grid_shape))
    if keep_coords:
        deliver.append(Q_reached)

    return deliver


def project_Q2S(Q, grids, proj_opt=None):
    if proj_opt is None:
        proj_opt = np.any
    a_axes = tuple(range(Q.ndim - len(grids['actions']), Q.ndim))
    return proj_opt(Q, a_axes)


def compute_QV(Q_map, grids, Q_V=None, Q_on_grid=None):
    '''
    Starting from the transition map and set of non-failing state-action
    pairs, compute the viable sets. The input Q_V is referred to as Q_N in the
    paper when passing it in, but since it is immediately copied to Q_V, we
    directly use this naming.
    '''

    # initialize estimate of Q_V
    if Q_V is None:
        Q_V = np.copy(Q_map)
        Q_V = Q_V.astype(bool)
    # if you have no info, treat everything as if in a bin
    if Q_on_grid is None:
        Q_on_grid = np.zeros(Q_V.shape, dtype=bool)
    # initialize empty of S_old
    # initialize estimate of S_V
    S_V = project_Q2S(Q_V, grids)
    S_old = np.zeros_like(S_V)

    # while S_V != S_old
    while not np.array_equal(S_V, S_old):
        # iterate over all s in S_V
        for qdx, is_viable in np.ndenumerate(Q_V):
            # iterate over all a
            if is_viable:
                # if s_k isOutside S_V:
                if is_outside(Q_map[qdx], grids['states'], S_V,
                              on_grid=Q_on_grid[qdx]):
                    Q_V[qdx] = False
                    # remove (s,a) from Q_V
        S_old = S_V
        S_V = project_Q2S(Q_V, grids)

    return Q_V, S_V


def is_outside(s, s_grid, S_V, already_binned=True, on_grid=False):
    '''
    given a level set S, check if s lands in a bin inside of S or not
    '''

    # only checking 1 state vector
    if not already_binned:
        bin_idx = digitize_s(s, s_grid)  # get unraveled indices
    else:
        bin_idx = np.unravel_index(s, tuple(x+1 for x in map(np.size, s_grid)))

    if on_grid:  # s is already binned in the flat
        s_grid_shape = list(map(np.size, s_grid))
        sdx = np.unravel_index(s, s_grid_shape)
        if S_V[sdx]:
            return False
        else:
            return True

    edge_indices = get_grid_indices(bin_idx, s_grid)

    if len(edge_indices) > 0:
        for idx in edge_indices:
            if not S_V[idx]:
                return True
    else:
        return True

    return False
    # for dim_idx, grid in enumerate(s_grid):
    #     # if outside the left-most or right-most side of grid, mark as outside
    #     # * NOTE: this can result in disastrous underestimations if the grid is
    #     # * not larger than the viable set!
    #     # TODO: this can lead to understimation if s is right on the gridline
    #     # because it will still check its neighbors. need to first check.
    #     if bin_idx[dim_idx] == 0:
    #         return True
    #     elif bin_idx[dim_idx] >= grid.size:
    #         return True
    # # Need to redo the loop. In the first loop, we check if any of the points
    # # has exited the grid. This needs to be done first to ensure we don't try
    # # to index outside the grid
    # for dim_idx, grid in enumerate(s_grid):
    #     # check if enclosing grid points are viable or not
    #     index_vec = np.zeros(len(s_grid), dtype=int)
    #     index_vec[dim_idx] = 1
    #     if (not S_V[tuple(bin_idx)] or
    #             not S_V[tuple(bin_idx - index_vec)]):
    #         return True

    #     return False


def get_grid_indices(bin_idx, s_grid):
    '''
    from a bin index (unraveled), get surrounding grid indices. Returns a list
    of tuples.
    '''

    grid_coords = list()
    for neighbor in it.product(*[(x-1, x) for x in bin_idx]):
        # check if neighbor is out of bounds
        for idx, x in enumerate(neighbor):
            if x<0 or x>=s_grid[idx].size:
                break
        else:  # if for loop completes (not out of bounds)
            grid_coords.append(neighbor)

    return grid_coords


def map_S2Q(Q_map, S_M, s_grid, Q_V=None, Q_on_grid=None):
    '''
    map the measure of robustness of S to the state action space Q, via
    inverse dynamics (using the lookup table).
    '''

    # TODO s_grid isn't strictly needed, can be done without it

    if Q_on_grid is None:
        Q_on_grid = np.zeros_like(Q_map, dtype=bool)

    if Q_V is None:
        Q_V = Q_map.astype(bool)

    Q_M = np.zeros(Q_map.shape)
    # iterate over viable state-action pairs in Q_V
    for qdx, is_viable in np.ndenumerate(Q_V):
        if is_viable:  # only check states-action pairs that are viable
            if Q_on_grid[qdx]:
                sdx = np.unravel_index(Q_map[qdx], S_M.shape)
            else:
                sdx = np.unravel_index(Q_map[qdx],
                                       list(x+1 for x in S_M.shape))
            edge_indices = get_grid_indices(sdx, s_grid)

            # TODO check that it actually has the right size
            measure = 0
            # taking the average measure of all enclosing grid-points
            if len(edge_indices) > 0:
                for idx in edge_indices:
                    measure += S_M[(idx)]
                measure /= len(edge_indices)

            # If sdx is on the outer edge, don't map it

            Q_M[qdx] = measure

    return Q_M


def get_feasibility_mask(feasible, sa2xp, grids, x0, p0):
    '''
    cycle through the state and action grids, and check if that state-action
    pair is feasible or nay. Returns an ND array of booleans.

    feasible: function to check if a state and parameter are feasible
    sa2xp: mapping to go from state-action to x and p
    grids: grids of states and actions

    x0: a default x0, used to fill out x0 (used by sa2xp)

    p: a default parameter dict, used to fill out p
    '''
    # initialize 1D, reshape later
    s_shape = list(map(np.size, grids['states']))  # shape of state-space grid
    a_shape = list(map(np.size, grids['actions']))
    Q_feasible = np.zeros(np.prod(s_shape)*np.prod(a_shape), dtype=bool)

    # TODO: can probably simplify this
    for idx, state_action in enumerate(np.array(list(
            it.product(*grids['states'], *grids['actions'])))):
        x, p = sa2xp(state_action, p0)
        Q_feasible[idx] = feasible(x, p)

    return Q_feasible.reshape(s_shape + a_shape)


# def compute_Q_cont(grids, p_map, verbose=0):
#     ''' Compute the transition map of a system, and output the result _without_
#     discretizing into bins, as an array of coordinate vectors (n, m) where
#     n is the dimensionality of state, and m are the number of grid-points
#     NOTES
#     - s_grid and a_grid have to be iterable lists of lists
#     e.g. if they have only 1 dimension, they should be `s_grid = ([1, 2], )`
#     - use p_map to carry parameters
#     '''

#     # initialize 1D, reshape later
#     # shape of state-space grid
#     # initialize 1D, reshape later
#     # shape of state-space grid
#     s_grid_shape = list(map(np.size, grids['states']))
#     a_grid_shape = list(map(np.size, grids['actions']))
#     total_gridpoints = np.prod(s_grid_shape)*np.prod(a_grid_shape)

#     if verbose > 0:
#         print('computing a total of ' + str(total_gridpoints) + ' points.')

#     # Q_map = np.zeros((total_gridpoints, 1), dtype=int)
#     Q_map = np.zeros((len(grids['states']), total_gridpoints))
#     Q_F = np.zeros((total_gridpoints, 1), dtype=bool)

#     for idx, state_action in enumerate(np.array(list(
#             it.product(*grids['states'], *grids['actions'])))):

#         if verbose > 1:
#             # NOTE: requires running python unbuffered (python -u)
#             if idx % (total_gridpoints/10) == 0:
#                 print('.', end=' ')

#         x, p = p_map.sa2xp(state_action, p_map.p)
#         x_next, failed = p_map(x, p)
#         s_next = p_map.xp2s(x_next, p)
#         Q_map[:, idx] = s_next
#         if failed:
#             Q_F[idx] = True

#     return (Q_map, Q_F)


def parcompute_Q_map(grids, p_map, verbose=0, check_grid=False,
                     keep_coords=False):
    ''' Compute the transition map of a system in parallel
    - s_grid and a_grid have to be iterable lists of lists
    e.g. if they have only 1 dimension, they should be `s_grid = ([1, 2], )`
    - use p_map to carry parameters
    - keep_coords: toggle to true to also output an array of actual states
    '''

    import multiprocessing as mp

    # initialize 1D, reshape later
    # shape of state-space grid
    s_grid_shape = list(map(np.size, grids['states']))
    s_bin_shape = tuple(dim+1 for dim in s_grid_shape)
    a_grid_shape = list(map(np.size, grids['actions']))
    total_gridpoints = np.prod(s_grid_shape)*np.prod(a_grid_shape)
    if verbose > 0:
        print('computing a total of ' + str(total_gridpoints) + ' points.')

    # initilize pool
    pool = mp.Pool()
    # create list of args
    SA = list(it.product(*grids['states'], *grids['actions']))
    # for sa in SA:
    #     print(sa[1],end=' in a, and ')
    p = p_map.p.copy()
    args = [p_map.sa2xp(sa, p) for sa in SA]
    # for ar in args:
    #     print(ar[1]['angle_of_attack'], end='')
    #     print(" and " + str(ar[0][1]))
    # start pool with starmap
    results = pool.starmap(p_map, args)
    pool.close()

    # for r in results:
    #     print(r[0])

    # do the standard stuff (put into bins etc.)

    Q_map = np.zeros((total_gridpoints, 1), dtype=int)
    Q_F = np.zeros((total_gridpoints, 1), dtype=bool)
    if keep_coords:
        Q_reached = np.zeros((len(grids['states']), total_gridpoints))

    if check_grid:
        Q_on_grid = np.copy(Q_F)  # HACK: keep track of wether you are in a bin

    # TODO: no need to use it.product here, since we just use the index
    for idx, sa in enumerate(np.array(list(it.product(*grids['states'],
                                                      *grids['actions'])))):

        x_next, failed = results[idx]
        s_next = p_map.xp2s(x_next, p)
        if keep_coords:
            Q_reached[:, idx] = s_next
        if not failed:
            if check_grid:
                for sdx, sval in enumerate(np.atleast_1d(s_next)):
                    if ~np.isin(sval, grids['states'][sdx]):
                        Q_map[idx] = digitize_s(s_next, grids['states'],
                                                s_bin_shape)
                        break
                else:
                    Q_on_grid[idx] = True
                    Q_map[idx] = digitize_s(s_next, grids['states'],
                                            s_grid_shape, to_bin=False)
            else:
                Q_map[idx] = digitize_s(s_next, grids['states'], s_bin_shape)

            # check if s happens to be right on the grid-point
        else:
            Q_F[idx] = 1

    Q_map = Q_map.reshape(s_grid_shape + a_grid_shape)
    Q_F = Q_F.reshape(s_grid_shape + a_grid_shape)

    deliver = [Q_map, Q_F]

    if check_grid:
        deliver.append(Q_on_grid.reshape(s_grid_shape+a_grid_shape))
    if keep_coords:
        deliver.append(Q_reached)

    return deliver
