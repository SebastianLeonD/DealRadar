"""Leg-correlation primitives for slip EV/variance and Kelly (council OBJ-16/39/40).

Phase 1 uses a conservative same-game correlation PRIOR: two legs in the same
game share latent correlation rho0; cross-game legs are independent. The prior
matrix is block-equicorrelation, which is positive semidefinite by construction
for rho0 in [0, 1) — so its Cholesky factor always exists and the Gaussian
copula in engine/portfolio.py can sample from it directly. No numpy: Cholesky
is hand-rolled (slips are <= 6 legs, so O(n^3) is trivial).

Phase 3 replaces build_prior_corr with a Ledoit-Wolf shrinkage estimate of the
realized residual-correlation matrix plus a nearest-PSD projection; that
estimator is gated behind the calibration loop and only adopted once it clears
the gate, otherwise rho0 stands (OBJ-40). estimate_residual_corr is the stub
interface for it.
"""

from __future__ import annotations

import math

from engine.config import RHO0_SAME_GAME


def build_prior_corr(game_ids: list, rho0: float = RHO0_SAME_GAME) -> list[list[float]]:
    """Block-equicorrelation prior: corr[i][j] = rho0 when legs i != j share a
    (non-null) game, 1.0 on the diagonal, else 0.0. PSD for rho0 in [0, 1)."""
    n = len(game_ids)
    corr = [[0.0] * n for _ in range(n)]
    for i in range(n):
        corr[i][i] = 1.0
        for j in range(i + 1, n):
            same = game_ids[i] is not None and game_ids[i] == game_ids[j]
            corr[i][j] = corr[j][i] = rho0 if same else 0.0
    return corr


def cholesky(matrix: list[list[float]]) -> list[list[float]]:
    """Lower-triangular L with L @ L^T == matrix. Raises ValueError if the
    matrix is not positive definite (a tiny floor admits PSD-with-zeros)."""
    n = len(matrix)
    L = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1):
            s = sum(L[i][k] * L[j][k] for k in range(j))
            if i == j:
                d = matrix[i][i] - s
                if d < -1e-12:
                    raise ValueError("matrix is not positive semidefinite")
                L[i][j] = math.sqrt(max(d, 0.0))
            else:
                L[i][j] = 0.0 if L[j][j] == 0.0 else (matrix[i][j] - s) / L[j][j]
    return L


def correlated_normals(L: list[list[float]], standard_normals: list[float]) -> list[float]:
    """Transform i.i.d. standard normals into draws with covariance L @ L^T."""
    n = len(L)
    return [sum(L[i][k] * standard_normals[k] for k in range(i + 1)) for i in range(n)]


def estimate_residual_corr(*args, **kwargs):  # pragma: no cover - Phase 3 stub
    """Phase-3 Ledoit-Wolf shrinkage estimate of realized residual correlation,
    shrunk toward the rho0 block prior, with a nearest-PSD projection and its own
    stability/calibration gate. Until that gate is built and passes, the rho0
    prior stands (OBJ-40)."""
    raise NotImplementedError("residual-correlation estimator is Phase 3 (gated)")
