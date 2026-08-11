import React, { ChangeEvent, FormEvent, useEffect, useState } from 'react';
import { HEIHostContext } from './host';

type SourceType = 'PasteRequirement' | 'UploadDocument' | 'AzureDevOpsWorkItem' | 'MeetingTranscript';

const SOURCES: Array<{ id: SourceType; label: string; description: string }> = [
  { id: 'PasteRequirement', label: 'Paste Requirement', description: 'Enter a business need or engineering outcome.' },
  { id: 'UploadDocument', label: 'Upload Document', description: 'Use a text, Markdown, BRD, or PRD document.' },
  { id: 'AzureDevOpsWorkItem', label: 'Azure DevOps Work Item', description: 'Use a synchronized Epic, Feature, Story, Task, or Bug.' },
  { id: 'MeetingTranscript', label: 'Meeting Transcript', description: 'Turn recorded decisions and needs into planning context.' },
];

const FUTURE_SOURCES = ['Confluence', 'SharePoint', 'Notion', 'Email', 'REST API'];

type ProposalNode = {
  nodeId: string; parentId: string; type: string; title: string; description: string; businessValue: string;
  acceptanceCriteria: string[]; businessRules: string[]; dependencies: string[]; storyPoints: number;
  repositoryModules: string[]; affectedApis: string[]; affectedScreens: string[]; technicalNotes: string[];
  generatedTests: string[]; risk: string; priority: string; origin: string; confidence: number; reason: string;
  taskType: string; storyType: string; owner: string; order: number; status: string; planningVersion: number;
  acceptanceCriteriaDetails: Array<{ criterionId: string; text: string; origin: string; status: string; confidence: number }>;
  affectedServices: string[]; affectedDatabaseObjects: string[]; externalIntegrations: string[];
  evidence: Array<{ type?: string; value?: string; source?: string }>; definitionOfDone: string[];
  repositoryMapping: {
    repositoryId?: string; repositoryName?: string; snapshotVersion?: string; mode?: string;
    modules?: string[]; services?: string[]; apis?: string[]; screens?: string[];
    databaseObjects?: string[]; externalIntegrations?: string[]; reason?: string; evidenceStatus?: string;
  };
  traceability: {
    requirementId: string; businessGoals: string[]; functionalRequirements: string[]; acceptanceCriteria: string[];
    recommendationId: string; repositoryModules: string[]; memoryReferences: string[];
    acceptanceCriterionIds?: string[]; knowledgeReferences?: string[]; contextVersion?: string;
  };
};
type PlanningProposalResult = {
  proposalId: string; planningPackId: string; requirementId: string; contextId: string; contextVersion: string;
  recommendationId: string; recommendationVersion: number;
  projectId: string; correlationId: string; title: string; executiveSummary: string; businessGoal: string;
  recommendedStrategy: { type: string; title: string; summary: string; reason: string; confidence: number };
  status: string; version: number; nodes: ProposalNode[];
  estimate: {
    aiEngineeringDays: number; aiStoryPoints: number; engineeringDays: number; storyPoints: number;
    sprintCount: number; developersRequired: number; complexity: string; risk: string; confidence: number; overrideReason: string;
  };
  implementationOrder: string[];
  dependencies: Array<{ from: string; to: string; type?: string }>;
  dependencyGraph: { categories: Record<string, Array<Record<string, unknown>>> };
  acceptanceCriteria: Array<{ criterionId: string; title: string; text: string; origin: string; status: string; confidence: number; mappedNodeIds: string[] }>;
  engineeringNotes: string[]; risks: Array<{ riskId: string; description: string; level: string; mitigation: string }>;
  definitionOfDone: string[]; knowledgeVersion: string; knowledgeReferences: string[];
  azureDevOpsPreview: {
    previewId: string; projectId: string; areaPath: string; iterationPath: string; tags: string[];
    workItems: Array<{ proposalNodeId: string; workItemType: string; title: string; parentProposalNodeId: string; storyPoints?: number; operation: string }>;
    links: Array<{ type: string; parentProposalNodeId: string; childProposalNodeId: string }>;
    writeStatus: string; writesPerformed: number;
  };
  aiReview: { status?: string; summary?: string; recommendations?: string[]; confidence?: number; provider?: string; reasoningMode?: string };
  validation: { status: string; mandatoryPassed: boolean; findings: Array<{ code: string; severity: string; message: string; nodeId?: string }> };
  health: {
    overallHealth: number; coverage: number; estimateCompleteness: number; repositoryCoverage: number;
    requirementCoverage: number; engineeringConfidence: number; planningConfidence: number; risk: string;
  };
  diff: {
    summary: Record<string, number>;
    changes: Array<{ action: string; artifactType?: string; type?: string; title: string; reason: string; confidence: number }>;
    estimatedSprintImpact: string;
  };
  review: { status: string; checklist: Array<{ name?: string; label?: string; passed: boolean; mandatory: boolean }>; reviewer: string; comments: string };
  history: Array<{ version: number; author: string; reason: string; timestamp: string; changes: string[] }>;
  createdAt: string; updatedAt: string; approvedBy: string; approvedAt: string;
};
type EngineeringReviewResult = {
  reviewId: string; proposalId: string; proposalVersion: number; contextVersion: string;
  knowledgeVersion: string; recommendationVersion: number; status: string; owner: string;
  currentStageId: string; stale: boolean; createdAt: string; updatedAt: string;
  currentStage: { stageId?: string; name?: string; role?: string; assignedReviewer?: string; status?: string };
  stages: Array<{ stageId: string; name: string; role: string; status: string; assignedReviewer: string; approvedBy: string; approvedAt: string }>;
  sections: Array<{ name: string; status: string; commentCount: number; approvedBy: string }>;
  comments: Array<{ commentId: string; section: string; targetType: string; targetId: string; comment: string; author: string; status: string; createdAt: string }>;
  changeRequests: Array<{ changeRequestId: string; type: string; description: string; targetId: string; requestedBy: string; status: string; createdAt: string }>;
  decisions: Array<{ decisionId: string; stage: string; reviewer: string; decision: string; comments: string; timestamp: string; proposalVersion: number }>;
  readiness: { status: string; approvalAllowed: boolean; blockers: string[]; warnings: string[]; checks: Record<string, boolean> };
  proposalSummary: {
    title: string; executiveSummary: string; proposalVersion: number; contextVersion: string;
    knowledgeVersion: string; recommendationVersion: number; approvalStatus: string; riskScore: string;
    readiness: number; validationStatus: string; estimatedEffort: number; storyPoints: number;
    affectedRepositories: string[]; affectedTeams: string[];
  };
  synchronization: { authorized: boolean; status: string; reasons: string[] };
};

type AnalysisFinding = { text: string; reason: string; evidence?: string; confidence: number };
type ArtifactOrigin = 'Source' | 'Source Derived' | 'Project Intelligence Generated' | 'AI Enhanced' | 'Deterministic Fallback' | 'AI Suggested' | 'AI Inferred' | 'User Edited' | 'User Added' | 'Imported';
type AcceptanceEvidence = {
  requirementSentence: string;
  matchedPhrase: string;
  confidence: number;
  source: string;
};
type AcceptanceCriterionSuggestion = {
  criterionId: string;
  title?: string;
  text: string;
  origin: ArtifactOrigin;
  status: 'PendingReview' | 'Approved';
  type?: string;
  confidence?: number;
  mappedFunctionalRequirement?: string;
  requirementCoverage?: 'Mapped' | 'Unmapped';
  evidence?: AcceptanceEvidence[];
  quality?: { atomic: boolean; independent: boolean; verifiable: boolean; implementationIndependent: boolean; traceable: boolean };
  order: number;
};
type MissingInformation = { field: string; status: string; reason: string; blocksGeneration: boolean };
type AIAssumption = { assumptionId: string; text: string; reason: string; confidence: number; status: string; origin: ArtifactOrigin };
type AcceptanceCoverage = {
  functionalRequirementCount: number;
  coveredFunctionalRequirementCount: number;
  coveragePercent: number;
  status: string;
  mappings: Array<{ functionalRequirementId: string; functionalRequirement: string; criterionIds: string[]; status: string }>;
  uncoveredFunctionalRequirements: string[];
  areas?: Array<{ area: string; count: number; coveredCount: number; status: string }>;
  uncoveredAreas?: string[];
};
type RepositoryCandidate = {
  repositoryId: string; name: string; url: string; defaultBranch: string; repositoryType: string;
  confidence: number; reason: string; evidence: string[]; matchedModules: string[];
  matchedTechnologies: string[]; snapshotVersion: string; manualOverride?: boolean;
};
type RepositorySuggestion = {
  detectionId: string; requirementId: string; suggestedRepository?: RepositoryCandidate;
  confidence: number; reason: string; alternativeRepositories: RepositoryCandidate[];
  availableRepositories: RepositoryCandidate[]; source: 'Detection' | 'ManualOverride'; detectedAt: string;
};
type AnalysisSectionSource = {
  origin: string;
  evidenceReferences: string[];
  provider?: string;
  reasoningMode?: string;
};
type GovernedStatement = {
  id: string;
  category: string;
  text: string;
  classification: 'SOURCE' | 'EVIDENCE' | 'AI_INFERRED' | 'AI_SUGGESTION' | 'UNKNOWN';
  source: string;
  provider?: string;
  model?: string;
  promptVersion?: string;
  confidence: number;
  evidenceReferences: string[];
  generatedAt: string;
  approvedStatus: string;
  why: string;
  requiresConfirmation?: boolean;
};
type RequirementAnalysisDocument = {
  schemaVersion: 'hei-requirement-analysis-v2';
  documentId: string;
  requirementId: string;
  contextVersion: string;
  title: string;
  executiveSummary: string;
  businessGoal: string;
  problemStatement: string;
  primaryActor: string;
  secondaryActors: string[];
  businessValue: string;
  capabilities: string[];
  functionalRequirements: string[];
  candidateNonFunctionalRequirements: string[];
  acceptanceCriteria: string[];
  businessRules: string[];
  constraints: string[];
  dependencies: string[];
  affectedModules: string[];
  affectedServices: string[];
  affectedApis: string[];
  affectedScreens: string[];
  repositoryFindings: DiscoveryEvidence[];
  markdownFindings: DiscoveryEvidence[];
  azureDevOpsFindings: DiscoveryEvidence[];
  reusableComponents: DiscoveryEvidence[];
  risks: string[];
  assumptions: string[];
  openQuestions: string[];
  engineeringInsights: string[];
  statementGovernance: GovernedStatement[];
  suggestedEnhancements: GovernedStatement[];
  planningReadiness: {
    status: 'Ready' | 'ReadyWithRecommendations' | 'NeedsUserInput' | 'Blocked';
    readyForPlanning: boolean;
    score: number;
    blockers: string[];
    warnings: string[];
    strengths?: string[];
    needsAttention?: string[];
    explanation: string;
    dimensions: Record<string, number>;
    evidenceStatus: string;
  };
  confidence: { score: number; level: string; reason: string };
  evidence: DiscoveryEvidence[];
  sectionSources: Record<string, AnalysisSectionSource>;
  validation: { valid: boolean; checks: Record<string, boolean>; warnings: string[] };
  generatedAt: string;
};
type RequirementAnalysisResult = {
  analysisId: string;
  requirementId: string;
  contextVersion: string;
  contentHash: string;
  requirementSummary: string;
  planningRequirement: string;
  reviewStatus: 'Pending' | 'Approved' | 'Cancelled';
  reviewContext: {
    source: string;
    repository: { id: string; name: string; status: string };
    documentType: string;
    engineeringMemory: { status: string; message: string };
    repositoryReuse: { status: string; message: string };
  };
  planningReadiness: { status: 'Ready' | 'ReadyWithRecommendations' | 'NeedsUserInput' | 'Blocked'; readyForPlanning: boolean; score: number; blockers: string[]; warnings: string[] };
  requirementQualityScore: number;
  confidence: number;
  businessGoals: string[];
  functionalRequirements: string[];
  nonFunctionalRequirements: string[];
  acceptanceCriteria: string[];
  actors: string[];
  businessRules: string[];
  constraints: string[];
  dependencies: string[];
  risks: string[];
  openQuestions: string[];
  assumptions: string[];
  acceptanceCriteriaState: {
    state: 'SourceProvided' | 'AISuggested' | 'Missing';
    origin: ArtifactOrigin | '';
    status: 'Approved' | 'PendingReview' | 'Missing' | 'NeedsUserInput' | 'Skipped' | 'Discarded';
    description: string;
  };
  acceptanceCriteriaSuggestions: AcceptanceCriterionSuggestion[];
  acceptanceCriteriaRecords?: AcceptanceCriterionSuggestion[];
  missingInformation?: MissingInformation[];
  aiAssumptions?: AIAssumption[];
  acceptanceCoverage?: AcceptanceCoverage;
  acceptanceEvidence?: AcceptanceEvidence[];
  fieldOrigins: Record<string, ArtifactOrigin>;
  missingAcceptanceCriteria: AnalysisFinding[];
  ambiguousRequirements: AnalysisFinding[];
  conflictingRequirements: AnalysisFinding[];
  duplicateRequirements: AnalysisFinding[];
  repositorySuggestion?: RepositorySuggestion;
  aiAnalysis?: {
    status: string; reasoningMode: string; provider: string; model: string; promptVersion: string;
    insights: string[]; warnings: string[]; confidence: { overall?: number; level?: string };
  };
  aiUnderstanding?: {
    status: string; reasoningMode: string; provider: string; model: string; promptVersion: string;
    insights: string[]; warnings: string[]; confidence: { overall?: number; level?: string };
  };
  requirementIntent?: {
    intentSummary: string; businessGoal: string; functionalIntent: string[];
    entities: string[]; primaryActor: string; secondaryActors: string[];
    capabilities: string[]; actions: string[]; concepts: string[];
    businessTerminology: string[]; explicitConstraints: string[]; possibleAssumptions: string[];
    ambiguities: string[]; riskIndicators: string[]; technologyConcepts: string[];
    domainSynonyms: string[]; searchKeywords: string[];
    possibleModuleNames: string[]; possibleFeatureNames: string[]; possibleApis: string[];
    possibleRepositoryTerms: string[]; possibleAzureDevOpsSearchTerms: string[];
    possibleMarkdownSearchTerms: string[]; clarificationCandidates: string[]; confidence: number;
  };
  evidenceSynthesis?: {
    repositoryFindings: string[]; architectureFindings: string[]; reuseOpportunities: string[];
    affectedEngineeringElements: string[]; missingInformation: string[];
    engineeringInsights: string[]; evidence: Array<{ referenceId: string; reason?: string }>;
  };
  engineeringDiscovery?: {
    contextId: string; contextVersion: string;
    repository: { mode?: string; snapshotVersion?: string; modules: string[]; files: unknown[]; services: string[]; apis: string[] };
    markdown: { selected?: Array<{ evidenceId: string; path: string; heading: string }>; diagnostics?: Record<string, unknown> };
    azureDevOps: { workItems: unknown[]; currentIteration: Record<string, unknown> };
    knowledge: Record<string, unknown>; memory: { matches: unknown[] };
    similarWork: Record<string, unknown>; architecture: Record<string, unknown>;
    dependencies: Record<string, unknown>; rejectedContext: unknown[];
    report?: {
      schemaVersion: string; contextId: string; contextVersion: string;
      status: 'Ready' | 'Partial' | 'DiscoveryPending' | 'NoRelevantEvidence';
      summary: string;
      whatIFound: Array<{ source: string; status: string; count: number; summary: string; evidenceReferences: string[]; findings?: Array<{ title: string; type: string; sourceReference: string; reason: string; confidence: number }> }>;
      reusableComponents: DiscoveryEvidence[]; similarFeatures: DiscoveryEvidence[];
      relevantDocumentation: DiscoveryEvidence[]; architectureEvidence: DiscoveryEvidence[];
      repositoryEvidence: DiscoveryEvidence[]; azureDevOpsEvidence: DiscoveryEvidence[];
      engineeringMemoryEvidence: DiscoveryEvidence[]; projectIntelligenceEvidence: DiscoveryEvidence[];
      knowledgeEvidence: DiscoveryEvidence[];
      conflicts: Array<{ reason?: string; path?: string; heading?: string }>;
      unknowns: Array<{ area: string; reason: string; classification: string }>;
      sourceStatus: Array<{ source: string; status: string; message: string }>;
      confidence: { score: number; level: string; evidenceCoverage: number; evidenceCount: number; conflictCount: number; reason: string };
    };
  };
  analysisLineage?: {
    provider: string; model: string; intentPromptVersion: string; synthesisPromptVersion: string;
    contextId: string; contextVersion: string; knowledgeVersion?: string;
    repositoryRevision?: string; analysisVersion: string; timestamp: string;
  };
  requirementRefinement?: RequirementRefinementResult;
  analysisMode?: 'AI' | 'Deterministic';
  acceptanceDiagnostics?: {
    generationMode?: string; reasoningMode?: string; provider?: string; model?: string;
    promptVersion?: string; warnings?: string[]; generationStatus?: string;
  };
  analysisDocument?: RequirementAnalysisDocument;
};

type DiscoveryEvidence = {
  evidenceId: string;
  evidenceType: string;
  title: string;
  source: string;
  sourceReference: string;
  reason: string;
  confidence: number;
  metadata: Record<string, unknown>;
};

type IngestionResult = {
  requirementId: string;
  sourceType: SourceType;
  status: string;
  title: string;
  planningReady: boolean;
  contextVersion: string;
  contentHash: string;
  correlationId: string;
};

type RequirementRefinementResult = {
  refinementId: string;
  requirementId: string;
  originalRequirement: string;
  refinedRequirement: string;
  executiveSummary?: string;
  requirementSummary: string;
  businessGoal?: string;
  businessObjective: string;
  problemStatement: string;
  userIntent: string;
  primaryActor: string;
  secondaryActors: string[];
  coreCapability: string;
  coreCapabilities?: string[];
  expectedOutcome: string;
  businessEntities?: string[];
  engineeringConcepts?: string[];
  domainTerminology?: string[];
  repositorySearchHints?: string[];
  markdownSearchHints?: string[];
  azureDevOpsSearchHints?: string[];
  possibleModuleNames?: string[];
  possibleFeatureNames?: string[];
  potentialDomainTerms: string[];
  potentialSearchKeywords: string[];
  potentialRepositoryTerms: string[];
  potentialAzureDevOpsTerms: string[];
  potentialMarkdownTerms: string[];
  changes: Array<{ change: string; reason: string }>;
  reasoning: string[];
  ambiguities: string[];
  clarificationCandidates: string[];
  clarificationResponses?: Array<{ question: string; answer: string }>;
  confidence: number;
  status: 'PendingReview' | 'Accepted' | 'Skipped';
  provider: string;
  model: string;
  promptVersion: string;
  version: number;
  generatedAt: string;
  warnings: string[];
  fallbackReason?: string;
  providerAttempts?: string[];
};

type DocumentResult = {
  documentId: string;
  fileName: string;
  mediaType: string;
  status: string;
  sizeBytes: number;
  readyForAnalysis: boolean;
  parsed?: { title?: string; detectedType?: string; pages?: number; language?: string };
};

type TranscriptFinding = { findingId: string; text: string; speaker?: string; timestamp?: string; confidence: number; evidence: string };
type TranscriptResult = {
  transcriptId: string;
  sourceType: string;
  status: string;
  requirementContextId: string;
  readyForPlanning: boolean;
  analysis: {
    meetingTitle: string;
    participants: string[];
    date: string;
    meetingSummary: string;
    requirements: TranscriptFinding[];
    actionItems: TranscriptFinding[];
    decisions: TranscriptFinding[];
    risks: TranscriptFinding[];
    openQuestions: TranscriptFinding[];
    dependencies: TranscriptFinding[];
    warnings: string[];
  };
};

type AdoWorkItemImportResult = {
  workItemId: string;
  workItemRevision: number;
  status: string;
  requirementContextId: string;
  currentWorkItem: {
    workItemType: string;
    title: string;
    description: string;
    state: string;
    area: string;
    iteration: string;
    tags: string[];
    comments: Array<{ commentId: string; text: string; createdBy: string }>;
    attachments: Array<{ name: string; url: string }>;
    linkedWorkItems: Array<{ workItemId: string; relationship: string; isDependency: boolean }>;
  };
  requirementSummary: {
    title: string;
    summary: string;
    acceptanceCriteria: string[];
    dependencies: Array<{ workItemId: string; relationship: string }>;
    missingInformation: string[];
    readyForPlanning: boolean;
  };
};

type PlanningContextResult = {
  contextId: string;
  contextVersion: string;
  requirementId: string;
  status: string;
  reviewStatus: string;
  azureDevOps: {
    counts: Record<string, number>;
    currentSprint?: { name?: string; path?: string };
    workItems: Array<{ id: string; type: string; title: string; state: string }>;
  };
  repository: {
    repositoryId: string; repositoryName: string; mode: string; branch: string; snapshotVersion: string;
    confidence: number; affectedModules: string[]; affectedServices: string[]; affectedApis: string[];
    affectedScreens: string[]; reusableComponents: string[]; reusableTests: string[]; reusePercent: number;
    reason: string; warnings: string[];
  };
  memory: {
    matches: Array<{ id: string; title: string; category: string; confidence: number }>;
    previousStories: Array<{ id: string; title: string }>;
    previousPullRequests: Array<{ id: string; title: string }>;
    previousBugs: Array<{ id: string; title: string }>;
    architectureDecisions: Array<{ id: string; title: string }>;
    reusableComponents: string[]; reusableTests: string[]; lessonsLearned: string[]; coverage: number;
  };
  similarWork: Array<{
    workItemId: string; workItemType: string; title: string; similarity: number; confidence: number;
    reason: string; suggestedAction: string; state: string;
  }>;
  classification: { value: string; confidence: number; reason: string; source: string };
  impact: {
    affectedFeatures: string[]; affectedStories: string[]; affectedApis: string[]; affectedModules: string[];
    potentialRisks: string[]; potentialBreakingChanges: string[]; sprintImpact: string;
    engineeringEffort: string; complexity: string;
  };
  recommendation: {
    planningMode: string; confidence: number; strategy: string; create: string[]; reuse: string[];
    modify: string[]; doNotCreate: string[]; reasons: string[];
  };
  readiness: {
    status: 'Ready' | 'ReadyWithRecommendations' | 'NeedsUserDecision' | 'Blocked';
    score: number; repositoryCoverage: number; memoryCoverage: number; requirementCompleteness: number;
    existingWorkMatch: number; blockers: string[]; warnings: string[];
  };
  summary: {
    currentProject: string; repository: string; planningMode: string; recommendedStrategy: string;
    affectedFeatures: number; affectedStories: number; engineeringRisk: string;
    estimatedComplexity: string; planningConfidence: number;
  };
  engineeringDiscovery?: {
    repositoryMarkdown?: {
      selected?: Array<{
        evidenceId: string; path: string; heading: string; classification: string;
        selectionReason: string; authority: string; confidence: number;
      }>;
      rejected?: Array<{ evidenceId?: string; path?: string; heading?: string; reason: string }>;
      conflicts?: Array<{ conflictId: string; path: string; heading: string; reason: string }>;
      diagnostics?: {
        filesScanned?: number; sectionsIndexed?: number; sectionsSelected?: number;
        rejectedContextCount?: number; conflictsDetected?: number; repositoryRevision?: string;
      };
    };
    projectIntelligence?: { knowledge?: { version?: string } };
  };
};

type PlanningRecommendationResult = {
  recommendationId: string;
  contextId: string;
  contextVersion: string;
  requirementId: string;
  strategy: string;
  title: string;
  status: 'PendingReview' | 'Approved';
  version: number;
  confidence: { engineering: number; repository: number; memory: number; planning: number; overall: number };
  reasons: Array<{ title: string; explanation: string; evidence: string[]; confidence: number }>;
  rejectedAlternatives: Array<{ title: string; explanation: string; evidence: string[]; confidence: number }>;
  alternatives: Array<{
    strategy: string; confidence: number; title: string; pros: string[]; cons: string[];
    rejectedReason: string; description?: string; estimatedEffort?: string; risks?: string[]; reuseScore?: number;
  }>;
  actions: Array<{ action: string; confidence: number; reason: string }>;
  similarWork: PlanningContextResult['similarWork'];
  relatedPullRequests: Array<{ pullRequestId?: string; id?: string; title?: string; status?: string }>;
  currentDevelopment: Array<{ workItemId?: string; id?: string; title?: string; state?: string }>;
  repositoryComponents: string[];
  dependencies: string[];
  architectureDecisions: Array<{ id?: string; title?: string }>;
  impact: {
    repositoryId: string; repositoryName: string; businessImpact: string; engineeringImpact: string;
    repositoryImpact: string; sprintImpact: string; estimatedComplexity: string;
    affectedModules: string[]; affectedStories: string[]; affectedFeatures: string[]; affectedApis: string[];
    affectedServices: string[]; affectedScreens: string[]; affectedDatabaseObjects: string[];
    affectedTests: string[]; affectedDocumentation: string[]; affectedPipelines: string[];
    riskLevel: string; storyPointEstimate: string; engineeringDays: string;
  };
  diff: {
    diffId: string;
    summary: Record<string, number>;
    operations: Array<{ operationId: string; action: string; artifactType: string; title: string; reason: string; confidence: number }>;
  };
  summary: {
    recommendedStrategy: string; engineeringConfidence: number; repositoryConfidence: number;
    memoryConfidence: number; planningConfidence: number; expectedSprint: string;
    expectedStoryCount: number; expectedTaskCount: number; expectedModificationCount: number;
  };
  risks: string[];
  engineeringReasoning: string[];
  expectedRepositoryImpact: string;
  expectedAzureDevOpsImpact: string;
  generatedAt: string;
  approvedAt: string;
  approvedBy: string;
  overrideReason: string;
  reasoningVersion?: string;
  promptVersion?: string;
  reasoningMode?: string;
  primaryRecommendation?: {
    description?: string; estimatedEffort?: string; reuseScore?: number; pros?: string[];
    cons?: string[]; risks?: string[];
  };
  repositoryAnalysis?: Record<string, Array<{
    name: string; type: string; reason: string; impact: string; confidence: number; source: string; evidence: string[];
  }>>;
  reuseSuggestions?: Array<{ type: string; name: string; reason: string; confidence: number; source: string; evidence: string[] }>;
  dependencyAnalysis?: Record<string, Array<{ name: string; reason: string; confidence: number; source: string }>>;
  engineeringImpact?: Record<string, string | number>;
  readiness?: {
    requirementCompleteness: number; acceptanceCriteriaCoverage: number; dependencyResolution: number;
    businessClarity: number; architectureConfidence: number; overallReadiness: number; status: string; reasons: string[];
  };
  missingInformation?: Record<string, string[]>;
  explanation?: {
    whyThisApproach?: string; whyNotAlternatives?: string[]; tradeOffs?: string[];
    evidenceUsed?: string[]; potentialFutureImpact?: string;
  };
};

export function NewRequirementWorkspace({ baseUrl, context, onOpenApprovals, onError }: {
  baseUrl: string;
  context: HEIHostContext;
  onOpenApprovals: () => void;
  onError: (message: string) => void;
}) {
  const [sourceType, setSourceType] = useState<SourceType>('PasteRequirement');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [workItemId, setWorkItemId] = useState(context.route.workItemId || '');
  const [documentName, setDocumentName] = useState('');
  const [documentMediaType, setDocumentMediaType] = useState('text/plain');
  const [documentContentBase64, setDocumentContentBase64] = useState('');
  const [documentResult, setDocumentResult] = useState<DocumentResult>();
  const [transcriptFormat, setTranscriptFormat] = useState<'TeamsTranscript' | 'ZoomTranscript' | 'TextTranscript'>('TeamsTranscript');
  const [transcriptResult, setTranscriptResult] = useState<TranscriptResult>();
  const [adoImportResult, setAdoImportResult] = useState<AdoWorkItemImportResult>();
  const [busyStage, setBusyStage] = useState<'uploading' | 'parsing' | 'refining' | 'analyzing' | 'ingesting' | 'context' | 'planning' | ''>('');
  const [ingestion, setIngestion] = useState<IngestionResult>();
  const [requirementRefinement, setRequirementRefinement] = useState<RequirementRefinementResult>();
  const [requirementAnalysis, setRequirementAnalysis] = useState<RequirementAnalysisResult>();
  const [editingReview, setEditingReview] = useState(false);
  const [reviewTitle, setReviewTitle] = useState('');
  const [reviewContent, setReviewContent] = useState('');
  const [result, setResult] = useState<PlanningProposalResult>();
  const [engineeringReview, setEngineeringReview] = useState<EngineeringReviewResult>();
  const [planningContext, setPlanningContext] = useState<PlanningContextResult>();
  const [planningRecommendation, setPlanningRecommendation] = useState<PlanningRecommendationResult>();

  async function readDocument(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > 25 * 1024 * 1024) {
      onError('Requirement documents must be 25 MB or smaller.');
      return;
    }
    try {
      setDocumentName(file.name);
      setDocumentMediaType(file.type || 'text/plain');
      setDocumentContentBase64(await fileToBase64(file));
      if (!title.trim()) setTitle(file.name.replace(/\.[^.]+$/, '').replace(/[-_]+/g, ' '));
    } catch {
      onError('The selected document could not be read as text.');
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusyStage('ingesting');
    try {
      let documentId = '';
      if (sourceType === 'UploadDocument') {
        setBusyStage('uploading');
        const uploadResponse = await fetch(`${baseUrl}/documents/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
          body: JSON.stringify({ fileName: documentName, mediaType: documentMediaType, contentBase64: documentContentBase64, projectId: context.project.id || context.project.name, actor: context.user.name }),
        });
        const uploaded = await uploadResponse.json() as DocumentResult & { error?: { message?: string } };
        if (!uploadResponse.ok) throw new Error(uploaded.error?.message || `Document Upload returned HTTP ${uploadResponse.status}.`);
        setBusyStage('parsing');
        const parseResponse = await fetch(`${baseUrl}/documents/${encodeURIComponent(uploaded.documentId)}/parse`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id }, body: '{}' });
        const parsed = await parseResponse.json() as DocumentResult & { error?: { message?: string } };
        if (!parseResponse.ok) throw new Error(parsed.error?.message || `Document Parsing returned HTTP ${parseResponse.status}.`);
        setDocumentResult(parsed);
        documentId = parsed.documentId;
      }
      let ingested: IngestionResult & { error?: { message?: string } };
      if (sourceType === 'AzureDevOpsWorkItem') {
        setBusyStage('analyzing');
        const projectId = context.project.id || context.project.name;
        const currentResponse = await fetch(`${baseUrl}/ado/workitem/${encodeURIComponent(workItemId)}?projectId=${encodeURIComponent(projectId)}`, {
          headers: { 'X-HEI-User': context.user.id, 'X-Correlation-ID': context.correlationId },
        });
        const current = await currentResponse.json() as AdoWorkItemImportResult['currentWorkItem'] & { error?: { message?: string } };
        if (!currentResponse.ok) throw new Error(current.error?.message || `Azure DevOps Work Item Import returned HTTP ${currentResponse.status}.`);
        const analysisResponse = await fetch(`${baseUrl}/ado/workitem/${encodeURIComponent(workItemId)}/analyze`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id, 'X-Correlation-ID': context.correlationId },
          body: JSON.stringify({ projectId, repositoryId: context.repository.id, repositoryName: context.repository.name, branch: context.repository.branch, actor: context.user.name }),
        });
        const analyzed = await analysisResponse.json() as AdoWorkItemImportResult & { error?: { message?: string } };
        if (!analysisResponse.ok) throw new Error(analyzed.error?.message || `Azure DevOps Work Item Analysis returned HTTP ${analysisResponse.status}.`);
        setAdoImportResult(analyzed);
        if (!analyzed.requirementSummary.readyForPlanning || !analyzed.requirementContextId) {
          throw new Error(analyzed.requirementSummary.missingInformation[0] || 'The work item requires more information before Planning.');
        }
        ingested = {
          requirementId: analyzed.requirementContextId,
          sourceType: 'AzureDevOpsWorkItem',
          status: analyzed.status,
          title: analyzed.requirementSummary.title,
          planningReady: true,
          contextVersion: '1.0',
          contentHash: '',
          correlationId: context.correlationId,
        };
      } else if (sourceType === 'MeetingTranscript') {
        setBusyStage('uploading');
        const fileFormat = documentName.toLowerCase().endsWith('.docx') ? 'DOCX' : documentName.toLowerCase().endsWith('.txt') ? 'TXT' : transcriptFormat;
        const uploadResponse = await fetch(`${baseUrl}/transcripts/upload`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
          body: JSON.stringify({
            sourceType: fileFormat,
            title,
            transcript: content,
            fileName: documentName,
            mediaType: documentMediaType,
            contentBase64: documentContentBase64,
            organization: context.organization.name,
            projectId: context.project.id || context.project.name,
            projectName: context.project.name,
            teamId: context.team.id,
            repositoryId: context.repository.id,
            repositoryName: context.repository.name,
            branch: context.repository.branch,
            actor: context.user.name,
            correlationId: context.correlationId,
          }),
        });
        const uploaded = await uploadResponse.json() as TranscriptResult & { error?: { message?: string } };
        if (!uploadResponse.ok) throw new Error(uploaded.error?.message || `Transcript Upload returned HTTP ${uploadResponse.status}.`);
        setBusyStage('analyzing');
        const analysisResponse = await fetch(`${baseUrl}/transcripts/analyze`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
          body: JSON.stringify({ transcriptId: uploaded.transcriptId }),
        });
        const analyzed = await analysisResponse.json() as TranscriptResult & { error?: { message?: string } };
        if (!analysisResponse.ok) throw new Error(analyzed.error?.message || `Transcript Analysis returned HTTP ${analysisResponse.status}.`);
        setTranscriptResult(analyzed);
        if (!analyzed.readyForPlanning || !analyzed.requirementContextId) {
          throw new Error(analyzed.analysis?.warnings?.[0] || 'No explicit engineering requirements were found. Review the transcript before Planning.');
        }
        ingested = {
          requirementId: analyzed.requirementContextId,
          sourceType: 'MeetingTranscript',
          status: analyzed.status,
          title: analyzed.analysis.meetingTitle,
          planningReady: analyzed.readyForPlanning,
          contextVersion: '1.0',
          contentHash: '',
          correlationId: context.correlationId,
        };
      } else {
        setBusyStage('ingesting');
      const sourcePayload = sourceType === 'UploadDocument' ? { title, documentId } : { title, content };
      const common = {
        sourceType,
        ...sourcePayload,
        organization: context.organization.name,
        projectId: context.project.id || context.project.name,
        projectName: context.project.name,
        teamId: context.team.id,
        iterationId: context.sprint.id,
        iterationPath: context.sprint.path,
        repositoryId: context.repository.id,
        repositoryName: context.repository.name,
        branch: context.repository.branch,
        actor: context.user.name,
        correlationId: context.correlationId,
      };
      const ingestResponse = await fetch(`${baseUrl}/requirements/ingest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify(common),
      });
      ingested = await ingestResponse.json() as IngestionResult & { error?: { message?: string } };
      if (!ingestResponse.ok) throw new Error(ingested.error?.message || `Requirement Ingestion returned HTTP ${ingestResponse.status}.`);
      }
      setIngestion(ingested);

      setBusyStage('refining');
      const refinementResponse = await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingested.requirementId)}/refine`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id, 'X-Correlation-ID': context.correlationId },
        body: JSON.stringify({ actor: context.user.name }),
      });
      const refined = await refinementResponse.json() as RequirementRefinementResult & { error?: { message?: string } };
      if (!refinementResponse.ok) throw new Error(refined.error?.message || `Requirement Refinement returned HTTP ${refinementResponse.status}.`);
      setRequirementRefinement(refined);

      setBusyStage('analyzing');
      const requirementAnalysisResponse = await fetch(`${baseUrl}/requirements/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id, 'X-Correlation-ID': context.correlationId },
        body: JSON.stringify({ requirementId: ingested.requirementId }),
      });
      const analyzedRequirement = await requirementAnalysisResponse.json() as RequirementAnalysisResult & { error?: { message?: string } };
      if (!requirementAnalysisResponse.ok) throw new Error(analyzedRequirement.error?.message || `Requirement Analysis returned HTTP ${requirementAnalysisResponse.status}.`);
      setRequirementAnalysis(analyzedRequirement);
      setReviewTitle(ingested.title);
      setReviewContent(analyzedRequirement.planningRequirement);
      if (analyzedRequirement.planningReadiness.status === 'Blocked') {
        throw new Error(analyzedRequirement.planningReadiness.blockers[0] || 'Resolve the requirement conflicts before Planning.');
      }
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to ingest the requirement.');
    } finally {
      setBusyStage('');
    }
  }

  async function continueToPlanning() {
    if (!ingestion || !requirementAnalysis) return;
    setBusyStage('context');
    try {
      const approvalResponse = await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/analysis/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ actor: context.user.name }),
      });
      const approved = await approvalResponse.json() as RequirementAnalysisResult & { error?: { message?: string } };
      if (!approvalResponse.ok) throw new Error(approved.error?.message || `Requirement Approval returned HTTP ${approvalResponse.status}.`);
      setRequirementAnalysis(approved);
      const planningResponse = await fetch(`${baseUrl}/planning/context/build`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ requirementId: ingestion.requirementId, actor: context.user.name, correlationId: context.correlationId }),
      });
      const landscape = await planningResponse.json() as PlanningContextResult & { error?: { message?: string } };
      if (!planningResponse.ok) throw new Error(landscape.error?.message || `Planning Context returned HTTP ${planningResponse.status}.`);
      setPlanningContext(landscape);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to continue to Planning.');
    } finally {
      setBusyStage('');
    }
  }

  async function continueFromPlanningContext() {
    if (!ingestion || !planningContext) return;
    setBusyStage('planning');
    try {
      const reviewResponse = await fetch(`${baseUrl}/planning/context/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ contextId: planningContext.contextId, decision: 'Accept', actor: context.user.name }),
      });
      const reviewed = await reviewResponse.json() as PlanningContextResult & { error?: { message?: string } };
      if (!reviewResponse.ok) throw new Error(reviewed.error?.message || `Planning Context Review returned HTTP ${reviewResponse.status}.`);
      setPlanningContext(reviewed);
      const recommendationResponse = await fetch(`${baseUrl}/planning/recommendation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ contextId: reviewed.contextId, actor: context.user.name }),
      });
      const recommendation = await recommendationResponse.json() as PlanningRecommendationResult & { error?: { message?: string } };
      if (!recommendationResponse.ok) throw new Error(recommendation.error?.message || `Planning Recommendation returned HTTP ${recommendationResponse.status}.`);
      setPlanningRecommendation(recommendation);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to continue to Planning Recommendation.');
    } finally {
      setBusyStage('');
    }
  }

  async function approvePlanningRecommendation() {
    if (!planningRecommendation) return;
    setBusyStage('planning');
    try {
      const response = await fetch(`${baseUrl}/planning/recommendation/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ recommendationId: planningRecommendation.recommendationId, actor: context.user.name }),
      });
      const approved = await response.json() as PlanningRecommendationResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(approved.error?.message || `Planning Recommendation Approval returned HTTP ${response.status}.`);
      setPlanningRecommendation(approved);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to approve the Planning Recommendation.');
    } finally {
      setBusyStage('');
    }
  }

  async function regeneratePlanningRecommendation() {
    if (!planningRecommendation) return;
    setBusyStage('planning');
    try {
      const response = await fetch(`${baseUrl}/planning/recommendation/regenerate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ recommendationId: planningRecommendation.recommendationId, actor: context.user.name }),
      });
      const regenerated = await response.json() as PlanningRecommendationResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(regenerated.error?.message || `Planning Recommendation Regeneration returned HTTP ${response.status}.`);
      setPlanningRecommendation(regenerated);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to regenerate the Planning Recommendation.');
    } finally {
      setBusyStage('');
    }
  }

  async function overridePlanningRecommendation(strategy: string, reason: string) {
    if (!planningRecommendation) return;
    setBusyStage('planning');
    try {
      const response = await fetch(`${baseUrl}/planning/recommendation/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({
          recommendationId: planningRecommendation.recommendationId,
          strategy,
          reason,
          actor: context.user.name,
        }),
      });
      const overridden = await response.json() as PlanningRecommendationResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(overridden.error?.message || `Planning Recommendation Override returned HTTP ${response.status}.`);
      setPlanningRecommendation(overridden);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to override the Planning Recommendation.');
    } finally {
      setBusyStage('');
    }
  }

  async function exportPlanningRecommendation() {
    if (!planningRecommendation) return;
    setBusyStage('planning');
    try {
      const response = await fetch(`${baseUrl}/planning/recommendation/${encodeURIComponent(planningRecommendation.recommendationId)}/export`, {
        headers: { 'X-HEI-User': context.user.id },
      });
      const report = await response.json() as Record<string, unknown> & { error?: { message?: string } };
      if (!response.ok) throw new Error(report.error?.message || `Planning Recommendation Export returned HTTP ${response.status}.`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `hei-planning-recommendation-${planningRecommendation.recommendationId}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to export the Planning Recommendation.');
    } finally {
      setBusyStage('');
    }
  }

  async function continueFromPlanningRecommendation() {
    if (!ingestion || !planningContext || !planningRecommendation || planningRecommendation.status !== 'Approved') return;
    setBusyStage('planning');
    try {
      const response = await fetch(`${baseUrl}/planning/proposal`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({
          recommendationId: planningRecommendation.recommendationId,
          actor: context.user.name,
        }),
      });
      const planning = await response.json() as PlanningProposalResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(planning.error?.message || `Planning Proposal returned HTTP ${response.status}.`);
      setResult(planning);
      setEngineeringReview(undefined);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to generate the Planning Proposal.');
    } finally {
      setBusyStage('');
    }
  }

  async function updateProposal(request: Record<string, unknown>) {
    if (!result) return;
    setBusyStage('planning');
    try {
      const response = await fetch(`${baseUrl}/planning/proposal/${encodeURIComponent(result.proposalId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ ...request, expectedVersion: result.version, actor: context.user.name }),
      });
      const updated = await response.json() as PlanningProposalResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(updated.error?.message || `Planning Proposal Update returned HTTP ${response.status}.`);
      setResult(updated);
      if (engineeringReview) await refreshEngineeringReview(updated.proposalId);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to update the Planning Proposal.');
    } finally {
      setBusyStage('');
    }
  }

  async function proposalAction(action: 'regenerate' | 'validate' | 'review' | 'approve' | 'ai-review', request: Record<string, unknown> = {}) {
    if (!result) return;
    setBusyStage('planning');
    try {
      const response = await fetch(`${baseUrl}/planning/proposal/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ proposalId: result.proposalId, expectedVersion: result.version, actor: context.user.name, ...request }),
      });
      const updated = await response.json() as PlanningProposalResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(updated.error?.message || `Planning Proposal ${action} returned HTTP ${response.status}.`);
      setResult(updated);
    } catch (error) {
      onError(error instanceof Error ? error.message : `Unable to ${action} the Planning Proposal.`);
    } finally {
      setBusyStage('');
    }
  }

  async function exportPlanningProposal() {
    if (!result) return;
    setBusyStage('planning');
    try {
      const response = await fetch(`${baseUrl}/planning/proposal/${encodeURIComponent(result.proposalId)}/export`, {
        headers: { 'X-HEI-User': context.user.id },
      });
      const report = await response.json() as Record<string, unknown> & { error?: { message?: string } };
      if (!response.ok) throw new Error(report.error?.message || `Planning Proposal Export returned HTTP ${response.status}.`);
      const url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `hei-planning-proposal-${result.proposalId}-v${result.version}.json`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to export the Planning Proposal.');
    } finally {
      setBusyStage('');
    }
  }

  async function refreshEngineeringReview(proposalId = result?.proposalId || '') {
    if (!proposalId) return;
    const response = await fetch(`${baseUrl}/engineering-reviews/proposal/${encodeURIComponent(proposalId)}`, {
      headers: { 'X-HEI-User': context.user.id },
    });
    if (response.status === 404) {
      setEngineeringReview(undefined);
      return;
    }
    const review = await response.json() as EngineeringReviewResult & { error?: { message?: string } };
    if (!response.ok) throw new Error(review.error?.message || `Engineering Review returned HTTP ${response.status}.`);
    setEngineeringReview(review);
  }

  async function startEngineeringReview() {
    if (!result) return;
    setBusyStage('planning');
    try {
      const response = await fetch(`${baseUrl}/engineering-reviews`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ proposalId: result.proposalId, owner: context.user.name, actor: context.user.name }),
      });
      const review = await response.json() as EngineeringReviewResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(review.error?.message || `Engineering Review creation returned HTTP ${response.status}.`);
      setEngineeringReview(review);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to start Engineering Review.');
    } finally {
      setBusyStage('');
    }
  }

  async function engineeringReviewAction(path: string, request: Record<string, unknown>) {
    if (!engineeringReview || !result) return;
    setBusyStage('planning');
    try {
      const response = await fetch(`${baseUrl}/engineering-reviews/${encodeURIComponent(engineeringReview.reviewId)}/${path}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ actor: context.user.name, ...request }),
      });
      const review = await response.json() as EngineeringReviewResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(review.error?.message || `Engineering Review action returned HTTP ${response.status}.`);
      setEngineeringReview(review);
      const proposalResponse = await fetch(`${baseUrl}/planning/proposal/${encodeURIComponent(result.proposalId)}`, {
        headers: { 'X-HEI-User': context.user.id },
      });
      if (proposalResponse.ok) setResult(await proposalResponse.json() as PlanningProposalResult);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to update Engineering Review.');
    } finally {
      setBusyStage('');
    }
  }

  async function exportEngineeringReview(reportType: string) {
    if (!engineeringReview) return;
    setBusyStage('planning');
    try {
      const response = await fetch(`${baseUrl}/engineering-reviews/${encodeURIComponent(engineeringReview.reviewId)}/report?type=${encodeURIComponent(reportType)}`, {
        headers: { 'X-HEI-User': context.user.id },
      });
      const report = await response.json() as { content?: string; error?: { message?: string } };
      if (!response.ok) throw new Error(report.error?.message || `Engineering Review report returned HTTP ${response.status}.`);
      const url = URL.createObjectURL(new Blob([report.content || ''], { type: 'text/markdown' }));
      const link = document.createElement('a');
      link.href = url;
      link.download = `hei-${reportType.toLowerCase().replace(/\s+/g, '-')}-${engineeringReview.reviewId}.md`;
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to export Engineering Review.');
    } finally {
      setBusyStage('');
    }
  }

  async function refreshPlanningContext() {
    if (!planningContext) return;
    setBusyStage('context');
    try {
      const response = await fetch(`${baseUrl}/planning/context/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ contextId: planningContext.contextId, actor: context.user.name }),
      });
      const refreshed = await response.json() as PlanningContextResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(refreshed.error?.message || `Planning Context Refresh returned HTTP ${response.status}.`);
      setPlanningContext(refreshed);
      setPlanningRecommendation(undefined);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to refresh Planning Context.');
    } finally {
      setBusyStage('');
    }
  }

  async function overridePlanningClassification(classification: string) {
    if (!planningContext) return;
    setBusyStage('context');
    try {
      const response = await fetch(`${baseUrl}/planning/context/classify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ contextId: planningContext.contextId, classification, actor: context.user.name }),
      });
      const updated = await response.json() as PlanningContextResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(updated.error?.message || `Planning Classification returned HTTP ${response.status}.`);
      setPlanningContext(updated);
      setPlanningRecommendation(undefined);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to update Planning classification.');
    } finally {
      setBusyStage('');
    }
  }

  async function savePlanningContextDraft() {
    if (!planningContext) return;
    setBusyStage('context');
    try {
      const response = await fetch(`${baseUrl}/planning/context/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ contextId: planningContext.contextId, decision: 'SaveDraft', actor: context.user.name }),
      });
      const saved = await response.json() as PlanningContextResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(saved.error?.message || `Planning Context Save returned HTTP ${response.status}.`);
      setPlanningContext(saved);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to save Planning Context.');
    } finally {
      setBusyStage('');
    }
  }

  async function reanalyze() {
    if (!ingestion) return;
    setBusyStage('analyzing');
    try {
      const response = await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/analysis/reanalyze`, { method: 'POST', headers: { 'X-HEI-User': context.user.id } });
      const analyzed = await response.json() as RequirementAnalysisResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(analyzed.error?.message || `Requirement Re-analysis returned HTTP ${response.status}.`);
      setRequirementAnalysis(analyzed);
      setIngestion({ ...ingestion, contextVersion: analyzed.contextVersion || ingestion.contextVersion, contentHash: analyzed.contentHash || ingestion.contentHash });
      setReviewContent(analyzed.planningRequirement);
      setEditingReview(false);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to re-analyze the requirement.');
    } finally {
      setBusyStage('');
    }
  }

  async function refinementAction(action: 'accept' | 'regenerate' | 'skip' | 'edit' | 'clarify', payload?: string | Array<{ question: string; answer: string }>) {
    if (!ingestion) return;
    setBusyStage('refining');
    try {
      const isEdit = action === 'edit';
      const path = isEdit ? 'refinement' : action === 'clarify' ? 'refinement/clarifications' : `refinement/${action}`;
      const response = await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/${path}`, {
        method: isEdit ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({
          actor: context.user.name,
          refinedRequirement: typeof payload === 'string' ? payload : undefined,
          responses: Array.isArray(payload) ? payload : undefined,
        }),
      });
      const refined = await response.json() as RequirementRefinementResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(refined.error?.message || `Requirement Refinement returned HTTP ${response.status}.`);
      setRequirementRefinement(refined);
      setBusyStage('analyzing');
      const analysisResponse = await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/analysis/reanalyze`, {
        method: 'POST', headers: { 'X-HEI-User': context.user.id },
      });
      const analyzed = await analysisResponse.json() as RequirementAnalysisResult & { error?: { message?: string } };
      if (!analysisResponse.ok) throw new Error(analyzed.error?.message || `Requirement Re-analysis returned HTTP ${analysisResponse.status}.`);
      setRequirementAnalysis(analyzed);
      setReviewContent(analyzed.planningRequirement);
      onError('');
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to update Requirement Refinement.');
    } finally {
      setBusyStage('');
    }
  }

  async function acceptanceCriteriaAction(
    action: 'suggest' | 'approve' | 'discard' | 'skip' | 'update',
    criteria?: AcceptanceCriterionSuggestion[],
  ) {
    if (!ingestion) return;
    setBusyStage('analyzing');
    try {
      const isUpdate = action === 'update';
      const path = isUpdate ? 'suggestions' : action;
      const response = await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/acceptance-criteria/${path}`, {
        method: isUpdate ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ actor: context.user.name, criteria }),
      });
      const analyzed = await response.json() as RequirementAnalysisResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(analyzed.error?.message || `Acceptance Criteria action returned HTTP ${response.status}.`);
      setRequirementAnalysis(analyzed);
      setReviewContent(analyzed.planningRequirement);
      onError('');
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to update Acceptance Criteria.');
    } finally {
      setBusyStage('');
    }
  }

  async function overrideRepository(repositoryId: string) {
    if (!ingestion || !repositoryId) return;
    setBusyStage('analyzing');
    try {
      const response = await fetch(`${baseUrl}/repositories/suggestions/${encodeURIComponent(ingestion.requirementId)}/override`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ repositoryId, actor: context.user.name, reason: 'Requirement Summary manual override' }),
      });
      const overridden = await response.json() as { error?: string };
      if (!response.ok) throw new Error(overridden.error || `Repository override returned HTTP ${response.status}.`);
      const analysisResponse = await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/analysis/reanalyze`, {
        method: 'POST', headers: { 'X-HEI-User': context.user.id },
      });
      const analyzed = await analysisResponse.json() as RequirementAnalysisResult & { error?: { message?: string } };
      if (!analysisResponse.ok) throw new Error(analyzed.error?.message || `Requirement Re-analysis returned HTTP ${analysisResponse.status}.`);
      setRequirementAnalysis(analyzed);
      setIngestion({ ...ingestion, contextVersion: analyzed.contextVersion || ingestion.contextVersion, contentHash: analyzed.contentHash || ingestion.contentHash });
      setReviewContent(analyzed.planningRequirement);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to override the repository recommendation.');
    } finally {
      setBusyStage('');
    }
  }

  async function saveReviewEdit() {
    if (!ingestion || !reviewTitle.trim() || !reviewContent.trim()) return;
    setBusyStage('analyzing');
    try {
      const response = await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/analysis/edit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id },
        body: JSON.stringify({ title: reviewTitle, content: reviewContent, actor: context.user.name }),
      });
      const analyzed = await response.json() as RequirementAnalysisResult & { error?: { message?: string } };
      if (!response.ok) throw new Error(analyzed.error?.message || `Requirement Edit returned HTTP ${response.status}.`);
      setRequirementAnalysis(analyzed);
      setIngestion({ ...ingestion, title: reviewTitle, contextVersion: analyzed.contextVersion || ingestion.contextVersion, contentHash: analyzed.contentHash || ingestion.contentHash });
      setReviewContent(analyzed.planningRequirement);
      setEditingReview(false);
    } catch (error) {
      onError(error instanceof Error ? error.message : 'Unable to save the requirement edit.');
    } finally {
      setBusyStage('');
    }
  }

  async function cancelReview() {
    if (ingestion) {
      await fetch(`${baseUrl}/requirements/${encodeURIComponent(ingestion.requirementId)}/analysis/cancel`, {
        method: 'POST', headers: { 'Content-Type': 'application/json', 'X-HEI-User': context.user.id }, body: JSON.stringify({ actor: context.user.name }),
      }).catch(() => undefined);
    }
    reset();
  }

  function reset() {
    setResult(undefined);
    setEngineeringReview(undefined);
    setPlanningRecommendation(undefined);
    setPlanningContext(undefined);
    setIngestion(undefined);
    setRequirementRefinement(undefined);
    setRequirementAnalysis(undefined);
    setEditingReview(false);
    setReviewTitle('');
    setReviewContent('');
    setTitle('');
    setContent('');
    setWorkItemId(context.route.workItemId || '');
    setDocumentName('');
    setDocumentMediaType('text/plain');
    setDocumentContentBase64('');
    setDocumentResult(undefined);
    setTranscriptResult(undefined);
    setAdoImportResult(undefined);
  }

  const requiresText = sourceType !== 'AzureDevOpsWorkItem';
  const canSubmit = Boolean(context.project.id || context.project.name)
    && (sourceType === 'AzureDevOpsWorkItem'
      ? Boolean(workItemId.trim())
      : sourceType === 'UploadDocument'
        ? Boolean(title.trim() && documentContentBase64)
        : sourceType === 'MeetingTranscript'
          ? Boolean(title.trim() && (content.trim() || documentContentBase64))
          : Boolean(title.trim() && content.trim()));

  return (
    <section className="hei-requirement-workspace" aria-label="New Requirement">
      <header>
        <div><span>Requirement Intelligence</span><h2>New Requirement</h2><p>Choose a source. HEI will create a normalized Requirement Context before Planning begins.</p></div>
        {result ? <Status value={result.status} /> : requirementAnalysis ? <Status value={`${requirementAnalysis.reviewStatus} Review`} /> : ingestion ? <Status value={ingestion.status} /> : null}
      </header>
      <RequirementProgressTimeline
        hasSource={Boolean(ingestion || result)}
        hasRefinement={Boolean(requirementRefinement || requirementAnalysis || result)}
        hasAnalysis={Boolean(requirementAnalysis)}
        hasRepository={Boolean(requirementAnalysis?.repositorySuggestion?.suggestedRepository)}
        contextCreated={Boolean(planningContext || result)}
        recommendationCreated={Boolean(planningRecommendation || result)}
        planningCreated={Boolean(result)}
        planningApproved={result?.status === 'Approved'}
      />
      {result ? (
        <PlanningProposalWorkspace
          value={result}
          busy={Boolean(busyStage)}
          onUpdate={updateProposal}
          onRegenerate={(scope, nodeId) => proposalAction('regenerate', { scope, nodeId })}
          onValidate={() => proposalAction('validate')}
          onAIReview={() => proposalAction('ai-review')}
          onExport={exportPlanningProposal}
          engineeringReview={engineeringReview}
          onStartReview={startEngineeringReview}
          onReviewAction={engineeringReviewAction}
          onExportReview={exportEngineeringReview}
          onOpenApprovals={onOpenApprovals}
          onStartAnother={reset}
        />
      ) : planningRecommendation && planningContext && ingestion ? (
        <PlanningRecommendationWorkspace
          value={planningRecommendation}
          contextValue={planningContext}
          busy={Boolean(busyStage)}
          onApprove={approvePlanningRecommendation}
          onRegenerate={regeneratePlanningRecommendation}
          onOverride={overridePlanningRecommendation}
          onExport={exportPlanningRecommendation}
          onContinue={continueFromPlanningRecommendation}
          onBack={() => setPlanningRecommendation(undefined)}
        />
      ) : planningContext && ingestion ? (
        <PlanningContextWorkspace
          value={planningContext}
          busy={Boolean(busyStage)}
          onContinue={continueFromPlanningContext}
          onRefresh={refreshPlanningContext}
          onEditRequirement={() => { setPlanningContext(undefined); setEditingReview(true); }}
          onSaveDraft={savePlanningContextDraft}
          onClassify={overridePlanningClassification}
        />
      ) : requirementAnalysis && ingestion ? (
        <RequirementReviewScreen
          analysis={requirementAnalysis}
          refinement={requirementRefinement || requirementAnalysis.requirementRefinement}
          ingestion={ingestion}
          editing={editingReview}
          title={reviewTitle}
          content={reviewContent}
          busy={Boolean(busyStage)}
          onTitleChange={setReviewTitle}
          onContentChange={setReviewContent}
          onEdit={() => setEditingReview(true)}
          onDiscardEdit={() => { setEditingReview(false); setReviewTitle(ingestion.title); setReviewContent(requirementAnalysis.planningRequirement); }}
          onSaveEdit={saveReviewEdit}
          onContinue={continueToPlanning}
          onCancel={cancelReview}
          onReanalyze={reanalyze}
          onRefinementAction={refinementAction}
          onSuggestAcceptanceCriteria={() => acceptanceCriteriaAction('suggest')}
          onApproveAcceptanceCriteria={() => acceptanceCriteriaAction('approve')}
          onDiscardAcceptanceCriteria={() => acceptanceCriteriaAction('discard')}
          onSkipAcceptanceCriteria={() => acceptanceCriteriaAction('skip')}
          onUpdateAcceptanceCriteria={(criteria) => acceptanceCriteriaAction('update', criteria)}
          onOverrideRepository={overrideRepository}
          projectName={context.project.name}
        />
      ) : (
        <form className="hei-requirement-form" onSubmit={submit}>
          <fieldset className="hei-requirement-source-picker">
            <legend>Choose Source</legend>
            {SOURCES.map((source) => (
              <label key={source.id} className={sourceType === source.id ? 'selected' : ''}>
                <input type="radio" name="requirement-source" value={source.id} checked={sourceType === source.id} onChange={() => { setSourceType(source.id); setContent(''); setDocumentName(''); setDocumentMediaType('text/plain'); setDocumentContentBase64(''); setDocumentResult(undefined); setTranscriptResult(undefined); setAdoImportResult(undefined); }} />
                <span><strong>{source.label}</strong><small>{source.description}</small></span>
              </label>
            ))}
          </fieldset>

          <div className="hei-requirement-source-workflow">
            {sourceType === 'AzureDevOpsWorkItem' ? (
              <label><span>Work item ID</span><input inputMode="numeric" value={workItemId} onChange={(event) => setWorkItemId(event.target.value)} placeholder="245" required /></label>
            ) : (
              <label><span>{sourceType === 'MeetingTranscript' ? 'Meeting title' : 'Requirement title'}</span><input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="What engineering outcome is needed?" maxLength={180} required /></label>
            )}
            {sourceType === 'UploadDocument' ? (
              <label className="wide hei-document-upload"><span>Requirement document</span><input type="file" accept=".pdf,.docx,.txt,.md,.markdown,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,text/markdown" onChange={readDocument} required={!documentContentBase64} /><small>{documentName ? `${documentName} ready to upload` : 'PDF, DOCX, TXT, and Markdown documents up to 25 MB.'}</small></label>
            ) : null}
            {sourceType === 'MeetingTranscript' ? (
              <>
                <label><span>Transcript source</span><select value={transcriptFormat} onChange={(event) => setTranscriptFormat(event.target.value as typeof transcriptFormat)}><option value="TeamsTranscript">Teams Transcript</option><option value="ZoomTranscript">Zoom Transcript</option><option value="TextTranscript">Text Transcript</option></select></label>
                <label className="wide hei-document-upload"><span>Transcript document (optional)</span><input type="file" accept=".docx,.txt,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain" onChange={readDocument} /><small>{documentName ? `${documentName} ready to analyze` : 'Upload DOCX or TXT, or paste the transcript below.'}</small></label>
              </>
            ) : null}
            {requiresText && sourceType !== 'UploadDocument' ? (
              <label className="wide"><span>{sourceType === 'MeetingTranscript' ? 'Transcript' : 'Requirement content'}</span><textarea value={content} onChange={(event) => setContent(event.target.value)} placeholder={sourceType === 'MeetingTranscript' ? 'Paste the meeting transcript. HEI will remove greetings, repetition, and conversational noise.' : 'Describe the business goal, users, expected outcome, constraints, and known acceptance criteria.'} rows={10} required={sourceType !== 'MeetingTranscript' || !documentContentBase64} /></label>
            ) : null}
          </div>

          {documentResult ? <div className="hei-uploaded-document-summary"><Signal label="Uploaded File" value={documentResult.fileName} /><Signal label="Detected Type" value={documentResult.parsed?.detectedType || 'Unknown'} /><Signal label="Pages" value={String(documentResult.parsed?.pages || 0)} /><Signal label="Analysis" value={documentResult.readyForAnalysis ? 'Ready for Analysis' : documentResult.status} /></div> : null}
          {transcriptResult ? <TranscriptSummary result={transcriptResult} /> : null}
          {adoImportResult ? <AdoWorkItemSummary result={adoImportResult} /> : null}
          <div className="hei-intake-context"><strong>Planning context</strong><span>{context.project.name || 'Project required'}</span><span>{context.team.name || 'Team unavailable'}</span><span>{context.repository.name || 'Repository will be resolved by HEI'}</span></div>
          <details className="hei-future-sources"><summary>Future sources</summary><div>{FUTURE_SOURCES.map((source) => <span key={source}>{source} · Coming later</span>)}</div></details>
          <button className="planner-button primary" type="submit" disabled={Boolean(busyStage) || !canSubmit}>{busyStage === 'uploading' ? `Uploading ${sourceType === 'MeetingTranscript' ? 'Transcript' : 'Document'}...` : busyStage === 'parsing' ? 'Parsing Document...' : busyStage === 'analyzing' ? 'Analyzing Requirement...' : busyStage === 'ingesting' ? 'Ingesting Requirement...' : busyStage === 'context' ? 'Building Planning Context...' : busyStage === 'planning' ? 'Preparing Planning Recommendation...' : 'Ingest & Analyze'}</button>
        </form>
      )}
    </section>
  );
}

function Signal({ label, value }: { label: string; value: string }) { return <div><span>{label}</span><strong>{value}</strong></div>; }
function PlanningProposalWorkspace({ value, busy, onUpdate, onRegenerate, onValidate, onAIReview, onExport, engineeringReview, onStartReview, onReviewAction, onExportReview, onOpenApprovals, onStartAnother }: {
  value: PlanningProposalResult;
  busy: boolean;
  onUpdate: (request: Record<string, unknown>) => void;
  onRegenerate: (scope: string, nodeId?: string) => void;
  onValidate: () => void;
  onAIReview: () => void;
  onExport: () => void;
  engineeringReview?: EngineeringReviewResult;
  onStartReview: () => void;
  onReviewAction: (path: string, request: Record<string, unknown>) => void;
  onExportReview: (reportType: string) => void;
  onOpenApprovals: () => void;
  onStartAnother: () => void;
}) {
  const tabs = ['Summary', 'Work Items', 'Approval'];
  const advancedTabs = ['Traceability', 'Dependencies', 'Engineering Estimate', 'Validation', 'Diff', 'Azure DevOps Preview', 'History'];
  const [tab, setTab] = useState('Work Items');
  const [advancedTab, setAdvancedTab] = useState('Traceability');
  const [selectedId, setSelectedId] = useState(value.nodes[0]?.nodeId || '');
  const selected = value.nodes.find((node) => node.nodeId === selectedId) || value.nodes[0];
  const nodeCounts = value.nodes.reduce<Record<string, number>>((counts, node) => ({ ...counts, [node.type]: (counts[node.type] || 0) + 1 }), {});
  const editable = !['Approved', 'Published', 'Archived'].includes(value.status);
  const roots = value.nodes.filter((node) => !node.parentId).sort((a, b) => a.order - b.order);

  function renderTree(parent: ProposalNode, depth = 0): React.ReactNode {
    const children = value.nodes.filter((node) => node.parentId === parent.nodeId).sort((a, b) => a.order - b.order);
    return <React.Fragment key={parent.nodeId}>
      <button type="button" className={selected?.nodeId === parent.nodeId ? 'selected' : ''} style={{ paddingLeft: `${10 + depth * 16}px` }} onClick={() => setSelectedId(parent.nodeId)}>
        <span>{parent.type}</span><strong>{parent.title}</strong><small>{parent.storyPoints} points · {parent.confidence}%</small>
      </button>
      {children.map((child) => renderTree(child, depth + 1))}
    </React.Fragment>;
  }

  return <section className="hei-planning-proposal-workspace" aria-live="polite">
    <header className="hei-planning-proposal-header">
      <div><span>Planning Proposal</span><h2>{value.title}</h2><p>Review the work items, approve the proposal, then create them in Azure DevOps.</p></div>
      <div><Status value={value.status} /><strong>v{value.version}</strong><details className="hei-proposal-header-actions"><summary>More</summary><div><button className="planner-button secondary" type="button" disabled={busy || !editable} onClick={() => onRegenerate('Entire Proposal')}>Regenerate</button><button className="planner-button secondary" type="button" disabled={busy} onClick={onAIReview}>AI Review</button><button className="planner-button secondary" type="button" disabled={busy} onClick={onExport}>Export</button></div></details></div>
    </header>
    <div className="hei-planning-proposal-metrics">
      <Signal label="Health" value={`${value.health.overallHealth}%`} />
      <Signal label="Scope" value={`${nodeCounts.Feature || 0} Features · ${nodeCounts.Story || 0} Stories · ${nodeCounts.Task || 0} Tasks`} />
      <Signal label="Estimate" value={`${value.estimate.engineeringDays} days · ${value.estimate.storyPoints} points`} />
      <Signal label="Risk" value={value.health.risk} />
    </div>
    <nav className="hei-planning-proposal-tabs" aria-label="Planning Proposal sections">
      {tabs.map((item) => <button key={item} type="button" className={tab === item ? 'active' : ''} onClick={() => setTab(item)}>{item}</button>)}
    </nav>

    {tab === 'Work Items' ? <div className="hei-planning-proposal-layout">
      <aside className="hei-proposal-tree" aria-label="Planning hierarchy">
        <header><strong>Planning Hierarchy</strong><span>{value.nodes.length} items</span></header>
        <div>{roots.map((node) => renderTree(node))}</div>
      </aside>
      <main>{selected ? <ProposalNodeEditor key={`${selected.nodeId}-${value.version}`} node={selected} nodes={value.nodes} editable={editable} busy={busy} onUpdate={onUpdate} onRegenerate={onRegenerate} /> : <p>No planning item selected.</p>}</main>
    </div> : null}

    {tab === 'Summary' ? <div className="hei-proposal-card-grid">
      <ProposalSummaryCard title="Executive Summary" items={[value.executiveSummary || 'Executive summary pending.']} />
      <ProposalSummaryCard title="Business Goal" items={[value.businessGoal || 'Business goal requires review.']} />
      <ProposalSummaryCard title="Recommended Strategy" items={[value.recommendedStrategy.title || value.recommendedStrategy.type.replace(/_/g, ' '), value.recommendedStrategy.reason || value.recommendedStrategy.summary, `${value.recommendedStrategy.confidence}% confidence`]} />
      <ProposalSummaryCard title="Planning Scope" items={[`${nodeCounts.Epic || 0} Epic`, `${nodeCounts.Feature || 0} Features`, `${nodeCounts.Story || 0} Stories`, `${nodeCounts.Task || 0} Tasks`]} />
      <ProposalSummaryCard title="Engineering Estimate" items={[`${value.estimate.engineeringDays} engineering days`, `${value.estimate.storyPoints} story points`, `${value.estimate.sprintCount} sprints`, `${value.estimate.developersRequired} developers`]} />
      <ProposalSummaryCard title="Planning Quality" items={[`${value.health.overallHealth}% overall health`, `${value.health.planningConfidence}% planning confidence`, `${value.health.engineeringConfidence}% engineering confidence`, `${value.validation.findings.length} validation findings`]} />
      <ProposalSummaryCard title="Definition of Done" items={value.definitionOfDone.length ? value.definitionOfDone : ['Definition of Done pending.']} />
      <ProposalSummaryCard title="Source Lineage" items={[`Requirement ${value.requirementId}`, `Recommendation ${value.recommendationId}`, `Context ${value.contextId}`, `Knowledge ${value.knowledgeVersion || 'Not versioned'}`, `Correlation ${value.correlationId}`]} />
      {value.aiReview?.status ? <ProposalSummaryCard title="HEI Proposal Review" items={[value.aiReview.status, value.aiReview.summary || 'Review completed.', `${value.aiReview.confidence || 0}% confidence`, ...(value.aiReview.recommendations || []).slice(0, 3)]} /> : null}
    </div> : null}

    <details className="hei-proposal-advanced"><summary>Advanced details</summary><nav aria-label="Advanced proposal sections">{advancedTabs.map((item) => <button key={item} type="button" className={advancedTab === item ? 'active' : ''} onClick={() => setAdvancedTab(item)}>{item}</button>)}</nav>
    {advancedTab === 'Traceability' ? <><div className="hei-proposal-table-wrap"><table><thead><tr><th>Artifact</th><th>Requirement</th><th>Business Goals</th><th>Acceptance Criteria</th><th>Repository Modules</th><th>Knowledge</th></tr></thead><tbody>{value.nodes.map((node) => <tr key={node.nodeId}><td><strong>{node.title}</strong><small>{node.type}</small></td><td>{node.traceability.requirementId}</td><td>{node.traceability.businessGoals.join(', ') || 'Not mapped'}</td><td>{node.traceability.acceptanceCriterionIds?.length || 0} mapped</td><td>{node.traceability.repositoryModules.join(', ') || 'Repository mapping pending'}</td><td>{node.traceability.knowledgeReferences?.join(', ') || 'No knowledge references'}</td></tr>)}</tbody></table></div>
      <div className="hei-proposal-card-grid">{value.acceptanceCriteria.map((criterion) => <article key={criterion.criterionId}><span>{criterion.origin} · {criterion.status}</span><h3>{criterion.title}</h3><p>{criterion.text}</p><small>{criterion.mappedNodeIds.length} Story mapping(s) · {Math.round((criterion.confidence || 0) * (criterion.confidence <= 1 ? 100 : 1))}% confidence</small></article>)}</div></> : null}

    {advancedTab === 'Dependencies' ? <div className="hei-proposal-card-grid">
      {value.dependencies.length ? value.dependencies.map((edge, index) => <article key={`${edge.from}-${edge.to}-${index}`}><span>{edge.type || 'Depends On'}</span><h3>{value.nodes.find((node) => node.nodeId === edge.from)?.title || edge.from}</h3><p>Depends on {value.nodes.find((node) => node.nodeId === edge.to)?.title || edge.to}</p></article>) : <article><h3>No dependencies identified</h3><p>Add dependencies to establish implementation order and critical path.</p></article>}
      {Object.entries(value.dependencyGraph.categories || {}).map(([category, entries]) => <article key={category}><span>Dependency Category</span><h3>{category.replace(/([A-Z])/g, ' $1')}</h3><p>{entries.length ? `${entries.length} mapped` : 'No dependencies identified'}</p></article>)}
    </div> : null}

    {advancedTab === 'Engineering Estimate' ? <ProposalEstimateEditor value={value} editable={editable} busy={busy} onUpdate={onUpdate} onRegenerate={onRegenerate} /> : null}

    {advancedTab === 'Validation' ? <section className="hei-proposal-review-panel"><header><div><span>Proposal Validation</span><h3>{value.validation.status}</h3></div><button className="planner-button primary" type="button" disabled={busy} onClick={onValidate}>Validate Proposal</button></header>
      {value.validation.findings.length ? value.validation.findings.map((finding, index) => <article key={`${finding.code}-${index}`}><Status value={finding.severity} /><div><strong>{finding.code.replace(/_/g, ' ')}</strong><p>{finding.message}</p></div></article>) : <p>No validation findings. The proposal satisfies the current mandatory gates.</p>}
    </section> : null}

    {advancedTab === 'Diff' ? <section className="hei-proposal-review-panel"><header><div><span>HEI Planning Diff</span><h3>{value.diff.changes.length} proposed changes</h3><p>{value.diff.estimatedSprintImpact}</p></div></header>
      {value.diff.changes.map((change, index) => <article key={`${change.title}-${index}`}><Status value={change.action} /><div><strong>{change.artifactType || change.type || 'Artifact'}: {change.title}</strong><p>{change.reason}</p></div><small>{change.confidence}%</small></article>)}
    </section> : null}

    {advancedTab === 'Azure DevOps Preview' ? <section className="hei-proposal-review-panel"><header><div><span>Azure DevOps Preview</span><h3>{value.azureDevOpsPreview.workItems.length} proposed work items</h3><p>Preview only. Nothing is created until this proposal is approved and a separate synchronization action is authorized.</p></div><Status value={value.azureDevOpsPreview.writeStatus} /></header>
      <div className="hei-proposal-card-grid"><Signal label="Writes Performed" value={String(value.azureDevOpsPreview.writesPerformed)} /><Signal label="Area Path" value={value.azureDevOpsPreview.areaPath || 'Not selected'} /><Signal label="Iteration" value={value.azureDevOpsPreview.iterationPath || 'Not selected'} /><Signal label="Links" value={String(value.azureDevOpsPreview.links.length)} /></div>
      {value.azureDevOpsPreview.workItems.map((item) => <article key={item.proposalNodeId}><Status value={item.operation} /><div><strong>{item.workItemType}: {item.title}</strong><p>{item.parentProposalNodeId ? 'Parent-child link prepared.' : 'Hierarchy root.'}</p></div><small>{item.storyPoints ? `${item.storyPoints} points` : 'No point field'}</small></article>)}
    </section> : null}

    {advancedTab === 'History' ? <section className="hei-proposal-review-panel"><header><div><span>Version History</span><h3>{value.history.length + 1} versions</h3></div></header>
      {value.history.length ? [...value.history].reverse().map((entry) => <article key={`${entry.version}-${entry.timestamp}`}><Status value={`v${entry.version}`} /><div><strong>{entry.reason}</strong><p>{entry.author} · {new Date(entry.timestamp).toLocaleString()}</p><small>{entry.changes.join(' ')}</small></div>{editable ? <button className="planner-button secondary" type="button" disabled={busy} onClick={() => onUpdate({ operation: 'rollback', targetVersion: entry.version, reason: `Rollback to version ${entry.version}` })}>Restore</button> : null}</article>) : <p>This is the first Planning Proposal version.</p>}
    </section> : null}</details>

    {tab === 'Approval' ? <EngineeringReviewPanel value={value} review={engineeringReview} busy={busy} onStart={onStartReview} onAction={onReviewAction} onExport={onExportReview} onOpenApprovals={onOpenApprovals} /> : null}

    <footer className="hei-planning-proposal-footer">
      <div><strong>{value.status}</strong><span>Health {value.health.overallHealth}% · Repository {value.health.repositoryCoverage}% · v{value.version}</span></div>
      <div>{value.status === 'Approved' && engineeringReview?.synchronization.authorized ? <button className="planner-button primary" type="button" onClick={onOpenApprovals}>Create in Azure DevOps</button> : engineeringReview ? <button className="planner-button primary" type="button" onClick={() => setTab('Approval')}>Continue Approval</button> : <button className="planner-button primary" type="button" disabled={busy || !value.validation.mandatoryPassed} onClick={onStartReview}>Review &amp; Approve</button>}<button className="planner-button secondary" type="button" onClick={onStartAnother}>Start Another</button></div>
    </footer>
  </section>;
}

function ProposalNodeEditor({ node, nodes, editable, busy, onUpdate, onRegenerate }: {
  node: ProposalNode; nodes: ProposalNode[]; editable: boolean; busy: boolean;
  onUpdate: (request: Record<string, unknown>) => void;
  onRegenerate: (scope: string, nodeId?: string) => void;
}) {
  const [title, setTitle] = useState(node.title);
  const [description, setDescription] = useState(node.description);
  const [businessValue, setBusinessValue] = useState(node.businessValue);
  const [acceptance, setAcceptance] = useState(node.acceptanceCriteria.join('\n'));
  const siblings = nodes.filter((item) => item.parentId === node.parentId && item.nodeId !== node.nodeId && item.type === node.type);
  const parentOptions = nodes.filter((item) => ({ Feature: 'Epic', Story: 'Feature', Task: 'Story', 'Sub Task': 'Task' } as Record<string, string>)[node.type] === item.type);
  return <section className="hei-proposal-node-editor">
    <header><div><span>{node.type}</span><h3>{node.title}</h3><p>{node.origin} · {node.confidence}% confidence · v{node.planningVersion}</p></div><Status value={node.status} /></header>
    <label><span>Title</span><input value={title} disabled={!editable} onChange={(event) => setTitle(event.target.value)} /></label>
    <label><span>Description</span><textarea rows={5} value={description} disabled={!editable} onChange={(event) => setDescription(event.target.value)} /></label>
    <label><span>Business Value</span><textarea rows={3} value={businessValue} disabled={!editable} onChange={(event) => setBusinessValue(event.target.value)} /></label>
    <label><span>Acceptance Criteria</span><textarea rows={6} value={acceptance} disabled={!editable} onChange={(event) => setAcceptance(event.target.value)} /></label>
    <div className="hei-proposal-node-meta"><Signal label="Story Points" value={String(node.storyPoints)} /><Signal label="Risk" value={node.risk} /><Signal label="Priority" value={node.priority} /><Signal label="Repository" value={node.repositoryMapping.repositoryName || 'Mapping pending'} />{node.storyType ? <Signal label="Story Type" value={node.storyType} /> : null}</div>
    <details><summary>Engineering context</summary><p>{node.repositoryMapping.reason || 'Repository mapping requires review.'}</p><ContextTags title="Repository Modules" values={node.repositoryModules} empty="Repository mapping pending." /><ContextTags title="Services, APIs and Screens" values={[...node.affectedServices, ...node.affectedApis, ...node.affectedScreens]} empty="No service, API, or screen impact identified." /><ContextTags title="Database and Integrations" values={[...node.affectedDatabaseObjects, ...node.externalIntegrations]} empty="No database or external integration impact identified." /><ContextTags title="Technical Notes" values={node.technicalNotes} empty="No technical notes." /><ContextTags title="Generated Tests" values={node.generatedTests} empty="No generated tests." /><ContextTags title="Definition of Done" values={node.definitionOfDone} empty="Definition of Done pending." /></details>
    <div className="hei-proposal-node-actions">
      <button className="planner-button primary" type="button" disabled={!editable || busy || !title.trim()} onClick={() => onUpdate({ nodeId: node.nodeId, changes: { title: title.trim(), description: description.trim(), businessValue: businessValue.trim(), acceptanceCriteria: acceptance.split('\n').map((item) => item.trim()).filter(Boolean) }, reason: `Edited ${node.type} ${node.title}` })}>Save Changes</button>
      <button className="planner-button secondary" type="button" disabled={!editable || busy || node.status === 'Approved'} onClick={() => onUpdate({ operation: 'approve', nodeId: node.nodeId, reason: `Approved ${node.title}` })}>Approve Item</button>
      <button className="planner-button secondary" type="button" disabled={!editable || busy || node.status === 'Rejected'} onClick={() => onUpdate({ operation: 'reject', nodeId: node.nodeId, reason: `Rejected ${node.title}` })}>Reject Item</button>
      <details className="hei-proposal-item-more"><summary>More actions</summary><div>
        <button className="planner-button secondary" type="button" disabled={!editable || busy} onClick={() => onRegenerate(node.type, node.nodeId)}>Regenerate</button>
        <button className="planner-button secondary" type="button" disabled={!editable || busy} onClick={() => onUpdate({ operation: 'duplicate', nodeId: node.nodeId, reason: `Duplicated ${node.title}` })}>Duplicate</button>
        {['Feature', 'Story', 'Task'].includes(node.type) ? <button className="planner-button secondary" type="button" disabled={!editable || busy} onClick={() => { const second = window.prompt('Second item title'); if (second) onUpdate({ operation: 'split', nodeId: node.nodeId, titles: [node.title, second], reason: `Split ${node.title}` }); }}>Split</button> : null}
        {siblings.length ? <button className="planner-button secondary" type="button" disabled={!editable || busy} onClick={() => onUpdate({ operation: 'merge', nodeId: node.nodeId, mergeNodeIds: [node.nodeId, siblings[0].nodeId], reason: `Merged ${node.title}` })}>Merge with Next</button> : null}
        {parentOptions.length ? <select aria-label="Move to parent" disabled={!editable || busy} value={node.parentId} onChange={(event) => onUpdate({ operation: 'move', nodeId: node.nodeId, parentId: event.target.value, reason: `Moved ${node.title}` })}>{parentOptions.map((parent) => <option key={parent.nodeId} value={parent.nodeId}>{parent.title}</option>)}</select> : null}
        {node.type !== 'Epic' ? <button className="planner-button danger" type="button" disabled={!editable || busy} onClick={() => { if (window.confirm(`Delete ${node.title} and its children?`)) onUpdate({ operation: 'delete', nodeId: node.nodeId, reason: `Deleted ${node.title}` }); }}>Delete</button> : null}
      </div></details>
    </div>
  </section>;
}

function ProposalEstimateEditor({ value, editable, busy, onUpdate, onRegenerate }: {
  value: PlanningProposalResult; editable: boolean; busy: boolean;
  onUpdate: (request: Record<string, unknown>) => void; onRegenerate: (scope: string) => void;
}) {
  const [days, setDays] = useState(String(value.estimate.engineeringDays));
  const [points, setPoints] = useState(String(value.estimate.storyPoints));
  const [reason, setReason] = useState(value.estimate.overrideReason);
  return <section className="hei-proposal-estimate-panel">
    <header><div><span>Engineering Estimate</span><h3>{value.estimate.engineeringDays} days · {value.estimate.storyPoints} points</h3><p>AI estimate remains visible beside any human override.</p></div><Status value={`${value.estimate.confidence}% confidence`} /></header>
    <div className="hei-proposal-card-grid"><Signal label="AI Engineering Days" value={String(value.estimate.aiEngineeringDays)} /><Signal label="AI Story Points" value={String(value.estimate.aiStoryPoints)} /><Signal label="Sprint Count" value={String(value.estimate.sprintCount)} /><Signal label="Developers" value={String(value.estimate.developersRequired)} /><Signal label="Complexity" value={value.estimate.complexity} /><Signal label="Risk" value={value.estimate.risk} /></div>
    <div className="hei-proposal-estimate-form"><label><span>Engineering Days</span><input type="number" value={days} disabled={!editable} onChange={(event) => setDays(event.target.value)} /></label><label><span>Story Points</span><input type="number" value={points} disabled={!editable} onChange={(event) => setPoints(event.target.value)} /></label><label><span>Override Reason</span><input value={reason} disabled={!editable} onChange={(event) => setReason(event.target.value)} /></label></div>
    <div><button className="planner-button primary" type="button" disabled={!editable || busy || !reason.trim()} onClick={() => onUpdate({ estimate: { engineeringDays: Number(days), storyPoints: Number(points), overrideReason: reason }, reason })}>Save Override</button> <button className="planner-button secondary" type="button" disabled={!editable || busy} onClick={() => onRegenerate('Engineering Estimate')}>Restore AI Estimate</button></div>
  </section>;
}

function EngineeringReviewPanel({ value, review, busy, onStart, onAction, onExport, onOpenApprovals }: {
  value: PlanningProposalResult; review?: EngineeringReviewResult; busy: boolean;
  onStart: () => void; onAction: (path: string, request: Record<string, unknown>) => void;
  onExport: (reportType: string) => void; onOpenApprovals: () => void;
}) {
  const [comments, setComments] = useState('');
  const [section, setSection] = useState('Business Review');
  const [targetType, setTargetType] = useState('Epic');
  const [targetId, setTargetId] = useState('');
  const [changeType, setChangeType] = useState('Business Clarification');
  const [reviewer, setReviewer] = useState('');
  if (!review) return <section className="hei-proposal-review-panel">
    <header><div><span>Planning Approval</span><h3>Approval not started</h3><p>Validation must pass before the proposal can receive its single approval.</p></div><Status value={value.validation.status} /></header>
    <div className="hei-proposal-card-grid"><Signal label="Proposal Version" value={`v${value.version}`} /><Signal label="Context Version" value={value.contextVersion} /><Signal label="Knowledge Version" value={value.knowledgeVersion || 'Not versioned'} /><Signal label="Validation" value={value.validation.status} /></div>
    <button className="planner-button primary" type="button" disabled={busy || !value.validation.mandatoryPassed} onClick={onStart}>Start Planning Approval</button>
  </section>;
  const stage = review.currentStage;
  const canDecide = Boolean(stage.stageId) && !['Approved', 'Rejected', 'Superseded', 'Expired'].includes(review.status);
  if (review.stages.length === 1) return <section className="hei-proposal-review-panel hei-engineering-review hei-single-approval">
    <header><div><span>Planning Approval</span><h3>{review.status === 'Approved' ? 'Proposal approved' : 'Ready for one approval'}</h3><p>{review.status === 'Approved' ? 'The approved proposal can now be created in Azure DevOps.' : 'Confirm the scope, validation, estimate, and repository mapping.'}</p></div><Status value={review.readiness.status} /></header>
    <div className="hei-single-approval-summary">
      <Signal label="Work Items" value={String(value.nodes.filter((item) => item.status !== 'Rejected').length)} />
      <Signal label="Estimate" value={`${value.estimate.engineeringDays} days · ${value.estimate.storyPoints} points`} />
      <Signal label="Validation" value={review.proposalSummary.validationStatus} />
      <Signal label="Risk" value={review.proposalSummary.riskScore || 'Not rated'} />
    </div>
    {review.stale ? <div className="hei-review-blocker">The proposal changed after this approval started. Start approval again for the latest version.</div> : null}
    {review.readiness.blockers.length ? <div className="hei-review-blocker"><strong>Resolve before approval</strong><ul>{review.readiness.blockers.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
    {canDecide ? <label className="hei-single-approval-comment"><span>Approval note (optional)</span><textarea rows={3} value={comments} onChange={(event) => setComments(event.target.value)} placeholder="Add a decision note or explain requested changes" /></label> : null}
    <div className="hei-review-actions">
      {canDecide ? <><button className="planner-button primary" type="button" disabled={busy || !review.readiness.approvalAllowed} onClick={() => onAction('decision', { decision: comments.trim() ? 'ApproveWithComments' : 'Approve', role: stage.role, comments: comments.trim() })}>Approve Proposal</button><button className="planner-button secondary" type="button" disabled={busy || !comments.trim()} onClick={() => onAction('decision', { decision: 'RequestChanges', role: stage.role, comments: comments.trim(), changeType: 'Business Clarification' })}>Request Changes</button><button className="planner-button danger" type="button" disabled={busy || !comments.trim()} onClick={() => onAction('decision', { decision: 'Reject', role: stage.role, comments: comments.trim() })}>Reject</button></> : null}
      {review.status === 'Approved' ? <button className="planner-button primary" type="button" onClick={onOpenApprovals}>Create in Azure DevOps</button> : null}
    </div>
    <details className="hei-single-approval-details"><summary>Review details</summary>
      <div className="hei-review-sections">{review.sections.map((item) => <article key={item.name}><div><strong>{item.name}</strong><p>{item.commentCount} comment(s)</p></div><Status value={item.status} /></article>)}</div>
      {review.decisions.length ? <div className="hei-review-history">{review.decisions.map((item) => <article key={item.decisionId}><Status value={item.decision} /><div><strong>{item.stage}</strong><p>{item.comments || 'No additional comments.'}</p></div><small>{item.reviewer}</small></article>)}</div> : null}
      <div className="hei-review-actions"><button className="planner-button secondary" type="button" onClick={() => onExport('Review Report')}>Export Review</button><button className="planner-button secondary" type="button" onClick={onOpenApprovals}>Open Approval Center</button></div>
    </details>
  </section>;
  return <section className="hei-proposal-review-panel hei-engineering-review">
    <header><div><span>Planning Approval</span><h3>{review.status}</h3><p>{stage.name ? 'One approval is required before Azure DevOps creation.' : 'Approval complete.'}</p></div><Status value={review.readiness.status} /></header>
    <div className="hei-planning-proposal-metrics">
      <Signal label="Proposal" value={`v${review.proposalVersion}`} /><Signal label="Context" value={review.contextVersion} />
      <Signal label="Knowledge" value={review.knowledgeVersion || 'Not versioned'} /><Signal label="Recommendation" value={`v${review.recommendationVersion}`} />
      <Signal label="Risk" value={review.proposalSummary.riskScore || 'Not rated'} /><Signal label="Effort" value={`${review.proposalSummary.estimatedEffort || 0} days`} />
      <Signal label="Validation" value={review.proposalSummary.validationStatus} />
    </div>
    {review.stale ? <div className="hei-review-blocker">This review belongs to an older proposal version. Start a new review.</div> : null}
    {review.readiness.blockers.length ? <div className="hei-review-blocker"><strong>Approval blocked</strong><ul>{review.readiness.blockers.map((item) => <li key={item}>{item}</li>)}</ul></div> : null}
    <div className="hei-review-stage-chain">{review.stages.map((item) => <article key={item.stageId} className={item.stageId === review.currentStageId ? 'active' : ''}><span>{item.role}</span><strong>{item.name}</strong><Status value={item.status} /><small>{item.assignedReviewer || item.approvedBy || 'Reviewer not assigned'}</small></article>)}</div>
    <div className="hei-review-sections">{review.sections.map((item) => <article key={item.name}><div><strong>{item.name}</strong><p>{item.commentCount} comment(s)</p></div><Status value={item.status} /></article>)}</div>
    {canDecide ? <div className="hei-review-assign"><label><span>Assign Current Reviewer</span><input value={reviewer} onChange={(event) => setReviewer(event.target.value)} placeholder={stage.assignedReviewer || 'Reviewer name'} /></label><button className="planner-button secondary" type="button" disabled={busy || !reviewer.trim()} onClick={() => onAction('assign', { stageId: stage.stageId, reviewer: reviewer.trim() })}>Assign Reviewer</button></div> : null}
    <div className="hei-review-compose">
      <h4>Add Inline Review Comment</h4>
      <div><label><span>Section</span><select value={section} onChange={(event) => setSection(event.target.value)}>{review.sections.map((item) => <option key={item.name}>{item.name}</option>)}</select></label><label><span>Target</span><select value={targetType} onChange={(event) => setTargetType(event.target.value)}>{['Epic', 'Feature', 'Story', 'Task', 'Acceptance Criterion', 'Engineering Note', 'Estimate', 'Dependency', 'Repository Mapping'].map((item) => <option key={item}>{item}</option>)}</select></label><label><span>Artifact ID</span><input value={targetId} onChange={(event) => setTargetId(event.target.value)} placeholder="Optional artifact ID" /></label></div>
      <label><span>Comment</span><textarea rows={3} value={comments} onChange={(event) => setComments(event.target.value)} /></label>
      <button className="planner-button secondary" type="button" disabled={busy || !comments.trim()} onClick={() => { onAction('comments', { section, targetType, targetId, comment: comments.trim() }); setComments(''); }}>Add Comment</button>
    </div>
    <details open={review.changeRequests.some((item) => item.status === 'Open')}><summary>Change Requests ({review.changeRequests.length})</summary>
      <div className="hei-review-compose"><label><span>Change Type</span><select value={changeType} onChange={(event) => setChangeType(event.target.value)}>{['Story Split', 'Story Merge', 'Estimate Change', 'Repository Change', 'Acceptance Criteria Update', 'Dependency Update', 'Architecture Review', 'Business Clarification'].map((item) => <option key={item}>{item}</option>)}</select></label><label><span>Description</span><textarea rows={3} value={comments} onChange={(event) => setComments(event.target.value)} /></label><button className="planner-button secondary" type="button" disabled={busy || !comments.trim()} onClick={() => { onAction('change-requests', { changeType, description: comments.trim(), targetId }); setComments(''); }}>Request Change</button></div>
      {review.changeRequests.map((item) => <article key={item.changeRequestId}><Status value={item.status} /><div><strong>{item.type}</strong><p>{item.description}</p></div><small>{item.requestedBy}</small></article>)}
    </details>
    <details><summary>Comments and Decision History</summary>
      {review.comments.map((item) => <article key={item.commentId}><Status value={item.status} /><div><strong>{item.section} · {item.targetType}</strong><p>{item.comment}</p></div><small>{item.author}</small></article>)}
      {review.decisions.map((item) => <article key={item.decisionId}><Status value={item.decision} /><div><strong>{item.stage}</strong><p>{item.comments || 'No additional comments.'}</p></div><small>{item.reviewer}</small></article>)}
    </details>
    <div className="hei-review-actions">
      {canDecide ? <><button className="planner-button primary" type="button" disabled={busy || !review.readiness.approvalAllowed} onClick={() => onAction('decision', { decision: comments.trim() ? 'ApproveWithComments' : 'Approve', role: stage.role, comments: comments.trim() })}>Approve {stage.name}</button><button className="planner-button secondary" type="button" disabled={busy || !comments.trim()} onClick={() => onAction('decision', { decision: 'RequestChanges', role: stage.role, comments: comments.trim(), changeType })}>Request Changes</button><button className="planner-button danger" type="button" disabled={busy || !comments.trim()} onClick={() => onAction('decision', { decision: 'Reject', role: stage.role, comments: comments.trim() })}>Reject</button><button className="planner-button secondary" type="button" disabled={busy} onClick={() => onAction('decision', { decision: 'SaveDraftReview', role: stage.role })}>Save Draft Review</button></> : null}
      <button className="planner-button secondary" type="button" onClick={() => onExport('Review Report')}>Export Review Report</button>
      <button className="planner-button secondary" type="button" onClick={() => onExport('Decision Log')}>Export Decision Log</button>
      <button className="planner-button secondary" type="button" onClick={onOpenApprovals}>Open Approval Center</button>
    </div>
  </section>;
}

function ProposalMeter({ label, value }: { label: string; value: number }) {
  return <div className="hei-proposal-meter"><div><span>{label}</span><strong>{value}%</strong></div><progress max="100" value={value} /></div>;
}

function ProposalSummaryCard({ title, items }: { title: string; items: string[] }) {
  return <article><h3>{title}</h3><ul>{items.map((item) => <li key={item}>{item}</li>)}</ul></article>;
}

function statusTone(value: string) {
  const normalized = value.toLowerCase();
  if (/blocked|failed|error|unavailable|critical|high severity/.test(normalized)) return 'error';
  if (/recommendation|review|pending|confidence|warning|medium severity|needs user input/.test(normalized)) return 'warning';
  if (/ready|approved|complete|active|selected|good/.test(normalized)) return 'success';
  return '';
}
function Status({ value }: { value: string }) { return <span className={`hei-operation-chip ${statusTone(value)}`.trim()}>{value}</span>; }

function RequirementProgressTimeline({ hasSource, hasRefinement, hasAnalysis, hasRepository, contextCreated, recommendationCreated, planningCreated, planningApproved }: {
  hasSource: boolean;
  hasRefinement: boolean;
  hasAnalysis: boolean;
  hasRepository: boolean;
  contextCreated: boolean;
  recommendationCreated: boolean;
  planningCreated: boolean;
  planningApproved: boolean;
}) {
  const stages = [
    { label: 'Understand', done: hasAnalysis && hasRepository, active: !hasAnalysis || !hasRepository },
    { label: 'Plan', done: planningCreated, active: hasAnalysis && hasRepository && !planningCreated },
    { label: 'Approve', done: planningApproved, active: planningCreated && !planningApproved },
    { label: 'Create in Azure DevOps', done: false, active: planningApproved },
  ];
  return <nav className="hei-requirement-progress" aria-label="Requirement progress">
    {stages.map((stage, index) => {
      const state = stage.done ? 'complete' : stage.active ? 'active' : 'locked';
      return <div key={stage.label} className={state} aria-current={stage.active ? 'step' : undefined}>
        <span className="hei-requirement-progress-marker" aria-hidden="true">{stage.done ? '✓' : stage.active ? '●' : '○'}</span>
        <span>{stage.label}</span>
        {index < stages.length - 1 ? <i aria-hidden="true" /> : null}
      </div>;
    })}
  </nav>;
}

function PlanningContextWorkspace({ value, busy, onContinue, onRefresh, onEditRequirement, onSaveDraft, onClassify }: {
  value: PlanningContextResult;
  busy: boolean;
  onContinue: () => void;
  onRefresh: () => void;
  onEditRequirement: () => void;
  onSaveDraft: () => void;
  onClassify: (classification: string) => void;
}) {
  const counts = value.azureDevOps.counts || {};
  const markdown = value.engineeringDiscovery?.repositoryMarkdown || {};
  const markdownDiagnostics = markdown.diagnostics || {};
  const selectedMarkdown = markdown.selected || [];
  const markdownConflicts = markdown.conflicts || [];
  const blocked = value.readiness.status === 'Blocked';
  const classifications = ['NEW_INITIATIVE', 'NEW_FEATURE', 'EXTEND_FEATURE', 'MODIFY_EXISTING', 'BUG', 'ENHANCEMENT', 'AI_RECOMMENDED'];
  return <section className="hei-planning-context-workspace" aria-label="Planning Context">
    <header>
      <div><span>Plan Preparation</span><h2>Engineering Context</h2><p>HEI checked existing work, repository evidence, and reusable engineering knowledge.</p></div>
      <Status value={planningContextReadiness(value.readiness.status)} />
    </header>

    <section className="hei-planning-context-summary">
      <header><div><span>Planning Context Summary</span><h3>{value.summary.recommendedStrategy || 'Review the current engineering landscape.'}</h3></div><Status value={`${value.summary.planningConfidence}% confidence`} /></header>
      <div>
        <Signal label="Current Project" value={value.summary.currentProject || 'Current Azure DevOps project'} />
        <Signal label="Repository" value={value.summary.repository} />
        <Signal label="Planning Mode" value={formatPlanningMode(value.summary.planningMode)} />
        <Signal label="Engineering Risk" value={value.summary.engineeringRisk} />
        <Signal label="Complexity" value={value.summary.estimatedComplexity} />
        <Signal label="Context Score" value={`${value.readiness.score}%`} />
      </div>
    </section>

    <details className="hei-process-details"><summary>Review engineering context and evidence</summary><div className="hei-planning-context-grid">
      <section>
        <header><div><span>Azure DevOps Overview</span><h3>Existing project work</h3></div><Status value={`${Object.values(counts).reduce((total, count) => total + Number(count || 0), 0)} items`} /></header>
        <div className="hei-planning-context-metrics">
          <Signal label="Epics" value={String(counts.Epic || 0)} />
          <Signal label="Features" value={String(counts.Feature || 0)} />
          <Signal label="Stories" value={String(counts.Story || 0)} />
          <Signal label="Tasks" value={String(counts.Task || 0)} />
        </div>
        <p>Current sprint: <strong>{value.azureDevOps.currentSprint?.name || value.azureDevOps.currentSprint?.path || 'No current sprint synchronized'}</strong></p>
      </section>

      <section>
        <header><div><span>Requirement Classification</span><h3>{formatPlanningMode(value.classification.value)}</h3></div><Status value={`${value.classification.confidence}% confidence`} /></header>
        <p>{value.classification.reason}</p>
        <label><span>Manual override</span><select value={value.classification.value} disabled={busy} onChange={(event) => onClassify(event.target.value)}>{classifications.map((item) => <option key={item} value={item}>{formatPlanningMode(item)}</option>)}</select></label>
      </section>

      <section className="wide">
        <header><div><span>Repository Recommendation</span><h3>{value.repository.repositoryName || 'Continue without Repository'}</h3><p>{value.repository.reason}</p></div><Status value={`${value.repository.confidence}% confidence`} /></header>
        <div className="hei-planning-context-metrics">
          <Signal label="Mode" value={value.repository.mode} />
          <Signal label="Branch" value={value.repository.branch || 'Not available'} />
          <Signal label="Snapshot" value={value.repository.snapshotVersion || 'Not available'} />
          <Signal label="Repository Reuse" value={`${value.repository.reusePercent}%`} />
        </div>
        <ContextTags title="Affected Modules" values={value.repository.affectedModules} empty="No affected modules identified." />
        <ContextTags title="Affected APIs and Services" values={[...value.repository.affectedApis, ...value.repository.affectedServices]} empty="No matching APIs or services identified." />
        <ContextTags title="Reusable Engineering Assets" values={[...value.repository.reusableComponents, ...value.repository.reusableTests]} empty="No reusable repository assets identified." />
      </section>

      <section>
        <header><div><span>Engineering Memory</span><h3>Validated prior knowledge</h3></div><Status value={`${value.memory.coverage}% coverage`} /></header>
        <ContextTags title="Previous Work" values={value.memory.matches.map((item) => item.title)} empty="No approved Engineering Memory match." />
        <ContextTags title="Lessons and Decisions" values={[...value.memory.lessonsLearned, ...value.memory.architectureDecisions.map((item) => item.title)]} empty="No relevant lessons or architecture decisions." />
      </section>

      <section>
        <header><div><span>Engineering Impact</span><h3>{value.impact.complexity} complexity</h3></div><Status value={value.summary.engineeringRisk} /></header>
        <ContextTags title="Affected Work" values={[...value.impact.affectedFeatures, ...value.impact.affectedStories]} empty="No existing work item impact identified." />
        <ContextTags title="Risks and Breaking Changes" values={[...value.impact.potentialRisks, ...value.impact.potentialBreakingChanges]} empty="No material risk identified." />
        <p>{value.impact.sprintImpact}</p>
      </section>
    </div>

    <section className="hei-planning-context-discovery">
      <header>
        <div><span>Engineering Discovery</span><h3>Context Used</h3><p>Traceable repository knowledge selected before planning reasoning.</p></div>
        <Status value={`${selectedMarkdown.length} sections selected`} />
      </header>
      <div className="hei-planning-context-metrics">
        <Signal label="Markdown Files Scanned" value={String(markdownDiagnostics.filesScanned || 0)} />
        <Signal label="Sections Indexed" value={String(markdownDiagnostics.sectionsIndexed || 0)} />
        <Signal label="Sections Selected" value={String(markdownDiagnostics.sectionsSelected || selectedMarkdown.length)} />
        <Signal label="Rejected Context" value={String(markdownDiagnostics.rejectedContextCount || 0)} />
        <Signal label="Conflicts" value={String(markdownDiagnostics.conflictsDetected || markdownConflicts.length)} />
        <Signal label="Repository Revision" value={markdownDiagnostics.repositoryRevision || 'Not available'} />
        <Signal label="Knowledge Version" value={value.engineeringDiscovery?.projectIntelligence?.knowledge?.version || 'Not available'} />
      </div>
      {selectedMarkdown.length ? <div className="hei-planning-context-documents">
        {selectedMarkdown.map((item) => <details key={item.evidenceId}>
          <summary><strong>{item.path}</strong><span>{item.heading}</span></summary>
          <div>
            <Status value={item.classification.replace(/_/g, ' ')} />
            <p>{item.selectionReason}</p>
            <small>{item.authority} · {item.confidence}% confidence · {item.evidenceId}</small>
          </div>
        </details>)}
      </div> : <p className="hei-planning-context-empty">No relevant repository Markdown was available for this planning context.</p>}
      {markdownConflicts.length ? <div className="hei-planning-context-conflicts">
        <strong>Conflicts require review</strong>
        {markdownConflicts.map((item) => <p key={item.conflictId}>{item.path} / {item.heading}: {item.reason}</p>)}
      </div> : null}
    </section>

    <section className="hei-planning-context-similar">
      <header><div><span>Similar Existing Work</span><h3>Reuse before creating</h3></div><Status value={`${value.similarWork.length} matches`} /></header>
      {value.similarWork.length ? <div>{value.similarWork.map((item) => <article key={`${item.workItemType}-${item.workItemId}`}>
        <header><div><span>{item.workItemType} #{item.workItemId}</span><h4>{item.title}</h4></div><Status value={`${item.similarity}% similar`} /></header>
        <p>{item.reason}</p><footer><strong>{item.suggestedAction}</strong><span>{item.state || 'State unavailable'}</span></footer>
      </article>)}</div> : <p className="hei-planning-context-empty">No similar synchronized work was found. HEI recommends bounded new planning.</p>}
    </section>

    <section className="hei-planning-context-recommendation">
      <header><div><span>Preliminary Planning Signal</span><h3>{formatPlanningMode(value.recommendation.planningMode)}</h3><p>{value.recommendation.strategy}</p></div><Status value={`${value.recommendation.confidence}% confidence`} /></header>
      <div>
        <ContextTags title="Create" values={value.recommendation.create} empty="No explicit creation candidates yet." />
        <ContextTags title="Reuse" values={value.recommendation.reuse} empty="No reuse candidates." />
        <ContextTags title="Modify" values={value.recommendation.modify} empty="No modification candidates." />
        <ContextTags title="Do Not Create" values={value.recommendation.doNotCreate} empty="No duplicate scope detected." />
      </div>
    </section></details>

    <section className="hei-planning-context-readiness">
      <header><div><span>Planning Readiness</span><h3>{planningContextReadiness(value.readiness.status)}</h3></div><strong>{value.readiness.score}%</strong></header>
      <div className="hei-planning-context-metrics">
        <Signal label="Repository Coverage" value={`${value.readiness.repositoryCoverage}%`} />
        <Signal label="Memory Coverage" value={`${value.readiness.memoryCoverage}%`} />
        <Signal label="Requirement Completeness" value={`${value.readiness.requirementCompleteness}%`} />
        <Signal label="Existing Work Match" value={`${value.readiness.existingWorkMatch}%`} />
      </div>
      {value.readiness.blockers.length ? <ul className="error">{value.readiness.blockers.map((item) => <li key={item}>{item}</li>)}</ul> : null}
      {value.readiness.warnings.length ? <ul>{value.readiness.warnings.map((item) => <li key={item}>{item}</li>)}</ul> : null}
    </section>

    <footer className="hei-planning-context-actions">
      <div><span>Context {value.contextVersion}</span><strong>{value.reviewStatus}</strong></div>
      <button className="planner-button secondary" type="button" disabled={busy} onClick={onEditRequirement}>Edit Requirement</button>
      <button className="planner-button primary" type="button" disabled={busy || blocked} onClick={onContinue}>{busy ? 'Preparing Plan...' : 'Continue to Plan'}</button>
    </footer>
  </section>;
}

function PlanningRecommendationWorkspace({ value, contextValue, busy, onApprove, onRegenerate, onOverride, onExport, onContinue, onBack }: {
  value: PlanningRecommendationResult;
  contextValue: PlanningContextResult;
  busy: boolean;
  onApprove: () => void;
  onRegenerate: () => void;
  onOverride: (strategy: string, reason: string) => void;
  onExport: () => void;
  onContinue: () => void;
  onBack: () => void;
}) {
  const approved = value.status === 'Approved';
  const [overrideStrategy, setOverrideStrategy] = useState(value.strategy);
  const [overrideReason, setOverrideReason] = useState('');
  const diffSymbols: Record<string, string> = { Create: '+', Modify: '~', Reuse: '=', Ignore: '-', Merge: 'M', Split: 'S', Delete: 'D', Move: '>' };
  return <section className="hei-planning-recommendation-workspace" aria-label="Planning Recommendation" aria-live="polite">
    <header>
      <div><span>Plan Decision</span><h2>Recommended Plan</h2><p>Confirm HEI's recommended approach before generating editable work items.</p></div>
      <Status value={approved ? 'Approved' : 'Needs Review'} />
    </header>

    <section className="hei-planning-recommendation-hero">
      <header>
        <div><span>Recommended Strategy</span><h3>{value.title}</h3><p>{value.engineeringReasoning[0]}</p></div>
        <strong>{value.confidence.overall}%</strong>
      </header>
      <div className="hei-planning-context-metrics">
        <Signal label="Expected Scope" value={`${value.summary.expectedStoryCount} Stories · ${value.summary.expectedTaskCount} Tasks`} />
        <Signal label="Estimated Effort" value={value.primaryRecommendation?.estimatedEffort || 'Calculated in proposal'} />
        <Signal label="Reuse" value={`${value.primaryRecommendation?.reuseScore ?? 0}%`} />
        <Signal label="Complexity" value={value.impact.estimatedComplexity} />
        <Signal label="Risk" value={value.impact.riskLevel} />
      </div>
      <div className="hei-planning-recommendation-actions-list">
        {value.actions.map((action) => <article key={action.action}><div><strong>{action.action}</strong><p>{action.reason}</p></div><Status value={`${action.confidence}% confidence`} /></article>)}
      </div>
    </section>

    <details className="hei-process-details"><summary>Compare recommendation, evidence, and alternatives</summary><div className="hei-planning-recommendation-grid">
      <section>
        <header><div><span>Recommendation Summary</span><h3>Expected planning shape</h3></div></header>
        <div className="hei-planning-context-metrics">
          <Signal label="Expected Sprint" value={value.summary.expectedSprint} />
          <Signal label="Stories" value={String(value.summary.expectedStoryCount)} />
          <Signal label="Tasks" value={String(value.summary.expectedTaskCount)} />
          <Signal label="Modifications" value={String(value.summary.expectedModificationCount)} />
        </div>
        <p>{value.expectedAzureDevOpsImpact}</p>
      </section>
      <section>
        <header><div><span>Engineering Impact</span><h3>{value.impact.repositoryName || contextValue.repository.repositoryName}</h3></div><Status value={value.impact.riskLevel} /></header>
        <p><strong>Business:</strong> {value.impact.businessImpact}</p>
        <p><strong>Engineering:</strong> {value.impact.engineeringImpact}</p>
        <p><strong>Repository:</strong> {value.impact.repositoryImpact}</p>
        <ContextTags title="Affected Modules" values={value.impact.affectedModules} empty="No evidence-matched modules identified." />
        <ContextTags title="Affected APIs and Services" values={[...value.impact.affectedApis, ...value.impact.affectedServices]} empty="No affected APIs or services identified." />
      </section>
    </div>

    <div className="hei-planning-recommendation-grid">
      <section>
        <header><div><span>Planning Readiness</span><h3>{value.readiness?.status || 'Needs Clarification'}</h3></div><Status value={`${value.readiness?.overallReadiness ?? value.confidence.planning}%`} /></header>
        <div className="hei-planning-context-metrics">
          <Signal label="Requirement" value={`${value.readiness?.requirementCompleteness ?? 0}%`} />
          <Signal label="Acceptance" value={`${value.readiness?.acceptanceCriteriaCoverage ?? 0}%`} />
          <Signal label="Dependencies" value={`${value.readiness?.dependencyResolution ?? 0}%`} />
          <Signal label="Architecture" value={`${value.readiness?.architectureConfidence ?? 0}%`} />
        </div>
        <ContextTags title="Clarifications Required" values={Object.values(value.missingInformation || {}).flat()} empty="No unresolved information was identified." />
      </section>
      <section>
        <header><div><span>Reuse Recommendation</span><h3>Evidence-backed reuse</h3></div><Status value={`${value.reuseSuggestions?.length || 0} candidates`} /></header>
        <ContextTags
          title="Reusable Engineering Assets"
          values={(value.reuseSuggestions || []).map((item) => `${item.type}: ${item.name} (${item.confidence}%)`)}
          empty="No reusable implementation evidence was identified."
        />
        <ContextTags
          title="Dependencies"
          values={Object.values(value.dependencyAnalysis || {}).flat().map((item) => item.name)}
          empty="No dependencies were identified in the reviewed context."
        />
      </section>
    </div>

    <section className="hei-planning-recommendation-diff">
      <header><div><span>HEI Planning Diff</span><h3>Proposed changes before Planning Proposal</h3><p>This is the intended planning change set. No work item has been created or modified.</p></div><Status value={`${value.diff.operations.length} changes`} /></header>
      <div className="hei-planning-diff-summary">
        {Object.entries(value.diff.summary).filter(([, count]) => count > 0).map(([action, count]) => <Signal key={action} label={action} value={String(count)} />)}
      </div>
      {value.diff.operations.length ? <div className="hei-planning-diff-list">{value.diff.operations.map((operation) => <article key={operation.operationId} className={operation.action.toLowerCase()}>
        <span aria-hidden="true">{diffSymbols[operation.action] || '·'}</span>
        <div><strong>{operation.action} {operation.artifactType}</strong><h4>{operation.title}</h4><p>{operation.reason}</p></div>
        <Status value={`${operation.confidence}%`} />
      </article>)}</div> : <p className="hei-planning-context-empty">No planning changes are recommended.</p>}
    </section>

    <section className="hei-planning-context-similar">
      <header><div><span>Existing Work</span><h3>Reuse and modification candidates</h3></div><Status value={`${value.similarWork.length} matches`} /></header>
      {value.similarWork.length ? <div>{value.similarWork.map((item) => <article key={`${item.workItemType}-${item.workItemId}`}>
        <header><div><span>{item.workItemType} #{item.workItemId}</span><h4>{item.title}</h4></div><Status value={`${item.similarity}% similar`} /></header>
        <p>{item.reason}</p><footer><strong>{item.suggestedAction}</strong><span>{item.state || 'State unavailable'}</span></footer>
      </article>)}</div> : <p className="hei-planning-context-empty">No sufficiently similar synchronized work was found.</p>}
      <div className="hei-planning-recommendation-existing-context">
        <ContextTags title="Open Pull Requests" values={value.relatedPullRequests.map((item) => item.title || `Pull Request #${item.pullRequestId || item.id || 'Unknown'}`)} empty="No overlapping open pull requests." />
        <ContextTags title="Current Development" values={value.currentDevelopment.map((item) => item.title || `Work Item #${item.workItemId || item.id || 'Unknown'}`)} empty="No related active development." />
        <ContextTags title="Repository Components" values={value.repositoryComponents} empty="No reusable repository components." />
        <ContextTags title="Dependencies and Architecture" values={[...value.dependencies, ...value.architectureDecisions.map((item) => item.title || '').filter(Boolean)]} empty="No dependency or architecture constraint identified." />
      </div>
    </section>

    <section className="hei-planning-recommendation-alternatives">
      <header><div><span>Alternative Strategies</span><h3>Other valid approaches</h3></div></header>
      <div>{value.alternatives.map((alternative) => <article key={alternative.strategy}>
        <header><div><h4>{alternative.title}</h4><p>{alternative.description || alternative.rejectedReason}</p></div><Status value={`${alternative.confidence}%`} /></header>
        <div className="hei-planning-context-metrics"><Signal label="Effort" value={alternative.estimatedEffort || 'Requires estimation'} /><Signal label="Reuse" value={`${alternative.reuseScore || 0}%`} /></div>
        <div><ContextTags title="Advantages" values={alternative.pros} empty="No additional advantage identified." /><ContextTags title="Trade-offs" values={alternative.cons} empty="No trade-off identified." /></div>
        <ContextTags title="Risks" values={alternative.risks || []} empty="No additional risk identified." />
        <button className="planner-button secondary" type="button" disabled={busy} onClick={() => onOverride(alternative.strategy, `Selected ${alternative.title} after reviewing HEI alternatives.`)}>Choose This Strategy</button>
      </article>)}</div>
    </section>

    <details className="hei-planning-recommendation-reasoning">
      <summary>View Engineering Reasoning</summary>
      <ContextTags title="Why this strategy" values={value.engineeringReasoning} empty="No additional reasoning recorded." />
      <ContextTags title="Risks" values={value.risks} empty="No material planning risks identified." />
      <ContextTags title="Rejected alternatives" values={value.rejectedAlternatives.map((item) => `${item.title}: ${item.explanation}`)} empty="No alternatives were rejected." />
      <ContextTags title="Evidence used" values={value.explanation?.evidenceUsed || []} empty="No evidence references recorded." />
      <p><strong>Reasoning mode:</strong> {value.reasoningMode || 'Deterministic'} · <strong>Prompt:</strong> {value.promptVersion || 'Not applicable'}</p>
    </details>

    <details className="hei-planning-recommendation-override">
      <summary>Override Recommendation</summary>
      <div>
        <label><span>Strategy</span><select value={overrideStrategy} disabled={busy} onChange={(event) => setOverrideStrategy(event.target.value)}>
          {['NEW_EPIC', 'NEW_FEATURE', 'NEW_STORY', 'EXTEND_EXISTING_FEATURE', 'EXTEND_EXISTING_EPIC', 'EXTEND_EXISTING_STORY', 'MODIFY_EXISTING_STORY', 'BUG_FIX', 'ENHANCEMENT', 'TECHNICAL_DEBT', 'REFACTOR_EXISTING_FEATURE', 'SPIKE', 'CONFIGURATION_CHANGE', 'DOCUMENTATION_UPDATE', 'MIXED_RECOMMENDATION', 'AI_RECOMMENDED'].map((strategy) => <option key={strategy} value={strategy}>{formatPlanningMode(strategy)}</option>)}
        </select></label>
        <label><span>Reason</span><input value={overrideReason} onChange={(event) => setOverrideReason(event.target.value)} placeholder="Why is this strategy more appropriate?" /></label>
        <button className="planner-button secondary" type="button" disabled={busy || !overrideReason.trim() || overrideStrategy === value.strategy} onClick={() => onOverride(overrideStrategy, overrideReason.trim())}>Apply Override</button>
      </div>
    </details><div className="hei-process-detail-actions"><button className="planner-button secondary" type="button" disabled={busy} onClick={onExport}>Export Report</button><button className="planner-button secondary" type="button" disabled={busy} onClick={onRegenerate}>Re-evaluate with AI</button></div></details>

    <footer className="hei-planning-context-actions">
      <div><span>Recommendation v{value.version}</span><strong>{approved ? `Approved by ${value.approvedBy}` : 'Awaiting decision'}</strong></div>
      <button className="planner-button secondary" type="button" disabled={busy} onClick={onBack}>Back</button>
      {approved
        ? <button className="planner-button primary" type="button" disabled={busy} onClick={onContinue}>{busy ? 'Generating Work Items...' : 'Generate Work Items'}</button>
        : <button className="planner-button primary" type="button" disabled={busy} onClick={onApprove}>{busy ? 'Accepting...' : 'Accept Recommended Plan'}</button>}
    </footer>
  </section>;
}

function ContextTags({ title, values, empty }: { title: string; values: string[]; empty: string }) {
  const unique = Array.from(new Set(values.filter(Boolean)));
  return <div className="hei-planning-context-tags"><strong>{title}</strong>{unique.length ? <div>{unique.map((value) => <span key={value}>{value}</span>)}</div> : <p>{empty}</p>}</div>;
}

function formatPlanningMode(value: string) {
  return value.toLowerCase().split('_').map((part) => part.charAt(0).toUpperCase() + part.slice(1)).join(' ');
}

function planningContextReadiness(value: PlanningContextResult['readiness']['status']) {
  if (value === 'ReadyWithRecommendations') return 'Ready with Recommendations';
  if (value === 'NeedsUserDecision') return 'Needs User Decision';
  return value;
}

function TranscriptSummary({ result }: { result: TranscriptResult }) {
  const analysis = result.analysis;
  return <section className="hei-transcript-summary" aria-label="Meeting transcript analysis">
    <header><div><span>Meeting Summary</span><h3>{analysis.meetingTitle}</h3><p>{analysis.meetingSummary}</p></div><Status value={result.readyForPlanning ? 'Ready for Planning' : 'Needs Review'} /></header>
    <div className="hei-requirement-signals"><Signal label="Requirements Found" value={String(analysis.requirements.length)} /><Signal label="Action Items" value={String(analysis.actionItems.length)} /><Signal label="Decisions" value={String(analysis.decisions.length)} /><Signal label="Participants" value={String(analysis.participants.length)} /></div>
    <details open><summary>Requirements Found</summary><FindingList items={analysis.requirements} empty="No explicit requirements found." /></details>
    <details><summary>Action Items</summary><FindingList items={analysis.actionItems} empty="No action items found." /></details>
    <details><summary>Decisions</summary><FindingList items={analysis.decisions} empty="No business decisions found." /></details>
  </section>;
}

function FindingList({ items, empty }: { items: TranscriptFinding[]; empty: string }) {
  return items.length ? <ul>{items.map((item) => <li key={item.findingId}>{item.text}{item.speaker ? <small> {item.speaker}{item.timestamp ? ` · ${item.timestamp}` : ''}</small> : null}</li>)}</ul> : <p>{empty}</p>;
}

function AdoWorkItemSummary({ result }: { result: AdoWorkItemImportResult }) {
  const item = result.currentWorkItem;
  const summary = result.requirementSummary;
  return <section className="hei-transcript-summary" aria-label="Azure DevOps work item requirement summary">
    <header><div><span>Current Work Item</span><h3>{item.workItemType} #{result.workItemId} · {item.title}</h3><p>{summary.summary}</p></div><Status value={summary.readyForPlanning ? 'Ready for Planning' : 'Needs Review'} /></header>
    <div className="hei-requirement-signals"><Signal label="Acceptance Criteria" value={String(summary.acceptanceCriteria.length)} /><Signal label="Dependencies" value={String(summary.dependencies.length)} /><Signal label="Missing Information" value={String(summary.missingInformation.length)} /><Signal label="Revision" value={String(result.workItemRevision)} /></div>
    <details open><summary>Acceptance Criteria</summary>{summary.acceptanceCriteria.length ? <ul>{summary.acceptanceCriteria.map((criterion, index) => <li key={`${index}-${criterion}`}>{criterion}</li>)}</ul> : <p>No acceptance criteria captured.</p>}</details>
    <details><summary>Dependencies</summary>{summary.dependencies.length ? <ul>{summary.dependencies.map((dependency) => <li key={`${dependency.workItemId}-${dependency.relationship}`}>Work item #{dependency.workItemId} · {dependency.relationship}</li>)}</ul> : <p>No dependency links identified.</p>}</details>
    <details open={!summary.readyForPlanning}><summary>Missing Information</summary>{summary.missingInformation.length ? <ul>{summary.missingInformation.map((value) => <li key={value}>{value}</li>)}</ul> : <p>No blocking information gaps.</p>}</details>
  </section>;
}

function RequirementRefinementCard({ value, busy, onAction }: {
  value: RequirementRefinementResult;
  busy: boolean;
  onAction: (action: 'accept' | 'regenerate' | 'skip' | 'edit' | 'clarify', payload?: string | Array<{ question: string; answer: string }>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value.refinedRequirement);
  const [clarifications, setClarifications] = useState<Record<string, string>>(() => Object.fromEntries((value.clarificationResponses || []).map((item) => [item.question, item.answer])));
  useEffect(() => {
    setDraft(value.refinedRequirement);
    setClarifications(Object.fromEntries((value.clarificationResponses || []).map((item) => [item.question, item.answer])));
  }, [value.version, value.refinedRequirement]);
  const accepted = value.status === 'Accepted';
  const normalizedOriginal = value.originalRequirement.trim().replace(/\s+/g, ' ');
  const normalizedRefinement = value.refinedRequirement.trim().replace(/\s+/g, ' ');
  const wordingChanged = normalizedOriginal !== normalizedRefinement;
  const capabilities = value.coreCapabilities?.length ? value.coreCapabilities : value.coreCapability ? [value.coreCapability] : [];
  const repositoryHints = value.repositorySearchHints?.length ? value.repositorySearchHints : value.potentialRepositoryTerms || [];
  const markdownHints = value.markdownSearchHints?.length ? value.markdownSearchHints : value.potentialMarkdownTerms || [];
  const adoHints = value.azureDevOpsSearchHints?.length ? value.azureDevOpsSearchHints : value.potentialAzureDevOpsTerms || [];
  return <section className="hei-requirement-refinement" aria-label="AI Requirement Refinement">
    <header>
      <div><span>AI Requirement Refinement</span><h3>{wordingChanged ? 'Engineering-ready wording' : 'Ready as written'}</h3><p>{wordingChanged ? 'HEI improved clarity before repository or Azure DevOps discovery. Your original requirement remains unchanged.' : 'HEI found the source requirement clear enough for engineering analysis. No rewritten copy is needed.'}</p></div>
      <Status value={`${value.status} · ${Math.round(value.confidence * 100)}%`} />
    </header>
    <div className="hei-requirement-refinement-comparison">
      <article><span>Original Requirement</span><p>{value.originalRequirement}</p></article>
      <article><span>Refined Requirement</span>{editing ? <textarea rows={7} value={draft} onChange={(event) => setDraft(event.target.value)} /> : <p>{value.refinedRequirement}</p>}</article>
    </div>
    <div className="hei-requirement-refinement-summary">
      <Signal label="Executive Summary" value={value.executiveSummary || value.requirementSummary || 'Not identified'} />
      <Signal label="Business Goal" value={value.businessGoal || value.businessObjective || 'Needs clarification'} />
      <Signal label="User Intent" value={value.userIntent || 'Needs clarification'} />
      <Signal label="Expected Outcome" value={value.expectedOutcome || 'Needs clarification'} />
    </div>
    <div className="hei-requirement-refinement-taxonomy">
      <ContextTags title="Actors" values={[value.primaryActor, ...(value.secondaryActors || [])].filter(Boolean)} empty="No actor identified." />
      <ContextTags title="Core capabilities" values={capabilities} empty="No capability identified." />
      <ContextTags title="Business entities" values={value.businessEntities || []} empty="No business entity identified." />
      <ContextTags title="Engineering concepts" values={value.engineeringConcepts || []} empty="No engineering concept identified." />
    </div>
    <div className="hei-requirement-refinement-details">
      <div><strong>{wordingChanged ? 'Changes Made' : 'Wording Review'}</strong>{value.changes.length ? <ul>{value.changes.map((item, index) => <li key={`${index}-${item.change}`}><b>{item.change}</b><small>{item.reason}</small></li>)}</ul> : <p>{wordingChanged ? 'No change summary was provided.' : 'The source wording is suitable for analysis.'}</p>}</div>
      <div><strong>Reasoning</strong>{value.reasoning.length ? <ul>{value.reasoning.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No additional reasoning was provided.</p>}</div>
      <div><strong>Ambiguities</strong>{value.ambiguities.length ? <ul>{value.ambiguities.map((item) => <li key={item}>{item}</li>)}</ul> : <p>No explicit ambiguity identified.</p>}</div>
      <div className="hei-requirement-clarifications"><strong>Clarification Candidates</strong>{value.clarificationCandidates.length ? <>{value.clarificationCandidates.map((item) => <label key={item}><span>{item}</span><textarea rows={2} value={clarifications[item] || ''} onChange={(event) => setClarifications((current) => ({ ...current, [item]: event.target.value }))} placeholder="Add the business answer HEI should use" /></label>)}<button className="planner-button secondary" type="button" disabled={busy || !value.clarificationCandidates.some((item) => (clarifications[item] || '').trim())} onClick={() => onAction('clarify', value.clarificationCandidates.filter((item) => (clarifications[item] || '').trim()).map((question) => ({ question, answer: clarifications[question].trim() })))}>Apply Answers &amp; Regenerate</button></> : <p>No clarification required before analysis.</p>}</div>
    </div>
    {value.provider === 'Deterministic' && value.fallbackReason ? <div className="hei-requirement-refinement-fallback" role="status"><strong>AI refinement fallback</strong><p>{value.fallbackReason}</p></div> : null}
    <details><summary>Refinement lineage and search hints</summary><div className="hei-requirement-refinement-lineage"><Signal label="Provider" value={value.provider || 'Deterministic'} /><Signal label="Model" value={value.model || 'Not applicable'} /><Signal label="Prompt" value={value.promptVersion} /><Signal label="Version" value={String(value.version)} /></div><ContextTags title="Repository search hints" values={repositoryHints} empty="No repository hints inferred." /><ContextTags title="Markdown search hints" values={markdownHints} empty="No Markdown hints inferred." /><ContextTags title="Azure DevOps search hints" values={adoHints} empty="No Azure DevOps hints inferred." /><ContextTags title="Possible modules" values={value.possibleModuleNames || []} empty="No possible module names inferred." /><ContextTags title="Possible features" values={value.possibleFeatureNames || []} empty="No possible feature names inferred." /></details>
    <footer>
      {editing ? <><button className="planner-button primary" type="button" disabled={busy || !draft.trim()} onClick={() => { onAction('edit', draft.trim()); setEditing(false); }}>Save Refinement</button><button className="planner-button secondary" type="button" disabled={busy} onClick={() => { setDraft(value.refinedRequirement); setEditing(false); }}>Cancel Edit</button></> : <>
        <button className="planner-button primary" type="button" disabled={busy || accepted} onClick={() => onAction('accept')}>{accepted ? (wordingChanged ? 'Refinement Accepted' : 'Wording Accepted') : (wordingChanged ? 'Accept Refinement' : 'Use Original Requirement')}</button>
        <button className="planner-button secondary" type="button" disabled={busy} onClick={() => { setDraft(value.refinedRequirement); setEditing(true); }}>Edit</button>
        <button className="planner-button secondary" type="button" disabled={busy} onClick={() => onAction('regenerate')}>Regenerate</button>
        <button className="planner-button secondary" type="button" disabled={busy || value.status === 'Skipped'} onClick={() => onAction('skip')}>Skip Refinement</button>
      </>}
    </footer>
  </section>;
}

function RequirementReviewScreen({ analysis, refinement, ingestion, editing, title, content, busy, onTitleChange, onContentChange, onEdit, onDiscardEdit, onSaveEdit, onContinue, onCancel, onReanalyze, onRefinementAction, onSuggestAcceptanceCriteria, onApproveAcceptanceCriteria, onDiscardAcceptanceCriteria, onSkipAcceptanceCriteria, onUpdateAcceptanceCriteria, onOverrideRepository, projectName }: {
  analysis: RequirementAnalysisResult;
  refinement?: RequirementRefinementResult;
  ingestion: IngestionResult;
  editing: boolean;
  title: string;
  content: string;
  busy: boolean;
  onTitleChange: (value: string) => void;
  onContentChange: (value: string) => void;
  onEdit: () => void;
  onDiscardEdit: () => void;
  onSaveEdit: () => void;
  onContinue: () => void;
  onCancel: () => void;
  onReanalyze: () => void;
  onRefinementAction: (action: 'accept' | 'regenerate' | 'skip' | 'edit' | 'clarify', payload?: string | Array<{ question: string; answer: string }>) => void;
  onSuggestAcceptanceCriteria: () => void;
  onApproveAcceptanceCriteria: () => void;
  onDiscardAcceptanceCriteria: () => void;
  onSkipAcceptanceCriteria: () => void;
  onUpdateAcceptanceCriteria: (criteria: AcceptanceCriterionSuggestion[]) => void;
  onOverrideRepository: (repositoryId: string) => void;
  projectName: string;
}) {
  const review = analysis.reviewContext;
  const blocked = analysis.planningReadiness.status === 'Blocked';
  const needsReview = analysis.planningReadiness.status !== 'Ready';
  const acceptancePending = analysis.acceptanceCriteriaState?.state === 'AISuggested' && analysis.acceptanceCriteriaState?.status === 'PendingReview';
  const qualityFindingCount = (analysis.acceptanceCriteriaSuggestions.length ? 0 : analysis.missingAcceptanceCriteria.length)
    + analysis.ambiguousRequirements.length + analysis.conflictingRequirements.length + analysis.duplicateRequirements.length;
  const suggestion = analysis.repositorySuggestion;
  const recommendedRepository = suggestion?.suggestedRepository;
  const repositoryOptions = suggestion?.availableRepositories || [];
  const [overrideRepositoryId, setOverrideRepositoryId] = useState(recommendedRepository?.repositoryId || '');
  const [repositorySearch, setRepositorySearch] = useState('');
  const visibleRepositories = repositoryOptions.filter((repository) => (repository.name || '').toLowerCase().includes(repositorySearch.trim().toLowerCase()));
  return <section className="hei-requirement-review" aria-label="Requirement Summary" aria-live="polite">
    <header><div><span>Mandatory Review</span><h2>Requirement Summary</h2><p>Validate HEI's understanding before Planning begins. No Planning Pack has been created.</p></div><Status value={readinessLabel(analysis.planningReadiness.status)} /></header>
    {editing ? <div className="hei-requirement-review-editor">
      <label><span>Requirement title</span><input value={title} onChange={(event) => onTitleChange(event.target.value)} maxLength={180} /></label>
      <label><span>Analyzed requirement</span><textarea value={content} onChange={(event) => onContentChange(event.target.value)} rows={18} /></label>
      <div className="hei-requirement-actions"><button className="planner-button primary" type="button" disabled={busy || !title.trim() || !content.trim()} onClick={onSaveEdit}>Save & Re-analyze</button><button className="planner-button secondary" type="button" disabled={busy} onClick={onDiscardEdit}>Discard Edit</button></div>
    </div> : <>
      <div className="hei-requirement-review-layout">
      <div className="hei-requirement-review-main">
      <details className="hei-requirement-advanced"><summary>Source and analysis details</summary><div className="hei-requirement-review-meta">
        <Signal label="Source" value={review.source || ingestion.sourceType} />
        <Signal label="Requirement Context" value={analysis.contextVersion} />
        <Signal label="Document Type" value={review.documentType || 'Not Applicable'} />
        <Signal label="Review Status" value={analysis.reviewStatus} />
        <Signal
          label="Analysis Mode"
          value={requirementAnalysisModeLabel(analysis, refinement)}
        />
      </div></details>
      {refinement ? refinement.status === 'Accepted' ? <details className="hei-requirement-accepted-refinement"><summary><span>AI refinement accepted</span><strong>{refinement.executiveSummary || refinement.requirementSummary}</strong></summary><RequirementRefinementCard value={refinement} busy={busy} onAction={onRefinementAction} /></details> : <RequirementRefinementCard value={refinement} busy={busy} onAction={onRefinementAction} /> : null}
      <RequirementHealth analysis={analysis} ingestion={ingestion} />
      <section className="hei-repository-recommendation" aria-label="Suggested Repository">
        <header>
          <div><span>Repository Recommendation</span><h3>{recommendedRepository?.name || 'No repository detected'}</h3><p>{suggestion?.reason || 'Register a repository to enable engineering workspace detection.'}</p></div>
          <Status value={recommendedRepository ? `${Math.round((suggestion?.confidence || 0) * 100)}% confidence` : 'Not Available'} />
        </header>
        {recommendedRepository ? <>
          <div className="hei-repository-recommendation-layout">
            <div className="hei-repository-recommendation-evidence">
              <Signal label="Azure DevOps Project" value={projectName || 'Current project'} />
              <Signal label="Branch" value={recommendedRepository.defaultBranch || 'Not configured'} />
              <Signal label="Snapshot" value={recommendedRepository.snapshotVersion || 'Unavailable'} />
              <Signal label="Engineering Memory" value={review.engineeringMemory.status || 'Not available'} />
            </div>
            <div className="hei-repository-reason">
              <span>Why HEI selected it</span>
              <p>{suggestion?.reason}</p>
              <strong>Matching repository metadata</strong>
              {(recommendedRepository.evidence || []).length ? <ul>{(recommendedRepository.evidence || []).map((item) => <li key={item}>{item}</li>)}</ul> : <p>No matching repository metadata was available.</p>}
            </div>
          </div>
          <div className="hei-repository-recommendation-actions">
            <button className="planner-button secondary" type="button" disabled={busy || suggestion?.source === 'ManualOverride'} onClick={() => onOverrideRepository(recommendedRepository.repositoryId)}>{suggestion?.source === 'ManualOverride' ? 'Recommendation Accepted' : 'Accept Recommendation'}</button>
            {repositoryOptions.length > 1 ? <details className="hei-repository-override"><summary>Override Repository</summary><div>
              <label><span>Search Repository</span><input value={repositorySearch} onChange={(event) => setRepositorySearch(event.target.value)} placeholder="Search registered repositories" /></label>
              <label><span>Repository</span><select value={overrideRepositoryId} disabled={busy} onChange={(event) => setOverrideRepositoryId(event.target.value)}>{visibleRepositories.map((repository) => <option key={repository.repositoryId} value={repository.repositoryId}>{repository.name || 'Unnamed repository'} · {Math.round((repository.confidence || 0) * 100)}%</option>)}</select></label>
              <button className="planner-button secondary" type="button" disabled={busy || !overrideRepositoryId || overrideRepositoryId === recommendedRepository.repositoryId} onClick={() => onOverrideRepository(overrideRepositoryId)}>Apply Override</button>
            </div></details> : null}
          </div>
          {(suggestion?.alternativeRepositories || []).length ? <small>Alternatives: {(suggestion?.alternativeRepositories || []).map((repository) => `${repository.name || 'Unnamed repository'} (${Math.round((repository.confidence || 0) * 100)}%)`).join(', ')}</small> : null}
        </> : null}
      </section>
      <details className="hei-requirement-advanced"><summary>Engineering analysis details</summary><RequirementAnalysisViewBoundary key={analysis.analysisDocument?.documentId || analysis.analysisId} analysis={analysis}>
        <RequirementAnalysisDocumentView analysis={analysis} />
      </RequirementAnalysisViewBoundary></details>
      <AcceptanceCriteriaCard analysis={analysis} busy={busy} onEditRequirement={onEdit} onGenerate={onSuggestAcceptanceCriteria} onApprove={onApproveAcceptanceCriteria} onDiscard={onDiscardAcceptanceCriteria} onSkip={onSkipAcceptanceCriteria} onUpdate={onUpdateAcceptanceCriteria} />
      <details className="hei-requirement-advanced" open={blocked}><summary>Quality findings ({qualityFindingCount})</summary><QualityFindings result={analysis} onEdit={onEdit} onReanalyze={onReanalyze} onGenerateAcceptanceCriteria={onSuggestAcceptanceCriteria} /></details>
      </div>
      <HEIInsights analysis={analysis} memoryStatus={review.engineeringMemory.status} busy={busy} blocked={blocked || acceptancePending} onEdit={onEdit} onGenerateAcceptanceCriteria={onSuggestAcceptanceCriteria} onContinue={onContinue} />
      </div>
      <div className="hei-requirement-sticky-actions">
        <div className="hei-requirement-sticky-status"><Signal label="Requirement Status" value={readinessLabel(analysis.planningReadiness.status)} /><Signal label="Confidence" value={`${Math.round(analysis.confidence * 100)}%`} /><Signal label="Repository" value={recommendedRepository?.name || 'Not selected'} /></div>
        <div className="hei-requirement-actions">
          <button className="planner-button secondary" type="button" disabled={busy} onClick={onEdit}>Edit Requirement</button>
          <button className="planner-button secondary" type="button" disabled={busy} onClick={onReanalyze}>Re-analyze</button>
          <button className="planner-button primary" type="button" disabled={busy || blocked || acceptancePending} onClick={onContinue}>{busy ? 'Preparing Plan...' : needsReview ? 'Accept & Continue to Plan' : 'Continue to Plan'}</button>
        </div>
      </div>
      {blocked ? <p className="hei-requirement-review-blocker">Resolve blocking findings with Edit before continuing to Planning.</p> : acceptancePending ? <p className="hei-requirement-review-guidance">Approve, edit, or discard the generated Acceptance Criteria before Planning approval.</p> : needsReview ? <p className="hei-requirement-review-guidance">Recommendations are visible and Planning may continue with the reviewed interpretation.</p> : null}
      <small>Requirement Context {analysis.contextVersion} · Review {analysis.reviewStatus}</small>
    </>}
  </section>;
}

class RequirementAnalysisViewBoundary extends React.Component<{
  analysis: RequirementAnalysisResult;
  children: React.ReactNode;
}, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error) {
    console.error('Requirement Analysis V2 view could not be rendered.', error);
  }

  render() {
    if (!this.state.failed) return this.props.children;
    const analysis = this.props.analysis;
    return <section className="hei-analysis-section" role="status">
      <header><h4>Requirement Analysis</h4><Status value="Fallback View" /></header>
      <div>
        <p>{analysis.requirementSummary || 'The requirement was analyzed, but the enhanced evidence view could not be displayed.'}</p>
        <ContextTags title="Functional Requirements" values={analysis.functionalRequirements || []} empty="No functional requirements were returned." />
        <p className="hei-analysis-empty">Re-analyze to refresh the enhanced view. The analysis result remains available and the workspace can continue.</p>
      </div>
    </section>;
  }
}

function RequirementAnalysisDocumentView({ analysis }: { analysis: RequirementAnalysisResult }) {
  const document = analysis.analysisDocument;
  if (!document || document.schemaVersion !== 'hei-requirement-analysis-v2') return <RequirementIntelligenceTrace analysis={analysis} />;
  const discovery = analysis.engineeringDiscovery?.report;
  const sectionSources = document.sectionSources || {};
  const evidence = document.evidence || [];
  const repositoryFindings = document.repositoryFindings || [];
  const markdownFindings = document.markdownFindings || [];
  const azureDevOpsFindings = document.azureDevOpsFindings || [];
  const reusableComponents = document.reusableComponents || [];
  const readiness = document.planningReadiness || analysis.planningReadiness;
  const dimensions = readiness.dimensions || {};
  const validationWarnings = document.validation?.warnings || [];
  const confidence = document.confidence || { score: Math.round(analysis.confidence * 100), level: 'Needs Review', reason: '' };
  const businessSource = sectionSources.businessGoal;
  const actorValues = [document.primaryActor, ...(document.secondaryActors || [])].filter(Boolean);
  const statements = document.statementGovernance || [];
  const discoveryFindings = (discovery?.whatIFound || []).flatMap((group) =>
    (group.findings || []).map((item) => `${item.title} · ${group.source}`),
  );
  return <section className="hei-analysis-document" aria-label="Canonical Requirement Analysis">
    <header className="hei-analysis-document-header">
      <div><span>Requirement Analysis V2</span><h3>{document.title}</h3><p>{document.executiveSummary || 'An executive summary could not be established from the current requirement.'}</p></div>
      <div><Status value={`${confidence.level} · ${confidence.score}%`} /><small>{document.schemaVersion}</small></div>
    </header>

    <AnalysisDocumentSection title="Business Understanding" source={businessSource}>
      <div className="hei-analysis-understanding-grid">
        <AnalysisValue label="Business Goal" value={document.businessGoal} empty="A distinct business outcome was not provided or supported." statement={findGovernedStatement(statements, 'Business Goal', document.businessGoal)} />
        <AnalysisValue label="Problem Statement" value={document.problemStatement} empty="The current problem could not be stated without adding scope." statement={findGovernedStatement(statements, 'Problem Statement', document.problemStatement)} />
        <AnalysisValue label="Business Value" value={document.businessValue} empty="Measurable business value requires clarification." statement={findGovernedStatement(statements, 'Business Value', document.businessValue)} />
        <AnalysisValue label="Primary Actor" value={document.primaryActor} empty="No primary actor could be identified." statement={findGovernedStatement(statements, 'Primary Actor', document.primaryActor)} />
      </div>
      <GovernedStatements title="Actors" statements={statements.filter((item) => item.category === 'Primary Actor' || item.category === 'Secondary Actor')} fallback={actorValues} empty="No actors were identifiable from the requirement." />
      <GovernedStatements title="Capabilities" statements={statements.filter((item) => item.category === 'Capability')} fallback={document.capabilities || []} empty="No capability could be identified without expanding the requirement." />
      <GovernedStatements title="Functional Requirements" statements={statements.filter((item) => item.category === 'Functional Requirement' && item.classification !== 'AI_SUGGESTION')} fallback={document.functionalRequirements || []} empty="No governed functional behavior was identified." />
      <GovernedStatements title="Non-Functional Requirements and Candidates" statements={statements.filter((item) => item.category === 'Non-Functional Requirement' || item.category === 'Candidate Non-Functional Requirement')} fallback={document.candidateNonFunctionalRequirements || []} empty="No quality requirements or candidates were identified." />
      <GovernedStatements title="Suggested Enhancements" statements={document.suggestedEnhancements || []} fallback={[]} empty="No unsupported enhancements were proposed." />
      <ContextTags title="Business Rules" values={document.businessRules || []} empty="No evidenced business rules were found." />
      <ContextTags title="Constraints" values={document.constraints || []} empty="No evidenced constraints were found." />
      <ContextTags title="Dependencies" values={document.dependencies || []} empty="No evidenced dependencies were found." />
    </AnalysisDocumentSection>

    <AnalysisDocumentSection title="Engineering Discovery" source={{ origin: 'Engineering Discovery', evidenceReferences: evidence.map((item) => item.sourceReference) }}>
      <div className="hei-analysis-discovery-summary">
        <AnalysisValue label="Discovery Status" value={discoveryStatusLabel(discovery?.status)} empty="Discovery Pending" />
        <AnalysisValue label="Discovery Confidence" value={discovery?.confidence ? `${discovery.confidence.score}%` : ''} empty="Discovery Pending" />
        <AnalysisValue label="Evidence Found" value={String(evidence.length)} empty="No relevant evidence found" />
        <AnalysisValue label="Conflicts" value={String(discovery?.conflicts?.length || 0)} empty="No conflicts detected" />
      </div>
      <ContextTags title="What HEI Found" values={discoveryFindings} empty={discovery?.status === 'DiscoveryPending' ? 'Discovery Pending' : 'No relevant evidence found'} />
      <ContextTags title="Engineering Insights" values={document.engineeringInsights || []} empty="No additional engineering insight was supported by current evidence." />
      <DiscoveryEvidenceGroup title="Reusable Components" values={reusableComponents} />
    </AnalysisDocumentSection>

    <AnalysisDocumentSection title="Evidence" source={{ origin: 'Verified Sources', evidenceReferences: evidence.map((item) => item.sourceReference) }}>
      <DiscoveryEvidenceGroup title="Repository Evidence" values={repositoryFindings} />
      <DiscoveryEvidenceGroup title="Markdown Evidence" values={markdownFindings} />
      <DiscoveryEvidenceGroup title="Azure DevOps Evidence" values={azureDevOpsFindings} />
      {!evidence.length ? <p className="hei-analysis-empty">No relevant evidence found. HEI has not invented repository or project facts.</p> : null}
    </AnalysisDocumentSection>

    <AnalysisDocumentSection title="Repository Impact" source={sectionSources.repositoryImpact}>
      <div className="hei-analysis-impact-grid">
        <ContextTags title="Affected Modules" values={document.affectedModules || []} empty="No affected module was supported by repository evidence." />
        <ContextTags title="Affected Services" values={document.affectedServices || []} empty="No affected service was supported by repository evidence." />
        <ContextTags title="Affected APIs" values={document.affectedApis || []} empty="No affected API was supported by repository evidence." />
        <ContextTags title="Affected Screens" values={document.affectedScreens || []} empty="No affected screen was supported by repository evidence." />
      </div>
    </AnalysisDocumentSection>

    <div className="hei-analysis-review-grid">
      <AnalysisDocumentSection title="Risks" source={sectionSources.risks} compact>
        <ContextTags title="Inferred Risks" values={document.risks || []} empty="No material risk was inferred from current intent and evidence." />
        <ContextTags title="Assumptions" values={document.assumptions || []} empty="No assumptions were introduced." />
      </AnalysisDocumentSection>
      <AnalysisDocumentSection title="Questions" source={sectionSources.openQuestions} compact>
        <ContextTags title="Open Questions" values={document.openQuestions || []} empty="The current evidence resolved all identified questions." />
      </AnalysisDocumentSection>
    </div>

    <AnalysisDocumentSection title="Planning Readiness" source={{ origin: 'Requirement Validation', evidenceReferences: evidence.map((item) => item.sourceReference) }}>
      <div className="hei-analysis-readiness">
        <div><Status value={readinessLabel(readiness.status)} /><p>{readiness.explanation || 'Planning readiness was calculated from requirement quality and available engineering evidence.'}</p><small>Supporting score: {readiness.score}%</small></div>
        <div>{Object.entries(dimensions).map(([key, value]) => <Signal key={key} label={humanizeAnalysisKey(key)} value={`${value}%`} />)}</div>
      </div>
      {(readiness.strengths || []).length ? <ContextTags title="Strengths" values={readiness.strengths || []} empty="No strengths identified." /> : null}
      {(readiness.needsAttention || []).length ? <ContextTags title="Needs Attention" values={readiness.needsAttention || []} empty="Nothing requires attention." /> : null}
      {(readiness.blockers || []).length ? <ContextTags title="Blockers" values={readiness.blockers || []} empty="No blockers." /> : null}
      {(readiness.warnings || []).length ? <ContextTags title="Recommendations" values={readiness.warnings || []} empty="No recommendations." /> : null}
      {validationWarnings.length ? <ContextTags title="Validation Notes" values={validationWarnings} empty="Validation passed." /> : null}
    </AnalysisDocumentSection>
  </section>;
}

function AnalysisDocumentSection({ title, source, compact = false, children }: { title: string; source?: AnalysisSectionSource; compact?: boolean; children: React.ReactNode }) {
  return <section className={`hei-analysis-section${compact ? ' compact' : ''}`}>
    <header><h4>{title}</h4><AnalysisSource value={source} /></header>
    <div>{children}</div>
  </section>;
}

function AnalysisSource({ value }: { value?: AnalysisSectionSource }) {
  if (!value) return <span className="hei-analysis-source muted">Source not available</span>;
  const evidenceCount = value.evidenceReferences?.length || 0;
  return <span className="hei-analysis-source" title={value.evidenceReferences?.join('\n')}>{value.origin}{evidenceCount ? ` · ${evidenceCount} evidence` : ''}</span>;
}

function AnalysisValue({ label, value, empty, statement }: { label: string; value: string; empty: string; statement?: GovernedStatement }) {
  return <article className={value ? '' : 'empty'} title={statement?.why || ''}><span>{label}</span><p>{value || empty}</p>{statement ? <StatementMeta statement={statement} /> : null}</article>;
}

function GovernedStatements({ title, statements, fallback, empty }: { title: string; statements: GovernedStatement[]; fallback: string[]; empty: string }) {
  if (!statements.length) return <ContextTags title={title} values={fallback} empty={empty} />;
  return <div className="hei-governed-statements"><strong>{title}</strong><div>{statements.map((statement) => <article key={statement.id} title={statement.why}><p>{statement.text}</p><StatementMeta statement={statement} /></article>)}</div></div>;
}

function StatementMeta({ statement }: { statement: GovernedStatement }) {
  const label = statement.classification.replace('_', ' ');
  return <small className="hei-statement-meta"><span className={`hei-statement-badge ${statement.classification.toLowerCase()}`}>{label}</span><span>{Math.round(statement.confidence * 100)}%</span>{statement.evidenceReferences?.length ? <span title={statement.evidenceReferences.join('\n')}>{statement.evidenceReferences.length} evidence</span> : null}{statement.requiresConfirmation ? <span>Review required</span> : null}</small>;
}

function findGovernedStatement(statements: GovernedStatement[], category: string, text: string) {
  return statements.find((statement) => statement.category === category && statement.text === text)
    || statements.find((statement) => statement.category === category);
}

function humanizeAnalysisKey(value: string) {
  return value.replace(/([A-Z])/g, ' $1').replace(/^./, (character) => character.toUpperCase());
}

function RequirementList({ icon, title, items, origin, empty, action, onAction }: { icon: string; title: string; items: string[]; origin?: ArtifactOrigin; empty: string; action: string; onAction: () => void }) {
  return <section className={items.length ? '' : 'empty'}><header><span aria-hidden="true">{icon}</span><h3>{title}</h3>{origin ? <OriginBadge value={origin} /> : <small>{items.length}</small>}</header>{items.length ? <ul>{items.map((item, index) => <li key={`${index}-${item}`}>{item}</li>)}</ul> : <div className="hei-requirement-empty"><strong>{empty}</strong><p>Add information to improve planning quality.</p><button className="planner-button secondary" type="button" onClick={onAction}>{action}</button></div>}</section>;
}

function OriginBadge({ value }: { value: ArtifactOrigin }) {
  return <span className={`hei-origin-badge ${value.toLowerCase().replace(/\s+/g, '-')}`}>{value}</span>;
}

function readinessLabel(value: RequirementAnalysisResult['planningReadiness']['status']) {
  if (value === 'ReadyWithRecommendations') return 'Ready with Recommendations';
  if (value === 'NeedsUserInput') return 'Needs User Input';
  return value;
}

function reasoningFallbackLabel(warnings: string[]) {
  const value = warnings.join(' ').toLowerCase();
  if (value.includes('budget') || value.includes('required_sections_exceed_budget')) return 'Deterministic fallback · prompt budget guard';
  if (value.includes('parse_error') || value.includes('missing_field') || value.includes('missing_valid_evidence')) return 'Deterministic fallback · provider response rejected';
  if (value.includes('provider_error') || value.includes('no configured reasoning provider')) return 'Deterministic fallback · provider unavailable';
  return warnings.length ? 'Deterministic fallback · see diagnostics' : 'Deterministic baseline';
}

function requirementAnalysisModeLabel(
  analysis: RequirementAnalysisResult,
  refinement?: RequirementRefinementResult,
) {
  const analysisLabel = analysis.aiAnalysis?.reasoningMode === 'AI'
    ? `${analysis.aiAnalysis.provider}${analysis.aiAnalysis.model ? ` · ${analysis.aiAnalysis.model}` : ''}`
    : reasoningFallbackLabel(analysis.aiAnalysis?.warnings || []);
  if (!refinement) return analysisLabel;
  if (refinement.provider === 'Deterministic' && analysis.aiAnalysis?.reasoningMode === 'AI') {
    return `Mixed · ${analysisLabel} analysis · deterministic refinement`;
  }
  return analysisLabel;
}

function AcceptanceCriteriaCard({ analysis, busy, onEditRequirement, onGenerate, onApprove, onDiscard, onSkip, onUpdate }: {
  analysis: RequirementAnalysisResult;
  busy: boolean;
  onEditRequirement: () => void;
  onGenerate: () => void;
  onApprove: () => void;
  onDiscard: () => void;
  onSkip: () => void;
  onUpdate: (criteria: AcceptanceCriterionSuggestion[]) => void;
}) {
  const state = analysis.acceptanceCriteriaState || { state: 'Missing', origin: '', status: 'Missing', description: '' };
  const [editing, setEditing] = useState(false);
  const [activeView, setActiveView] = useState<'criteria' | 'missing' | 'assumptions' | 'coverage' | 'evidence'>('criteria');
  const [drafts, setDrafts] = useState<AcceptanceCriterionSuggestion[]>(analysis.acceptanceCriteriaSuggestions || []);
  const suggestions = analysis.acceptanceCriteriaSuggestions || [];
  const sourceRecords = analysis.acceptanceCriteriaRecords || [];
  const missingInformation = analysis.missingInformation || [];
  const assumptions = analysis.aiAssumptions || [];
  const coverage = analysis.acceptanceCoverage;
  const evidence = analysis.acceptanceEvidence || [];
  const sourceProvided = state.state === 'SourceProvided';
  const aiSuggested = state.state === 'AISuggested';
  const approvedSuggestions = aiSuggested && state.status === 'Approved';
  const visibleSuggestions = editing ? drafts : suggestions;
  const suggestionSignature = suggestions.map((item) => `${item.criterionId}:${item.text}`).join('|');

  useEffect(() => {
    setDrafts(suggestions.map((item) => ({ ...item })));
    setEditing(false);
    if (suggestions.length) setActiveView('criteria');
  }, [suggestionSignature]);

  function beginEdit() {
    setDrafts(suggestions.map((item) => ({ ...item })));
    setEditing(true);
  }

  function saveEdits() {
    onUpdate(drafts);
    setEditing(false);
  }

  return <section className={`hei-acceptance-card ${state.state.toLowerCase()}`} aria-label="Acceptance Criteria">
    <header><span aria-hidden="true">AC</span><h3>Acceptance Criteria</h3>{state.origin ? <OriginBadge value={state.origin as ArtifactOrigin} /> : <Status value="Missing" />}</header>
    <nav className="hei-acceptance-tabs" aria-label="Acceptance Criteria intelligence">
      {([
        ['criteria', 'Acceptance Criteria'],
        ['missing', `Missing Information (${missingInformation.length})`],
        ['assumptions', `AI Assumptions (${assumptions.length})`],
        ['coverage', `Coverage (${coverage?.coveragePercent || 0}%)`],
        ['evidence', `Evidence (${evidence.length})`],
      ] as const).map(([id, label]) => <button key={id} type="button" className={activeView === id ? 'active' : ''} onClick={() => setActiveView(id)}>{label}</button>)}
    </nav>
    {activeView === 'criteria' && sourceProvided ? <>
      <p className="hei-acceptance-description">Acceptance Criteria were found in the source requirement.</p>
      <div className="hei-acceptance-records">{sourceRecords.length ? sourceRecords.map((criterion) => <CriterionRecord key={criterion.criterionId} criterion={criterion} />) : analysis.acceptanceCriteria.map((criterion, index) => <article key={`${index}-${criterion}`}><p>{criterion}</p></article>)}</div>
      <footer><button className="planner-button secondary" type="button" disabled={busy} onClick={onEditRequirement}>Edit Requirement</button></footer>
    </> : activeView === 'criteria' && aiSuggested ? <>
      <div className="hei-acceptance-callout"><strong>{approvedSuggestions ? 'Approved for Planning' : 'Review before approval'}</strong><p>{state.description}</p></div>
      <div className="hei-acceptance-suggestions">
        {visibleSuggestions.map((criterion, index) => editing
          ? <label key={criterion.criterionId}><span>Criterion {index + 1}</span><textarea rows={5} value={criterion.text} onChange={(event) => setDrafts((current) => current.map((item) => item.criterionId === criterion.criterionId ? { ...item, text: event.target.value, origin: 'User Edited' } : item))} /></label>
          : <CriterionRecord key={criterion.criterionId} criterion={criterion} />)}
      </div>
      <footer>
        {editing ? <>
          <button className="planner-button primary" type="button" disabled={busy || drafts.some((item) => !item.text.trim())} onClick={saveEdits}>Save Suggestions</button>
          <button className="planner-button secondary" type="button" disabled={busy} onClick={() => setEditing(false)}>Cancel Edit</button>
        </> : <>
          {!approvedSuggestions ? <button className="planner-button primary" type="button" disabled={busy} onClick={onApprove}>Approve Suggestions</button> : null}
          <button className="planner-button secondary" type="button" disabled={busy} onClick={beginEdit}>Edit</button>
          <button className="planner-button secondary" type="button" disabled={busy} onClick={onGenerate}>Regenerate</button>
          <button className="planner-button secondary" type="button" disabled={busy} onClick={onDiscard}>Discard</button>
        </>}
      </footer>
    </> : activeView === 'criteria' ? <div className="hei-requirement-empty hei-acceptance-missing">
      <strong>No Acceptance Criteria were found in the requirement.</strong>
      <p>{state.description || 'This is not an AI error. Planning can continue, but testability and implementation quality may be reduced.'}</p>
      {analysis.acceptanceDiagnostics?.generationMode ? <small>
        Last generation: {analysis.acceptanceDiagnostics.generationMode === 'AI'
          ? `${analysis.acceptanceDiagnostics.provider || 'Reasoning AI'}${analysis.acceptanceDiagnostics.model ? ` · ${analysis.acceptanceDiagnostics.model}` : ''}`
          : 'Deterministic fallback'}{analysis.acceptanceDiagnostics.generationStatus === 'InsufficientEvidence' ? ' · More requirement detail is needed' : ''}
      </small> : null}
      <div>
        <button className="planner-button primary" type="button" disabled={busy} onClick={onGenerate}>{busy ? 'Generating with Reasoning AI...' : 'Generate Suggested Acceptance Criteria'}</button>
        <button className="planner-button secondary" type="button" disabled={busy} onClick={onSkip}>Skip</button>
        <button className="planner-button secondary" type="button" disabled={busy} onClick={onEditRequirement}>Edit Requirement</button>
      </div>
    </div> : null}
    {activeView === 'missing' ? <div className="hei-acceptance-intelligence-list">{missingInformation.length ? missingInformation.map((item) => <article key={item.field}><div><strong>{item.field}</strong><Status value={item.blocksGeneration ? 'Blocking' : item.status} /></div><p>{item.reason}</p></article>) : <p>No requirement information gaps were detected.</p>}</div> : null}
    {activeView === 'assumptions' ? <div className="hei-acceptance-intelligence-list">{assumptions.length ? assumptions.map((item) => <article key={item.assumptionId}><div><strong>{item.text}</strong><Status value={item.status} /></div><p>{item.reason}</p><small>{Math.round(item.confidence * 100)}% confidence · {item.origin}</small></article>) : <p>No AI assumptions were introduced.</p>}</div> : null}
    {activeView === 'coverage' ? <div className="hei-acceptance-coverage"><header><strong>{coverage?.coveragePercent || 0}% functional coverage</strong><Status value={coverage?.status || 'Incomplete'} /></header>{coverage?.areas?.length ? <div className="hei-acceptance-coverage-areas">{coverage.areas.map((item) => <article key={item.area}><div><strong>{item.area}</strong><Status value={item.status} /></div><small>{item.count} identified</small></article>)}</div> : null}{coverage?.mappings?.length ? coverage.mappings.map((item) => <article key={item.functionalRequirementId}><div><strong>{item.functionalRequirementId.toUpperCase()}</strong><Status value={item.status} /></div><p>{item.functionalRequirement}</p><small>{item.criterionIds.length ? `${item.criterionIds.length} mapped criterion` : 'No mapped criterion'}</small></article>) : <p>No functional requirements are available for coverage validation.</p>}</div> : null}
    {activeView === 'evidence' ? <div className="hei-acceptance-evidence">{evidence.length ? evidence.map((item, index) => <article key={`${index}-${item.matchedPhrase}`}><strong>{item.matchedPhrase}</strong><blockquote>{item.requirementSentence}</blockquote><small>{item.source} · {Math.round(item.confidence * 100)}% confidence</small></article>) : <p>No approved or suggested criterion evidence is available.</p>}</div> : null}
  </section>;
}

function CriterionRecord({ criterion }: { criterion: AcceptanceCriterionSuggestion }) {
  return <article className="hei-criterion-record">
    <header><div><strong>{criterion.title || `Criterion ${criterion.order}`}</strong><small>{criterion.type || 'Functional'} · {criterion.requirementCoverage || 'Mapped'}</small></div><div><OriginBadge value={criterion.origin} /><Status value={criterion.status} /></div></header>
    <pre>{criterion.text}</pre>
    {criterion.mappedFunctionalRequirement ? <p><span>Requirement</span>{criterion.mappedFunctionalRequirement}</p> : null}
    {criterion.evidence?.length ? <details><summary>Evidence · {Math.round((criterion.confidence || 0) * 100)}% confidence</summary>{criterion.evidence.map((item, index) => <blockquote key={`${index}-${item.matchedPhrase}`}><strong>{item.matchedPhrase}</strong><span>{item.requirementSentence}</span></blockquote>)}</details> : null}
  </article>;
}

function RequirementIntelligenceTrace({ analysis }: { analysis: RequirementAnalysisResult }) {
  const intent = analysis.requirementIntent;
  const discovery = analysis.engineeringDiscovery;
  const synthesis = analysis.evidenceSynthesis;
  if (!intent && !discovery && !synthesis) return null;
  const markdown = discovery?.markdown?.selected || [];
  const workItems = discovery?.azureDevOps?.workItems || [];
  const memory = discovery?.memory?.matches || [];
  const report = discovery?.report;
  const repositoryItems = [
    ...(discovery?.repository?.modules || []),
    ...(discovery?.repository?.services || []),
    ...(discovery?.repository?.apis || []),
  ];
  return <section className="hei-requirement-intelligence-trace" aria-label="AI and engineering analysis">
    <header>
      <div><span>AI-Driven Analysis</span><h3>Understanding and engineering evidence</h3><p>AI interpretation is separated from verified engineering discovery.</p></div>
      <Status value={analysis.analysisMode === 'AI' ? `${analysis.analysisLineage?.provider || 'AI'} analysis` : 'Deterministic fallback'} />
    </header>
    <div>
      <article>
        <span>AI Understanding</span>
        <h4>{intent?.intentSummary || analysis.requirementSummary}</h4>
        <p>{intent?.businessGoal || 'No distinct business goal was inferred.'}</p>
        <ContextTags title="Capabilities and concepts" values={[...(intent?.capabilities || []), ...(intent?.concepts || [])]} empty="No additional intent hints were produced." />
        <small>{Math.round((intent?.confidence || 0) * 100)}% interpretation confidence · Not repository fact</small>
      </article>
      <article>
        <span>Engineering Discovery</span>
        <h4>{report?.summary || discoveryEmptyLabel(discovery?.repository?.mode)}</h4>
        {report ? <p>{report.confidence.score}% discovery confidence · {report.confidence.evidenceCount} traceable evidence item{report.confidence.evidenceCount === 1 ? '' : 's'}</p> : null}
        <div className="hei-requirement-discovery-counts">
          <Signal label="Repository evidence" value={String(report?.repositoryEvidence.length ?? repositoryItems.length)} />
          <Signal label="Relevant documents" value={String(report?.relevantDocumentation.length ?? markdown.length)} />
          <Signal label="Similar work" value={String(report?.azureDevOpsEvidence.length ?? workItems.length)} />
          <Signal label="Reusable knowledge" value={String(report?.reusableComponents.length ?? memory.length)} />
        </div>
        <ContextTags title="What HEI found" values={report?.whatIFound.filter((item) => item.count > 0).map((item) => item.summary) || repositoryItems.slice(0, 10)} empty={report?.status === 'DiscoveryPending' ? 'Discovery Pending' : 'No relevant evidence found'} />
      </article>
    </div>
    <details>
      <summary>Evidence, missing information, and lineage</summary>
      <div className="hei-requirement-trace-details">
        {report ? <>
          <ContextTags title="Source status" values={report.sourceStatus.map((item) => `${item.source}: ${discoveryStatusLabel(item.status)}. ${item.message}`)} empty="Discovery Pending" />
          <DiscoveryEvidenceGroup title="Repository evidence" values={report.repositoryEvidence} />
          <DiscoveryEvidenceGroup title="Relevant documentation" values={report.relevantDocumentation} />
          <DiscoveryEvidenceGroup title="Similar features and ADO work" values={report.azureDevOpsEvidence} />
          <DiscoveryEvidenceGroup title="Reusable components" values={report.reusableComponents} />
          <DiscoveryEvidenceGroup title="Architecture evidence" values={report.architectureEvidence} />
          <DiscoveryEvidenceGroup title="Project knowledge and memory" values={[...report.projectIntelligenceEvidence, ...report.knowledgeEvidence, ...report.engineeringMemoryEvidence]} />
          {report.conflicts.length ? <ContextTags title="Conflicts" values={report.conflicts.map((item) => `${item.path ? `${item.path}: ` : ''}${item.reason || 'Conflicting engineering evidence requires review.'}`)} empty="No evidence conflicts detected." /> : null}
          {report.unknowns.length ? <ContextTags title="Unknowns" values={report.unknowns.map((item) => `${item.area}: ${item.reason}`)} empty="No unresolved information identified." /> : null}
        </> : <>
          <ContextTags title="Repository findings" values={synthesis?.repositoryFindings || []} empty="No relevant evidence found." />
          <ContextTags title="Markdown evidence" values={markdown.map((item) => `${item.path} · ${item.heading}`)} empty="No relevant evidence found." />
          <ContextTags title="Open or missing information" values={[...(analysis.openQuestions || []), ...(synthesis?.missingInformation || [])]} empty="No unresolved information identified." />
          <ContextTags title="Engineering insights" values={synthesis?.engineeringInsights || []} empty="No relevant evidence found." />
        </>}
        <p><strong>Context:</strong> {analysis.analysisLineage?.contextVersion || 'Not available'} · <strong>Repository revision:</strong> {analysis.analysisLineage?.repositoryRevision || 'Not available'} · <strong>Knowledge:</strong> {analysis.analysisLineage?.knowledgeVersion || 'Not available'}</p>
      </div>
    </details>
  </section>;
}

function DiscoveryEvidenceGroup({ title, values = [] }: { title: string; values?: DiscoveryEvidence[] }) {
  if (!values.length) return null;
  return <ContextTags
    title={title}
    values={values.map((item) => `${item.title} · ${item.reason} [${item.sourceReference}]`)}
    empty="No relevant evidence found."
  />;
}

function discoveryStatusLabel(value?: string) {
  if (value === 'DiscoveryPending') return 'Discovery Pending';
  if (value === 'NoRelevantEvidence') return 'No relevant evidence found';
  return value || 'Discovery Pending';
}

function discoveryEmptyLabel(repositoryMode?: string) {
  return repositoryMode && repositoryMode !== 'Unavailable'
    ? 'No relevant evidence found'
    : 'Discovery Pending';
}

function RequirementHealth({ analysis, ingestion }: { analysis: RequirementAnalysisResult; ingestion: IngestionResult }) {
  const repositoryConfidence = Math.round(Number(analysis.repositorySuggestion?.confidence || 0) * 100);
  const documentQuality = ingestion.sourceType === 'PasteRequirement' ? 'Direct Input' : analysis.reviewContext.documentType && analysis.reviewContext.documentType !== 'Unknown' ? 'Good' : 'Needs Review';
  const metrics = [
    { label: 'Overall Confidence', value: `${Math.round(analysis.confidence * 100)}%`, description: 'Confidence in extracted requirement intent.' },
    { label: 'Planning Quality', value: `${analysis.requirementQualityScore}%`, description: 'Completeness and clarity for planning.' },
    { label: 'Repository Confidence', value: repositoryConfidence ? `${repositoryConfidence}%` : 'Not detected', description: 'Strength of repository alignment.' },
    { label: 'Readiness', value: readinessLabel(analysis.planningReadiness.status), description: 'Current planning transition state.' },
    { label: 'Document Quality', value: documentQuality, description: ingestion.sourceType === 'PasteRequirement' ? 'Reviewed from direct requirement input.' : 'Source extraction quality.' },
  ];
  return <section className="hei-requirement-health" aria-label="Requirement Health"><header><div><span>Requirement Health</span><h3>Planning readiness at a glance</h3></div><Status value={readinessLabel(analysis.planningReadiness.status)} /></header><div>{metrics.map((metric) => <article key={metric.label} className={statusTone(metric.value)}><span>{metric.label}</span><strong>{metric.value}</strong><p>{metric.description}</p></article>)}</div></section>;
}

function QualityFindings({ result, onEdit, onReanalyze, onGenerateAcceptanceCriteria }: { result: RequirementAnalysisResult; onEdit: () => void; onReanalyze: () => void; onGenerateAcceptanceCriteria: () => void }) {
  const missingAcceptanceFindings = result.acceptanceCriteriaSuggestions.length
    ? []
    : result.missingAcceptanceCriteria;
  const issues: Array<AnalysisFinding & { title: string; severity: string; impact: string; aiAssistance?: string }> = [
    ...missingAcceptanceFindings.map((finding) => ({ ...finding, title: 'Acceptance Criteria Missing', severity: 'Medium', impact: 'Generated Stories may not contain verifiable completion conditions.', aiAssistance: 'HEI can generate editable Given/When/Then suggestions for review.' })),
    ...result.ambiguousRequirements.map((finding) => ({ ...finding, title: 'Ambiguous Requirement', severity: 'Medium', impact: 'Multiple interpretations may produce inconsistent planning artifacts.' })),
    ...result.conflictingRequirements.map((finding) => ({ ...finding, title: 'Conflicting Requirement', severity: 'Critical', impact: 'Planning is blocked until the conflicting intent is resolved.' })),
    ...result.duplicateRequirements.map((finding) => ({ ...finding, title: 'Duplicate Requirement', severity: 'Low', impact: 'Duplicate scope can create repeated stories and estimates.' })),
  ];
  return <section className="hei-quality-findings" aria-label="Quality Findings"><header><div><span>Quality Review</span><h3>Quality Findings</h3><p>{issues.length ? `${issues.length} issue${issues.length === 1 ? '' : 's'} include transparent recommendations.` : 'No requirement quality issues detected.'}</p></div><Status value={issues.length ? 'Recommendations Available' : 'Clear'} /></header>{issues.length ? <div>{issues.map((issue, index) => <article key={`${issue.title}-${index}`}><header><div><span>Issue</span><h4>{issue.title}</h4></div><Status value={`${issue.severity} Severity`} /></header><dl><div><dt>Description</dt><dd>{issue.text}</dd></div><div><dt>Business Impact</dt><dd>{issue.impact}</dd></div><div><dt>Recommended Action</dt><dd>{issue.reason}</dd></div>{issue.aiAssistance ? <div><dt>AI Assistance</dt><dd>{issue.aiAssistance}</dd></div> : null}</dl><footer>{issue.title === 'Acceptance Criteria Missing' ? <button className="planner-button primary" type="button" onClick={onGenerateAcceptanceCriteria}>Generate</button> : null}<button className="planner-button secondary" type="button" onClick={onEdit}>Edit Requirement</button><button className="planner-button secondary" type="button" onClick={onReanalyze}>Re-analyze</button></footer></article>)}</div> : null}</section>;
}

function EngineeringContext({ result }: { result: RequirementAnalysisResult }) {
  const metrics = [
    ['Business Goals', 'businessGoals', result.businessGoals.length], ['Actors', 'actors', result.actors.length],
    ['Business Rules', 'businessRules', result.businessRules.length], ['Dependencies', 'dependencies', result.dependencies.length],
    ['Constraints', 'constraints', result.constraints.length], ['Risks', 'risks', result.risks.length],
    ['Open Questions', 'openQuestions', result.openQuestions.length],
  ] as Array<[string, string, number]>;
  return <section className="hei-engineering-context" aria-label="Engineering Context"><header><span>Engineering Context</span><h3>Extracted planning signals</h3></header><div>{metrics.map(([label, key, value]) => <article key={label} className={value ? '' : 'empty'}><span>{label}</span><strong>{value}</strong>{value && result.fieldOrigins[key] ? <OriginBadge value={result.fieldOrigins[key]} /> : <small>Not provided</small>}</article>)}</div></section>;
}

function HEIInsights({ analysis, memoryStatus, busy, blocked, onEdit, onGenerateAcceptanceCriteria, onContinue }: {
  analysis: RequirementAnalysisResult;
  memoryStatus: string;
  busy: boolean;
  blocked: boolean;
  onEdit: () => void;
  onGenerateAcceptanceCriteria: () => void;
  onContinue: () => void;
}) {
  const repositoryConfidence = Math.round(Number(analysis.repositorySuggestion?.confidence || 0) * 100);
  const contextCount = analysis.functionalRequirements.length + analysis.nonFunctionalRequirements.length + analysis.acceptanceCriteria.length + analysis.dependencies.length + analysis.risks.length + analysis.openQuestions.length;
  const complexity = contextCount >= 12 ? 'High' : contextCount >= 5 ? 'Medium' : 'Low';
  const normalizedMemory = memoryStatus.toLowerCase();
  const memoryInsight = normalizedMemory.includes('no relevant') || normalizedMemory.includes('not available')
    ? 'No approved Engineering Memory match was found.'
    : normalizedMemory.includes('pending')
      ? 'Engineering Memory will be resolved after approval.'
      : 'Relevant implementation context is available in Engineering Memory.';
  const insights = [
    analysis.requirementQualityScore < 70 ? `Requirement quality is below target (${analysis.requirementQualityScore}%).` : `Requirement quality meets the planning target (${analysis.requirementQualityScore}%).`,
    analysis.acceptanceCriteria.length
      ? `${analysis.acceptanceCriteria.length} approved Acceptance Criteria are available.`
      : analysis.acceptanceCriteriaSuggestions.length
        ? `${analysis.acceptanceCriteriaSuggestions.length} generated Acceptance Criteria require review.`
        : 'The source did not provide Acceptance Criteria. This is not an AI error.',
    repositoryConfidence >= 75 ? `Repository confidence is high (${repositoryConfidence}%).` : repositoryConfidence ? `Repository confidence needs review (${repositoryConfidence}%).` : 'Repository confidence is not available.',
    memoryInsight,
    `Estimated planning complexity: ${complexity}.`,
  ];
  return <aside className="hei-insights" aria-label="HEI Insights"><details open><summary><span aria-hidden="true">💡</span><strong>HEI Insights</strong><small>{insights.length}</small></summary><div>
    <ul>{insights.map((insight) => <li key={insight}>{insight}</li>)}</ul>
    <section><span>Recommended Next Action</span><strong>{analysis.acceptanceCriteria.length ? 'Continue to Planning Context' : analysis.acceptanceCriteriaSuggestions.length ? 'Review suggested Acceptance Criteria' : 'Generate Acceptance Criteria suggestions'}</strong></section>
    <div className="hei-insights-actions">
      {!analysis.acceptanceCriteria.length && !analysis.acceptanceCriteriaSuggestions.length ? <button className="planner-button secondary" type="button" disabled={busy} onClick={onGenerateAcceptanceCriteria}>Generate Acceptance Criteria</button> : null}
      {!analysis.acceptanceCriteria.length ? <button className="planner-button secondary" type="button" disabled={busy} onClick={onEdit}>Edit Requirement</button> : null}
    </div>
  </div></details></aside>;
}

function RequirementAnalysisSummary({ result }: { result: RequirementAnalysisResult }) {
  const readiness = result.planningReadiness;
  const issues = [
    ...result.missingAcceptanceCriteria,
    ...result.ambiguousRequirements,
    ...result.conflictingRequirements,
    ...result.duplicateRequirements,
  ];
  return <details className="hei-requirement-analysis" aria-label="Requirement analysis">
    <summary><span>Analysis details</span><Status value={readinessLabel(readiness.status)} /></summary>
    <div className="hei-requirement-analysis-body"><header><div><span>Requirement Analysis</span><h3>{result.requirementSummary}</h3><p>Planning will receive the analyzed engineering requirement, not the raw source.</p></div></header>
    <div className="hei-requirement-signals"><Signal label="Quality" value={`${result.requirementQualityScore}%`} /><Signal label="Confidence" value={`${Math.round(result.confidence * 100)}%`} /><Signal label="Functional" value={String(result.functionalRequirements.length)} /><Signal label="Acceptance" value={String(result.acceptanceCriteria.length)} /></div>
    <details open={issues.length > 0}><summary>Planning Readiness</summary>
      {readiness.blockers.length || readiness.warnings.length ? <ul>{[...readiness.blockers, ...readiness.warnings].map((value) => <li key={value}>{value}</li>)}</ul> : <p>Requirement is ready for Planning.</p>}
    </details>
    <details open={issues.length > 0}><summary>Quality Findings ({issues.length})</summary>
      {issues.length ? <ul>{issues.map((finding, index) => <li key={`${index}-${finding.text}`}><strong>{finding.text}</strong><small> {finding.reason}</small></li>)}</ul> : <p>No ambiguity, conflict, duplicate, or acceptance gaps detected.</p>}
    </details>
    <details><summary>Analysis Evidence</summary><div className="hei-requirement-analysis-grid"><Signal label="Missing Criteria" value={String(result.missingAcceptanceCriteria.length)} /><Signal label="Ambiguities" value={String(result.ambiguousRequirements.length)} /><Signal label="Conflicts" value={String(result.conflictingRequirements.length)} /><Signal label="Duplicates" value={String(result.duplicateRequirements.length)} /></div></details>
    </div>
  </details>;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('The selected document could not be read.'));
    reader.onload = () => resolve(String(reader.result || '').split(',', 2)[1] || '');
    reader.readAsDataURL(file);
  });
}
