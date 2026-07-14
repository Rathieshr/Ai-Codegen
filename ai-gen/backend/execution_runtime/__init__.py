"""HEI AI Execution Runtime foundation."""

from .api import build_engineering_diff_router, build_execution_runtime_router, build_memory_candidate_router, build_pr_candidate_router, build_qa_trigger_router, build_response_interpreter_router, build_runtime_observability_router, build_runtime_recovery_router, build_validation_trigger_router
from .application import (
    EngineeringDiffRepository,
    EngineeringDiffService,
    ExecutionRuntime,
    ExecutionRuntimeRepository,
    IExecutionRuntime,
    ResponseInterpretationRepository,
    ResponseInterpretationService,
)
from .comparison import EngineeringDiffEngine, RepositoryComparator
from .domain import EXECUTION_RUNTIME_VERSION, ExecutionArtifact, ExecutionResult, ExecutionSession
from .interpreter import ResponseInterpreter
from .memory import MemoryCandidateGenerator, MemoryCandidateRepository, MemoryCandidateService
from .observability import RuntimeObservabilityService, RuntimeTraceRepository
from .hardening import RuntimeHardeningHarness, build_runtime_hardening_router, render_runtime_benchmark_markdown
from .pr import PRCandidateGenerator, PRCandidateRepository, PRCandidateService
from .qa import QAExecutionPlanRepository, QATriggerEngine, QATriggerService
from .validation import ValidationTriggerEngine, ValidationTriggerRepository, ValidationTriggerService

__all__ = [
    "EXECUTION_RUNTIME_VERSION",
    "ExecutionArtifact",
    "EngineeringDiffEngine",
    "EngineeringDiffRepository",
    "EngineeringDiffService",
    "ExecutionResult",
    "ExecutionRuntime",
    "ExecutionRuntimeRepository",
    "ExecutionSession",
    "IExecutionRuntime",
    "MemoryCandidateGenerator",
    "MemoryCandidateRepository",
    "MemoryCandidateService",
    "PRCandidateGenerator",
    "PRCandidateRepository",
    "PRCandidateService",
    "RepositoryComparator",
    "QAExecutionPlanRepository",
    "QATriggerEngine",
    "QATriggerService",
    "ResponseInterpretationRepository",
    "ResponseInterpretationService",
    "ResponseInterpreter",
    "RuntimeObservabilityService",
    "RuntimeHardeningHarness",
    "RuntimeTraceRepository",
    "ValidationTriggerEngine",
    "ValidationTriggerRepository",
    "ValidationTriggerService",
    "build_engineering_diff_router",
    "build_execution_runtime_router",
    "build_memory_candidate_router",
    "build_pr_candidate_router",
    "build_qa_trigger_router",
    "build_response_interpreter_router",
    "build_runtime_observability_router",
    "build_runtime_hardening_router",
    "build_runtime_recovery_router",
    "build_validation_trigger_router",
    "render_runtime_benchmark_markdown",
]
