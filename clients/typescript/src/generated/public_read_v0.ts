// GENERATED from contracts/public/openapi_v0.json. DO NOT EDIT.
// Authority: ADR-0008 / PUBLIC_READ_PLANE_V0.

export interface FrontierPublicReadTransport {
  get<T>(path: string, query?: Record<string, string | number | boolean | null | undefined>): Promise<T>;
}

export type CollectionOccurrenceResponse = { "completed_at": string | null; "occurrence_status": string; "reason": string; "recovered_after_gap": boolean; "run_id": string; "started_at": string; "trigger_id": string | null; };
export type EpisodeEvidenceResponse = { "episode": EpisodeResponse; "generated_at": string; "observations": Array<ObservationEvidenceResponse>; "schema_version"?: string; "snapshot": SnapshotBindingResponse; };
export type EpisodeResponse = { "acceleration_6h": number; "age_seconds": number; "backfill_evidence_count": number; "confirmation": string; "episode_id": string; "evidence_count_total": number; "evidence_root_diversity"?: null; "first_observed_at": string; "last_observed_at": string; "mentions_1h": number; "mentions_24h": number; "mentions_6h": number; "observation_ids": Array<string>; "preprevious_6h": number; "previous_6h": number; "prospective_evidence_count": number; "rank": number; "recovered_backlog_evidence_count": number; "signal_roles": Array<string>; "source_count": number; "source_ids": Array<string>; "source_role_diversity": number; "velocity_6h_delta": number; };
export type ExperimentalAnalysisArtifactResponse = { "algorithm_version": string; "analysis_id": string; "as_of": string; "authority_state": string; "configuration_digest": string; "control_receipt_id": string | null; "control_snapshot_id": string | null; "episode_universe_digest": string | null; "generated_at": string; "input_digest": string | null; "kind": string; "output_digest": string; "schema_version": string; "source_registry_version": string | null; "status": string; };
export type ExperimentalAnalysisArtifactSectionResponse = { "authority_state"?: string; "availability": string; "interpretation"?: string; "kind": string; "latest": ExperimentalAnalysisArtifactResponse | null; "schema_version"?: string; };
export type ExperimentalControlRankEntryResponse = { "episode_id": string; "rank": number; };
export type ExperimentalEpisodeComparisonResponse = { "as_of": string | null; "authority_state"?: string; "availability": string; "baseline_rank": number | null; "baseline_rank_state": string; "candidate_components": Record<string, unknown> | null; "candidate_components_state": string; "candidate_freeze_receipt_id": string | null; "candidate_rank": number | null; "candidate_rank_state": string; "control_snapshot_id": string | null; "episode_id": string; "evaluation_receipt_id": string | null; "evaluation_receipt_status": string | null; "evaluation_state": string; "feature_availability": string; "feature_interpretation": string | null; "feature_interpretation_state": string; "feature_values": Array<Record<string, unknown>>; "interpretation"?: string; "rank_delta": number | null; "rank_delta_state": string; "run_failure_reason": string | null; "run_id": string | null; "run_status": string | null; "schema_version"?: string; };
export type ExperimentalEvaluationDetailResponse = { "as_of": string; "authority_state": string; "candidate_configuration_digest": string; "candidate_freeze_receipt_id": string; "candidate_id": string; "domains": Array<ExperimentalEvaluationDomainRowResponse>; "evaluation_algorithm_version": string; "evaluation_configuration_digest": string; "evaluation_id": string; "experiment_id": string; "freeze_receipt_digest": string; "freeze_status": string; "generated_at": string; "preregistration_digest": string; "receipt_digest": string; "schema_version": string; "shadow_run_ids": Array<string>; "status": string; "status_reason": string | null; "verdict": string | null; };
export type ExperimentalEvaluationDetailSectionResponse = { "authority_state"?: string; "availability": string; "evaluation": ExperimentalEvaluationDetailResponse | null; "interpretation"?: string; "schema_version"?: string; };
export type ExperimentalEvaluationDomainRowResponse = { "candidate_positive_surfaced_resolved": number | null; "candidate_precision": string | null; "candidate_surfaced_resolved": number | null; "control_positive_surfaced_resolved": number | null; "control_precision": string | null; "control_surfaced_resolved": number | null; "difference_lower_bound": string | null; "domain": string; "median_lead_time_advantage_seconds": string | null; "noninferiority_pass": boolean | null; "qualifies_sample_adequacy": boolean | null; };
export type ExperimentalEvaluationHistoryEntryResponse = { "as_of": string; "evaluation_id": string; "status": string; };
export type ExperimentalEvaluationReceiptResponse = { "as_of": string; "authority_state": string; "candidate_configuration_digest": string; "candidate_freeze_receipt_id": string; "candidate_id": string; "evaluation_algorithm_version": string; "evaluation_configuration_digest": string; "evaluation_id": string; "experiment_id": string; "freeze_receipt_digest": string; "freeze_status": string; "generated_at": string; "preregistration_digest": string; "receipt_digest": string; "schema_version": string; "shadow_run_ids": Array<string>; "status": string; "status_reason": string | null; "verdict": string | null; };
export type ExperimentalEvaluationReceiptSectionResponse = { "authority_state"?: string; "availability": string; "interpretation"?: string; "latest": ExperimentalEvaluationReceiptResponse | null; "schema_version"?: string; };
export type ExperimentalFeatureBatchResponse = { "algorithm_version": string; "as_of": string; "authority_state": string; "batch_digest": string; "batch_id": string; "configuration_digest": string; "control_receipt_id": string; "control_snapshot_id": string; "episode_universe_digest": string; "generated_at": string; "schema_version": string; "status": string; "vector_count": number | null; };
export type ExperimentalFeatureBatchSectionResponse = { "authority_state"?: string; "availability": string; "interpretation"?: string; "latest": ExperimentalFeatureBatchResponse | null; "schema_version"?: string; };
export type ExperimentalHistoryResponse = { "authority_state"?: string; "availability": string; "candidate_id": string; "evaluations": Array<ExperimentalEvaluationHistoryEntryResponse>; "experiment_id": string; "interpretation"?: string; "limit": number; "runs": Array<ExperimentalRunHistoryEntryResponse>; "schema_version"?: string; };
export type ExperimentalOverviewResponse = { "analysis_artifacts": Record<string, ExperimentalAnalysisArtifactResponse>; "as_of": string; "authority_state"?: string; "availability": Record<string, string>; "candidate_id": string; "configuration_digest": string; "experiment_id": string; "generated_at": string; "interpretation"?: string; "latest_evaluation_receipt": ExperimentalEvaluationReceiptResponse | null; "latest_feature_batch": ExperimentalFeatureBatchResponse | null; "latest_pef_artifact": ExperimentalPefArtifactResponse | null; "latest_shadow_run": ExperimentalShadowRunResponse | null; "schema_version"?: string; };
export type ExperimentalPefArtifactResponse = { "algorithm_version": string; "artifact_id": string; "as_of": string; "authority_state": string; "candidate_id": string; "configuration_digest": string; "control_receipt_id": string; "control_snapshot_id": string; "episode_count": number | null; "experiment_id": string; "failure_reason": string | null; "generated_at": string; "output_digest": string; "ranking_policy_version": string; "receipt_id": string; "schema_version": string; "status": string; };
export type ExperimentalPefArtifactSectionResponse = { "authority_state"?: string; "availability": string; "interpretation"?: string; "latest": ExperimentalPefArtifactResponse | null; "schema_version"?: string; };
export type ExperimentalRunDetailResponse = { "algorithm_version": string; "as_of": string; "authority_state": string; "candidate_artifact_id": string; "candidate_freeze_receipt_id": string | null; "candidate_id": string; "candidate_output_digest": string; "configuration_digest": string; "control_ranking": Array<ExperimentalControlRankEntryResponse>; "control_receipt_id": string; "control_snapshot_id": string; "coverage_state": string; "episode_universe_digest": string; "experiment_id": string; "failure_reason": string | null; "generated_at": string; "run_class": string | null; "run_digest": string; "run_id": string; "schema_version": string; "status": string; };
export type ExperimentalRunDetailSectionResponse = { "authority_state"?: string; "availability": string; "interpretation"?: string; "run": ExperimentalRunDetailResponse | null; "schema_version"?: string; };
export type ExperimentalRunHistoryEntryResponse = { "as_of": string; "run_class": string | null; "run_digest": string; "run_id": string; "status": string; };
export type ExperimentalShadowRunResponse = { "algorithm_version": string; "as_of": string; "authority_state": string; "candidate_artifact_id": string; "candidate_freeze_receipt_id": string | null; "candidate_id": string; "candidate_output_digest": string; "configuration_digest": string; "control_receipt_id": string; "control_snapshot_id": string; "episode_universe_digest": string; "experiment_id": string; "failure_reason": string | null; "generated_at": string; "run_digest": string; "run_id": string; "schema_version": string; "status": string; };
export type ExperimentalShadowRunSectionResponse = { "authority_state"?: string; "availability": string; "interpretation"?: string; "latest": ExperimentalShadowRunResponse | null; "schema_version"?: string; };
export type ExperimentalStatusResponse = { "authority_state"?: string; "availability": string; "interpretation"?: string; "schema_version"?: string; "status": Record<string, unknown> | null; };
export type HTTPValidationError = { "detail"?: Array<ValidationError>; };
export type HealthResponse = { "coverage_state": string; "freshness_state": string; "generated_at": string; "schema_state": string; "schema_version"?: string; "snapshot": SnapshotBindingResponse; "sources": Array<SourceHealthResponse>; "transport_state": string; };
export type MetaResponse = { "api_version": string; "intelligence_authority": string; "mutation_authority": boolean; "openapi_typescript_authority": string; "response_schema_family": string; };
export type ObservationEvidenceResponse = { "canonicalization_version": string; "collection_occurrences": Array<CollectionOccurrenceResponse>; "content_digest": string; "effective_at": string | null; "fetch_digest": string; "kind": string; "observation_id": string; "observed_at": string; "payload": Record<string, unknown>; "relations": Array<ObservationRelationResponse>; "retrieved_at": string; "schema_version": string; "source_id": string; "source_item_key": string; "source_published_at": string | null; };
export type ObservationRelationResponse = { "algorithm_version": string | null; "authority": string; "confidence": string | null; "evidence": Record<string, unknown>; "from_observation_id": string; "relation_id": string; "relation_type": string; "target_external_ref": string | null; "target_observation_id": string | null; };
export type ObservationResponse = { "generated_at": string; "observation": ObservationEvidenceResponse; "schema_version"?: string; "snapshot": SnapshotBindingResponse; };
export type PublicViewKind = "RADAR" | "NOW" | "TRENDING";
export type SnapshotBindingResponse = { "algorithm_version": string; "as_of": string; "configuration_digest": string; "input_digest": string; "output_digest": string; "projection_name": string; "projection_version": string; "ranking_policy_version": string; "receipt_id": string; "receipt_schema_version": string; "schema_version": string; "snapshot_id": string; "source_registry_version": string; };
export type SourceHealthResponse = { "as_of": string; "completeness": string; "details": Record<string, unknown>; "freshness": string; "schema": string; "source_id": string; "transport": string; };
export type ValidationError = { "ctx"?: Record<string, unknown>; "input"?: unknown; "loc": Array<string | number>; "msg": string; "type": string; };
export type ViewResponse = { "coverage_state": string; "freshness_state": string; "generated_at": string; "items": Array<EpisodeResponse>; "limit": number; "offset": number; "schema_state": string; "schema_version"?: string; "semantic_scope": string; "snapshot": SnapshotBindingResponse; "total": number; "transport_state": string; "view": PublicViewKind; "view_policy_version": string; };

export async function getEpisode(transport: FrontierPublicReadTransport, episode_id: string, query: { snapshot_id?: string | null; } = {}): Promise<EpisodeEvidenceResponse> {
  return transport.get<EpisodeEvidenceResponse>(`/v0/episodes/${encodeURIComponent(String(episode_id))}`, query);
}

export async function getExperimentalAnalysisArtifacts(transport: FrontierPublicReadTransport, kind: string, query: { as_of?: string | null; } = {}): Promise<ExperimentalAnalysisArtifactSectionResponse> {
  return transport.get<ExperimentalAnalysisArtifactSectionResponse>(`/v0/experimental/analysis/${encodeURIComponent(String(kind))}`, query);
}

export async function getExperimentalEpisodeComparison(transport: FrontierPublicReadTransport, episode_id: string, query: { as_of?: string | null; run_id?: string | null; } = {}): Promise<ExperimentalEpisodeComparisonResponse> {
  return transport.get<ExperimentalEpisodeComparisonResponse>(`/v0/experimental/episodes/${encodeURIComponent(String(episode_id))}/comparison`, query);
}

export async function getExperimentalEvaluationReceipts(transport: FrontierPublicReadTransport, query: { as_of?: string | null; } = {}): Promise<ExperimentalEvaluationReceiptSectionResponse> {
  return transport.get<ExperimentalEvaluationReceiptSectionResponse>("/v0/experimental/evaluation-receipts", query);
}

export async function getExperimentalEvaluationDetail(transport: FrontierPublicReadTransport, evaluation_id: string, query: { as_of?: string | null; } = {}): Promise<ExperimentalEvaluationDetailSectionResponse> {
  return transport.get<ExperimentalEvaluationDetailSectionResponse>(`/v0/experimental/evaluations/${encodeURIComponent(String(evaluation_id))}`, query);
}

export async function getExperimentalFeatureBatches(transport: FrontierPublicReadTransport, query: { as_of?: string | null; } = {}): Promise<ExperimentalFeatureBatchSectionResponse> {
  return transport.get<ExperimentalFeatureBatchSectionResponse>("/v0/experimental/feature-batches", query);
}

export async function getExperimentalHistory(transport: FrontierPublicReadTransport, query: { limit?: number; } = {}): Promise<ExperimentalHistoryResponse> {
  return transport.get<ExperimentalHistoryResponse>("/v0/experimental/history", query);
}

export async function getExperimentalOverview(transport: FrontierPublicReadTransport, query: { as_of?: string | null; } = {}): Promise<ExperimentalOverviewResponse> {
  return transport.get<ExperimentalOverviewResponse>("/v0/experimental/overview", query);
}

export async function getExperimentalPefArtifacts(transport: FrontierPublicReadTransport, query: { as_of?: string | null; } = {}): Promise<ExperimentalPefArtifactSectionResponse> {
  return transport.get<ExperimentalPefArtifactSectionResponse>("/v0/experimental/pef-artifacts", query);
}

export async function getExperimentalRunDetail(transport: FrontierPublicReadTransport, run_id: string, query: { as_of?: string | null; } = {}): Promise<ExperimentalRunDetailSectionResponse> {
  return transport.get<ExperimentalRunDetailSectionResponse>(`/v0/experimental/runs/${encodeURIComponent(String(run_id))}`, query);
}

export async function getExperimentalShadowRuns(transport: FrontierPublicReadTransport, query: { as_of?: string | null; } = {}): Promise<ExperimentalShadowRunSectionResponse> {
  return transport.get<ExperimentalShadowRunSectionResponse>("/v0/experimental/shadow-runs", query);
}

export async function getExperimentalStatus(transport: FrontierPublicReadTransport): Promise<ExperimentalStatusResponse> {
  return transport.get<ExperimentalStatusResponse>("/v0/experimental/status");
}

export async function getHealth(transport: FrontierPublicReadTransport, query: { snapshot_id?: string | null; } = {}): Promise<HealthResponse> {
  return transport.get<HealthResponse>("/v0/health", query);
}

export async function getPublicReadMeta(transport: FrontierPublicReadTransport): Promise<MetaResponse> {
  return transport.get<MetaResponse>("/v0/meta");
}

export async function getNow(transport: FrontierPublicReadTransport, query: { limit?: number; offset?: number; snapshot_id?: string | null; } = {}): Promise<ViewResponse> {
  return transport.get<ViewResponse>("/v0/now", query);
}

export async function getObservation(transport: FrontierPublicReadTransport, observation_id: string, query: { snapshot_id?: string | null; } = {}): Promise<ObservationResponse> {
  return transport.get<ObservationResponse>(`/v0/observations/${encodeURIComponent(String(observation_id))}`, query);
}

export async function getRadar(transport: FrontierPublicReadTransport, query: { limit?: number; offset?: number; snapshot_id?: string | null; } = {}): Promise<ViewResponse> {
  return transport.get<ViewResponse>("/v0/radar", query);
}

export async function getTrending(transport: FrontierPublicReadTransport, query: { limit?: number; offset?: number; snapshot_id?: string | null; } = {}): Promise<ViewResponse> {
  return transport.get<ViewResponse>("/v0/trending", query);
}
