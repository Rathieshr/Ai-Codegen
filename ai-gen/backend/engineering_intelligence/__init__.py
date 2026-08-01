"""Reusable Engineering Intelligence orchestration layer."""

from .builder import EngineeringContextBuilder
from .models import (
    ArchitectureSummary,
    AzureDevOpsSummary,
    DependencySummary,
    DiscoveryEvidence,
    EngineeringAnalysisResult,
    EngineeringContext,
    EngineeringDiscoveryReport,
    EngineeringMemorySummary,
    EngineeringSummary,
    ImpactSummary,
    RepositoryRecommendation,
    RepositorySummary,
    ReuseSummary,
    SimilaritySummary,
)
from .service import EngineeringIntelligenceService
from .providers import ProjectIntelligenceProvider
from .services import (
    ArchitectureService,
    AzureDevOpsService,
    ContextBuilder,
    DependencyService,
    EngineeringDiscoveryService,
    IntelligenceOrchestrator,
    MarkdownService,
    MemoryService,
    RepositoryService,
    SimilarityService,
)

__all__ = [
    "ArchitectureSummary",
    "ArchitectureService",
    "AzureDevOpsSummary",
    "AzureDevOpsService",
    "ContextBuilder",
    "DependencySummary",
    "DependencyService",
    "DiscoveryEvidence",
    "EngineeringAnalysisResult",
    "EngineeringContext",
    "EngineeringContextBuilder",
    "EngineeringDiscoveryReport",
    "EngineeringDiscoveryService",
    "EngineeringIntelligenceService",
    "EngineeringMemorySummary",
    "EngineeringSummary",
    "ImpactSummary",
    "IntelligenceOrchestrator",
    "MarkdownService",
    "MemoryService",
    "RepositoryRecommendation",
    "ProjectIntelligenceProvider",
    "RepositorySummary",
    "RepositoryService",
    "ReuseSummary",
    "SimilaritySummary",
    "SimilarityService",
]
