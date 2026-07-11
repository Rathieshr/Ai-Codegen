"""Platform jobs foundation."""

from .service import IJobHandler, IJobQueue, IJobRunner, InMemoryJobQueue, JobHandlerRegistry, JobRunner
from .types import is_terminal, normalize_platform_job

__all__ = [
    "IJobHandler",
    "IJobQueue",
    "IJobRunner",
    "InMemoryJobQueue",
    "JobHandlerRegistry",
    "JobRunner",
    "is_terminal",
    "normalize_platform_job",
]
