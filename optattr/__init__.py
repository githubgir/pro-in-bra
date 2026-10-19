"""Optimization attribution: target / constraint pressure decomposition with
structural covariance propagation (Specification v3)."""

from .attribution import Attribution, attribute
from .counterfactual import DEFAULT_LADDER, covariance_ladder, factor_shapley
from .covariance import CovModel
from .problem import Optimizer, PortfolioSpec, Solution, prior_holdings
from .universe import Universe, synthetic_universe

__all__ = [
    "Attribution", "attribute", "DEFAULT_LADDER", "covariance_ladder", "factor_shapley",
    "CovModel", "Optimizer", "PortfolioSpec", "Solution", "prior_holdings",
    "Universe", "synthetic_universe",
]
