"""Classical AMG (Ruge-Stuben AMG)."""
from __future__ import absolute_import


from warnings import warn
from scipy.sparse import csr_matrix, isspmatrix_csr, SparseEfficiencyWarning

from pyamg.multilevel import multilevel_solver
from pyamg.relaxation.smoothing import change_smoothers
from pyamg.strength import *
from pyamg.classical.interpolate import *
from pyamg.classical.split import *
from pyamg.classical.cr import CR

__all__ = ['ruge_stuben_solver']


def ruge_stuben_solver(A,
                       strength=('classical', {'theta': 0.25}),
                       CF='RS',
                       interpolation='standard',
                       presmoother=('gauss_seidel', {'sweep': 'symmetric'}),
                       postsmoother=('gauss_seidel', {'sweep': 'symmetric'}),
                       max_levels=30, max_coarse=20, keep=False, **kwargs):
    """Create a multilevel solver using Classical AMG (Ruge-Stuben AMG)

    Parameters
    ----------
    A : csr_matrix
        Square matrix in CSR format
    strength : ['symmetric', 'classical', 'evolution', 'distance',
                'algebraic_distance','affinity', 'energy_based', None]
        Method used to determine the strength of connection between unknowns
        of the linear system.  Method-specific parameters may be passed in
        using a tuple, e.g. strength=('symmetric',{'theta' : 0.25 }). If
        strength=None, all nonzero entries of the matrix are considered strong.
    CF : {string} : default 'RS'
        Method used for coarse grid selection (C/F splitting)
        Supported methods are RS, PMIS, PMISc, CLJP, CLJPc, and CR.
    interpolation : {string} : default 'standard'
        Method for interpolation. Options include 'direct', 'standard', and
        'distance_two'.
    presmoother : {string or dict}
        Method used for presmoothing at each level.  Method-specific parameters
        may be passed in using a tuple, e.g.
        presmoother=('gauss_seidel',{'sweep':'symmetric}), the default.
    postsmoother : {string or dict}
        Postsmoothing method with the same usage as presmoother
    max_levels: {integer} : default 30
        Maximum number of levels to be used in the multilevel solver.
    max_coarse: {integer} : default 20
        Maximum number of variables permitted on the coarse grid.
    keep: {bool} : default False
        Flag to indicate keeping extra operators in the hierarchy for
        diagnostics, such as strength of connection (C).

    Returns
    -------
    ml : multilevel_solver
        Multigrid hierarchy of matrices and prolongation operators

    Examples
    --------
    >>> from pyamg.gallery import poisson
    >>> from pyamg import ruge_stuben_solver
    >>> A = poisson((10,),format='csr')
    >>> ml = ruge_stuben_solver(A,max_coarse=3)

    Notes
    -----
    "coarse_solver" is an optional argument and is the solver used at the
    coarsest grid.  The default is a pseudo-inverse.  Most simply,
    coarse_solver can be one of ['splu', 'lu', 'cholesky, 'pinv',
    'gauss_seidel', ... ].  Additionally, coarse_solver may be a tuple
    (fn, args), where fn is a string such as ['splu', 'lu', ...] or a callable
    function, and args is a dictionary of arguments to be passed to fn.
    See [0] for additional details.


    References
    ----------
    .. [0] Trottenberg, U., Oosterlee, C. W., and Schuller, A.,
       "Multigrid" San Diego: Academic Press, 2001.  Appendix A

    See Also
    --------
    aggregation.smoothed_aggregation_solver, multilevel_solver,
    aggregation.rootnode_solver

    """
    levels = [multilevel_solver.level()]

    # convert A to csr
    if not isspmatrix_csr(A):
        try:
            A = csr_matrix(A)
            warn("Implicit conversion of A to CSR",
                 SparseEfficiencyWarning)
        except BaseException:
            raise TypeError('Argument A must have type csr_matrix, \
                             or be convertible to csr_matrix')
    # preprocess A
    A = A.asfptype()
    if A.shape[0] != A.shape[1]:
        raise ValueError('expected square matrix')

    levels[-1].A = A

    while len(levels) < max_levels and levels[-1].A.shape[0] > max_coarse:
        extend_hierarchy(levels, strength, CF, keep)

    ml = multilevel_solver(levels, **kwargs)
    change_smoothers(ml, presmoother, postsmoother)
    return ml


# internal function
def extend_hierarchy(levels, strength, CF, keep):
    """Extend the multigrid hierarchy."""
    def unpack_arg(v):
        if isinstance(v, tuple):
            return v[0], v[1]
        else:
            return v, {}

    A = levels[-1].A
    
    # Check if matrix was filtered to be diagonal --> coarsest grid
    if A.nnz == A.shape[0]:
        return 1

    # Compute the strength-of-connection matrix C, where larger
    # C[i,j] denote stronger couplings between i and j.
    fn, kwargs = unpack_arg(strength)
    if fn == 'symmetric':
        C = symmetric_strength_of_connection(A, **kwargs)
    elif fn == 'classical':
        C = classical_strength_of_connection(A, **kwargs)
    elif fn == 'distance':
        C = distance_strength_of_connection(A, **kwargs)
    elif (fn == 'ode') or (fn == 'evolution'):
        C = evolution_strength_of_connection(A, **kwargs)
    elif fn == 'energy_based':
        C = energy_based_strength_of_connection(A, **kwargs)
    elif fn == 'algebraic_distance':
        C = algebraic_distance(A, **kwargs)
    elif fn == 'affinity':
        C = affinity_distance(A, **kwargs)
    elif fn is None:
        C = A
    else:
        raise ValueError('unrecognized strength of connection method: %s' %
                         str(fn))

    # Generate the C/F splitting
    fn, kwargs = unpack_arg(CF)
    if fn == 'RS':
        splitting = RS(C, **kwargs)
    elif fn == 'PMIS':
        splitting = PMIS(C, **kwargs)
    elif fn == 'PMISc':
        splitting = PMISc(C, **kwargs)
    elif fn == 'CLJP':
        splitting = CLJP(C, **kwargs)
    elif fn == 'CLJPc':
        splitting = CLJPc(C, **kwargs)
    elif fn == 'CR':
        splitting = CR(C, **kwargs)
    else:
        raise ValueError('unknown C/F splitting method (%s)' % CF)

    # Make sure at least one point was declared C-point
    if np.sum(splitting) == len(splitting):
        return 1

    # Generate the interpolation matrix that maps from the coarse-grid to the
    # fine-grid
    fn, kwargs = unpack_arg(interpolation)
    if fn == 'standard':
        P = standard_interpolation(A, C, splitting, **kwargs)
    elif fn == 'distance_two':
        P = distance_two_interpolation(A, C, splitting, **kwargs)
    elif fn == 'direct':
        P = direct_interpolation(A, C, splitting, **kwargs)
    else:
        raise ValueError('unknown interpolation method (%s)' % interpolation)

    # Generate the restriction matrix that maps from the fine-grid to the
    # coarse-grid
    R = P.T.tocsr()

    # Store relevant information for this level
    if keep:
        levels[-1].C = C                  # strength of connection matrix

    levels[-1].P = P                  # prolongation operator
    levels[-1].R = R                  # restriction operator
    levels[-1].splitting = splitting  # C/F splitting


    # Form next level through Galerkin product
    levels.append(multilevel_solver.level())
    A = R * A * P
    levels[-1].A = A
