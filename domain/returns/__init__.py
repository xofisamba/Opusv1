"""Returns module - XIRR, XNPV, and other return metrics."""
from domain.returns.xirr import xirr, xirr_bisection, xnpv
from domain.returns.xnpv import xnpv as xnpv_func, xnpv_schedule

__all__ = ["xirr", "xirr_bisection", "xnpv", "xnpv_func", "xnpv_schedule"]
