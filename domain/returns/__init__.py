"""Returns module - XIRR, XNPV, and other return metrics."""
from domain.returns.xirr import xirr, xirr_bisection, robust_xirr
from domain.returns.xnpv import xnpv, xnpv_schedule

__all__ = ["xirr", "xirr_bisection", "robust_xirr", "xnpv", "xnpv_schedule"]
