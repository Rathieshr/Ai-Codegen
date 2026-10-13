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
    EngineeringEntryMode,
    EngineeringMemorySummary,
    EngineeringSummary,
    ImpactSummary,
    RepositoryRecommendation,
    RepositorySummary,
    ReuseSummary,
    SimilaritySummary,
)
from .api import build_engineering_intelligence_router
from .shared_orchestrator import HEIIntelligenceOrchestrator
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
    "EngineeringEntryMode",
    "EngineeringDiscoveryService",
    "EngineeringIntelligenceService",
    "HEIIntelligenceOrchestrator",
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
    "build_engineering_intelligence_router",
]
