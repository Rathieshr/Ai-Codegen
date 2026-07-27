"""Provider boundary marker.

Engineering Intelligence depends on injected fact providers. AI providers must
not be registered in this package.
"""
"""Fact-provider adapters used by Engineering Intelligence."""

from .project_intelligence import ProjectIntelligenceProvider

__all__ = ["ProjectIntelligenceProvider"]
