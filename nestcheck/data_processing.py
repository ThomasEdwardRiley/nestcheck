#!/usr/bin/env python
"""
Functions for processing nested sampling samples.
"""

import numpy as np
import nestcheck.io_utils as iou


def process_polychord_run(root):
    """
    Loads data from PolyChord run into the standard nestcheck format.
    """
    dead_points = np.loadtxt(root + '_dead.txt')
    ns_run = process_polychord_dead_points(dead_points)
    try:
        info = iou.pickle_load(root + '_info')
        for key in ['output', 'settings']:
            assert key not in ns_run
            ns_run[key] = info.pop(key)
        assert not info
        # Run some tests
        # --------------
        # For the standard ns case
        if not ns_run['settings']['nlives']:
            nthread = np.unique(ns_run['thread_labels']).shape[0]
            assert nthread == ns_run['settings']['nlive'], \
                str(nthread) + '!=' + str(ns_run['settings']['nlive'])
            standard_nlive_array = np.zeros(ns_run['logl'].shape)
            standard_nlive_array += ns_run['settings']['nlive']
            for i in range(1, ns_run['settings']['nlive']):
                standard_nlive_array[-i] = i
            assert np.array_equal(ns_run['nlive_array'],
                                  standard_nlive_array)
    except OSError:
        pass
    return ns_run


def process_polychord_dead_points(dead_points):
    """
    tbc
    """
    dead_points = dead_points[np.argsort(dead_points[:, 0])]
    # Treat dead points
    ns_run = {}
    ns_run['logl'] = dead_points[:, 0]
    repeat_logls = ns_run['logl'].shape[0] - np.unique(ns_run['logl']).shape[0]
    assert repeat_logls == 0, \
        '# unique logl values is ' + str(repeat_logls) + ' less than # points'
    ns_run['birth_step'] = dead_points[:, 1].astype(int)
    assert np.array_equal(ns_run['birth_step'], dead_points[:, 1]), \
        'birth_step values should all be integers!'
    # birth contours with value 0 are sometimes printed to the dead points file
    # by PolyChord as -2^31 due to Fortran io errors
    if np.any(ns_run['birth_step'] == -2147483648):
        assert not np.any(ns_run['birth_step'] == 0)
        print('WARNING: dead points birth contours use -2147483648 instead '
              + 'of zero')
        ns_run['birth_step'][np.where(
            ns_run['birth_step'] == -2147483648)[0]] = 0
    ns_run['theta'] = dead_points[:, 2:]
    ns_run['thread_labels'] = threads_given_birth_order(ns_run['birth_step'])
    # perform some checks
    # nlive = dead_points.shape[0] - np.count_nonzero(dead_points[:, 1])
    # assert np.unique(ns_run['thread_labels'][-nlive:]).shape[0] == nlive, \
    #     'The final nlive=' + str(nlive) + ' points of the run are not all ' \
    #     'from different threads!'
    # get thread min max
    unique_threads = np.unique(ns_run['thread_labels'])
    # Work out nlive_array and thread_min_max logls from thread labels and
    # birth contours
    thread_min_max = np.zeros((unique_threads.shape[0], 2))
    # NB delta_nlive indexes are offset from points' indexes by 1 as we need an
    # element to repesent the initial sampling of live points before any dead
    # points are created.
    # I.E. birth on step 1 corresponds to replacing dead point zero
    delta_nlive = np.zeros(dead_points.shape[0] + 1)
    for i, label in enumerate(unique_threads):
        inds = np.where(ns_run['thread_labels'] == label)[0]
        birth = ns_run['birth_step'][inds[0]]
        death = inds[-1] + 1
        delta_nlive[birth] += 1
        delta_nlive[death] -= 1
        if birth == 0:
            # thread minimum is -inf it starts by sampling from whole prior
            thread_min_max[i, 0] = -np.inf
        else:
            thread_min_max[i, 0] = ns_run['logl'][birth - 1]
        # Max is final logl in thread
        thread_min_max[i, 1] = ns_run['logl'][death - 1]
    ns_run['thread_min_max'] = thread_min_max
    ns_run['nlive_array'] = np.cumsum(delta_nlive)[:-1]
    return ns_run


def threads_given_birth_order(birth_order):
    """
    Divides a nested sampling run into threads, using info on the contours at
    which points were sampled.
    """
    unique, counts = np.unique(birth_order, return_counts=True)
    multi_birth_steps = unique[np.where(counts > 1)]
    thread_labels = np.zeros(birth_order.shape)
    thread_num = 0
    for nstep, step in enumerate(multi_birth_steps):
        for i, start_ind in enumerate(np.where(birth_order == step)[0]):
            # unless nstep=0 the first point born on the contour (i=0) is
            # already assigned to a thread
            if i != 0 or nstep == 0:
                thread_num += 1
                # check point has not already been assigned
                assert thread_labels[start_ind] == 0
                thread_labels[start_ind] = thread_num
                # find the point which replaced it
                next_ind = np.where(birth_order == (start_ind + 1))[0]
                while next_ind.shape != (0,):
                    # check point has not already been assigned
                    assert thread_labels[next_ind[0]] == 0
                    thread_labels[next_ind[0]] = thread_num
                    # find the point which replaced it
                    next_ind = np.where(birth_order == (next_ind[0] + 1))[0]
    assert np.all(thread_labels != 0), \
        ('Point not given a thread labels! Indexes='
         + str(np.where(thread_labels == 0)[0]))
    assert np.array_equal(thread_labels, thread_labels.astype(int)), \
        'Thread labels should all be ints!'
    thread_labels = thread_labels.astype(int)
    # Check unique thread labels are a sequence from 1 to nthreads as expected
    n_threads = (np.sum(counts[np.where(counts > 1)]) -
                 (multi_birth_steps.shape[0] - 1))
    assert np.array_equal(np.unique(thread_labels),
                          np.asarray(range(1, n_threads + 1)))
    return thread_labels
