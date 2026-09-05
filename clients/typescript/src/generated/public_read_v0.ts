// GENERATED from contracts/public/openapi_v0.json. DO NOT EDIT.
// Authority: ADR-0008 / PUBLIC_READ_PLANE_V0.

export interface FrontierPublicReadTransport {
  get<T>(path: string, query?: Record<string, string | number | boolean | null | undefined>): Promise<T>;
}

export type CollectionOccurrenceResponse = { "completed_at": string | null; "occurrence_status": string; "reason": string; "recovered_after_gap": boolean; "run_id": string; "started_at": string; "trigger_id": string | null; };
export type EpisodeEvidenceResponse = { "episode": EpisodeResponse; "generated_at": string; "observations": Array<ObservationEvidenceResponse>; "schema_version"?: string; "snapshot": SnapshotBindingResponse; };
export type EpisodeResponse = { "acceleration_6h": number; "age_seconds": number; "backfill_evidence_count": number; "confirmation": string; "episode_id": string; "evidence_count_total": number; "evidence_root_diversity"?: null; "first_observed_at": string; "last_observed_at": string; "mentions_1h": number; "mentions_24h": number; "mentions_6h": number; "observation_ids": Array<string>; "preprevious_6h": number; "previous_6h": number; "prospective_evidence_count": number; "rank": number; "recovered_backlog_evidence_count": number; "signal_roles": Array<string>; "source_count": number; "source_ids": Array<string>; "source_role_diversity": number; "velocity_6h_delta": number; };
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
