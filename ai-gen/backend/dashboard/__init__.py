"""HEI operational dashboard module."""

from .api import build_dashboard_router
from .service import DashboardService

__all__ = ["DashboardService", "build_dashboard_router"]
