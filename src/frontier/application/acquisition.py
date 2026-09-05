from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from frontier.adapters.acquisition.config import FetchPolicy, RegisteredSource, SourceRegistry
from frontier.adapters.acquisition.normalizers import NormalizationError, normalize_source
from frontier.application.acquisition_state import SourceFetchState
from frontier.application.ports.fetcher import FetcherPort
from frontier.application.ports.repositories import AcquisitionRepository
from frontier.contracts.fetch import (
    BoundedFetchResult,
    FetchFailure,
    FetchOutcome,
    FetchRequest,
)
from frontier.domain.canonical_json import CanonicalValue
from frontier.domain.collection import CollectionReason, CollectionRun, CollectionRunStatus
from frontier.domain.digests import sha256_digest
from frontier.domain.health import HealthValue, SourceHealthObservation
from frontier.domain.observation import ObservationCandidate

Clock = Callable[[], datetime]
Sleep = Callable[[float], Awaitable[None]]
Jitter = Callable[[], float]


@dataclass(frozen=True, slots=True)
class AcquisitionResult:
    run_id: UUID
    source_id: str
    status: CollectionRunStatus
    inserted: int
    duplicates: int
    rejected: int
    observation_ids: tuple[str, ...]
    failure_code: str | None


class AcquisitionService:
    def __init__(
        self,
        *,
        registry: SourceRegistry,
        policy: FetchPolicy,
        fetcher: FetcherPort,
        repository: AcquisitionRepository,
        clock: Clock | None = None,
        sleep: Sleep | None = None,
        jitter: Jitter | None = None,
    ) -> None:
        self._registry = registry
        self._policy = policy
        self._fetcher = fetcher
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))
        self._sleep = sleep or asyncio.sleep
        self._jitter = jitter or random.random

    async def acquire(
        self,
        source_id: str,
        *,
        reason: CollectionReason = CollectionReason.SCHEDULED,
        trigger_id: str | None = None,
    ) -> AcquisitionResult:
        source = self._registry.require(source_id)
        if source.policy_profile != self._policy.policy_profile:
            raise ValueError("source policy profile does not match loaded fetch policy")
        self._repository.upsert_source(source.contract)
        state = self._repository.get_source_fetch_state(source_id)
        now = self._clock()
        if state is not None and state.next_retry_at is not None and state.next_retry_at > now:
            return AcquisitionResult(
                run_id=uuid4(),
                source_id=source_id,
                status=CollectionRunStatus.FAILED,
                inserted=0,
                duplicates=0,
                rejected=0,
                observation_ids=(),
                failure_code="RETRY_NOT_DUE",
            )
        recovered_after_gap = state is not None and state.consecutive_failures > 0
        run = CollectionRun(
            run_id=uuid4(),
            source_id=source_id,
            reason=reason,
            trigger_id=trigger_id,
            recovered_after_gap=recovered_after_gap,
            started_at=now,
        )
        self._repository.start_collection_run(run)

        result = await self._fetch_with_retry(source, run.run_id, state)
        trusted_retrieved_at = self._clock()
        if result.outcome is not FetchOutcome.SUCCESS:
            failure = result.failure
            code = failure.code if failure is not None else "FETCH_FAILED"
            next_retry = self._next_retry_at(failure, attempt=self._policy.retry.max_attempts)
            self._repository.record_fetch_failure(source_id, next_retry_at=next_retry)
            self._record_health(
                source_id,
                run.run_id,
                transport=(
                    HealthValue.FAILED
                    if result.outcome is FetchOutcome.FAILED
                    else HealthValue.DEGRADED
                ),
                freshness=HealthValue.UNKNOWN,
                completeness=HealthValue.DEGRADED,
                schema=HealthValue.UNKNOWN,
                details={
                    "failure_code": code,
                    "fetch_outcome": result.outcome.value,
                    "recovered_after_gap": recovered_after_gap,
                },
            )
            self._repository.complete_collection_run(
                run.run_id,
                status=CollectionRunStatus.FAILED,
                records_received=0,
                records_accepted=0,
                records_rejected=0,
                duplicates=0,
                failure_code=code,
            )
            return AcquisitionResult(
                run_id=run.run_id,
                source_id=source_id,
                status=CollectionRunStatus.FAILED,
                inserted=0,
                duplicates=0,
                rejected=0,
                observation_ids=(),
                failure_code=code,
            )

        if result.request_id.rsplit(":", 1)[0] != run.run_id.hex:
            return self._fail_closed(run, source, "FETCH_CORRELATION_MISMATCH")
        if result.body is None:
            return self._fail_closed(run, source, "FETCH_BODY_MISSING")
        trusted_digest = sha256_digest(result.body)
        if result.body_digest is not None and result.body_digest != trusted_digest:
            return self._fail_closed(run, source, "FETCH_DIGEST_MISMATCH")

        if result.http_status == 304:
            if state is None or state.last_body_digest is None:
                return self._fail_closed(run, source, "CACHE_ENTITY_MISSING")
            self._repository.record_fetch_success(
                source_id,
                etag=result.response_headers.get("ETag") or state.etag,
                last_modified=result.response_headers.get("Last-Modified") or state.last_modified,
                body_digest=state.last_body_digest,
                succeeded_at=trusted_retrieved_at,
            )
            completeness = (
                HealthValue.DEGRADED
                if source.finite_window and recovered_after_gap
                else HealthValue.OK
            )
            self._record_health(
                source_id,
                run.run_id,
                transport=HealthValue.OK,
                freshness=HealthValue.UNKNOWN,
                completeness=completeness,
                schema=HealthValue.OK,
                details={
                    "http_status": 304,
                    "not_modified": True,
                    "recovered_after_gap": recovered_after_gap,
                },
            )
            self._repository.complete_collection_run(
                run.run_id,
                status=CollectionRunStatus.SUCCESS,
                records_received=0,
                records_accepted=0,
                records_rejected=0,
                duplicates=0,
                failure_code=None,
            )
            return AcquisitionResult(
                run_id=run.run_id,
                source_id=source_id,
                status=CollectionRunStatus.SUCCESS,
                inserted=0,
                duplicates=0,
                rejected=0,
                observation_ids=(),
                failure_code=None,
            )

        if result.http_status != 200:
            return self._fail_closed(run, source, "UNEXPECTED_SUCCESS_STATUS")
        actual_type = (result.content_type or "").lower()
        accepted = {value.lower() for value in source.accepted_content_types}
        if actual_type not in accepted:
            return self._semantic_failure(
                run,
                source,
                "CONTENT_TYPE_UNEXPECTED",
                transport=HealthValue.OK,
                schema=HealthValue.DEGRADED,
                details={"content_type": actual_type or None},
            )
        try:
            batch = normalize_source(
                source_id,
                result.body,
                retrieved_at=trusted_retrieved_at,
                fetch_digest=trusted_digest,
            )
        except NormalizationError as exc:
            return self._semantic_failure(
                run,
                source,
                exc.code,
                transport=HealthValue.OK,
                schema=HealthValue.FAILED,
                details={"normalization_error": exc.code},
            )

        inserted = 0
        duplicates = 0
        observation_ids: list[str] = []
        for candidate in batch.candidates:
            observation, was_inserted = self._repository.append_observation(candidate, run.run_id)
            observation_ids.append(observation.observation_id)
            if was_inserted:
                inserted += 1
            else:
                duplicates += 1

        previous_digest = state.last_body_digest if state is not None else None
        previous_etag = state.etag if state is not None else None
        response_etag = result.response_headers.get("ETag")
        validator_inconsistency = (
            previous_digest is not None
            and previous_etag is not None
            and response_etag == previous_etag
            and previous_digest != trusted_digest
        )
        schema_health = batch.schema_health
        if validator_inconsistency:
            schema_health = HealthValue.DEGRADED
        completeness = batch.completeness_health
        if source.finite_window and recovered_after_gap:
            completeness = HealthValue.DEGRADED
        if batch.records_rejected:
            completeness = HealthValue.DEGRADED
        freshness = self._freshness(source, batch.candidates, trusted_retrieved_at)
        self._repository.record_fetch_success(
            source_id,
            etag=response_etag,
            last_modified=result.response_headers.get("Last-Modified"),
            body_digest=trusted_digest,
            succeeded_at=trusted_retrieved_at,
        )
        self._record_health(
            source_id,
            run.run_id,
            transport=HealthValue.OK,
            freshness=freshness,
            completeness=completeness,
            schema=schema_health,
            details={
                **batch.details,
                "http_status": 200,
                "recovered_after_gap": recovered_after_gap,
                "validator_inconsistency": validator_inconsistency,
                "source_registry_version": str(self._registry.source_registry_version),
            },
        )
        status = (
            CollectionRunStatus.PARTIAL
            if schema_health is HealthValue.DEGRADED or completeness is HealthValue.DEGRADED
            else CollectionRunStatus.SUCCESS
        )
        self._repository.complete_collection_run(
            run.run_id,
            status=status,
            records_received=batch.records_received,
            records_accepted=inserted,
            records_rejected=batch.records_rejected,
            duplicates=duplicates,
            failure_code=None,
        )
        return AcquisitionResult(
            run_id=run.run_id,
            source_id=source_id,
            status=status,
            inserted=inserted,
            duplicates=duplicates,
            rejected=batch.records_rejected,
            observation_ids=tuple(observation_ids),
            failure_code=None,
        )

    async def _fetch_with_retry(
        self,
        source: RegisteredSource,
        run_id: UUID,
        state: SourceFetchState | None,
    ) -> BoundedFetchResult:
        last_result: BoundedFetchResult | None = None
        for attempt in range(1, self._policy.retry.max_attempts + 1):
            request = self._request(source, run_id, attempt, state)
            last_result = await self._fetch_with_fallback(source, request)
            if last_result.outcome is FetchOutcome.SUCCESS:
                return last_result
            failure = last_result.failure
            if (
                failure is None
                or not failure.retryable
                or attempt == self._policy.retry.max_attempts
            ):
                return last_result
            delay = self._retry_delay(failure.retry_after_seconds, attempt)
            if (
                failure.retry_after_seconds is not None
                and delay > self._policy.retry.max_delay_ms / 1000
            ):
                return last_result
            await self._sleep(delay)
        assert last_result is not None
        return last_result

    async def _fetch_with_fallback(
        self, source: RegisteredSource, request: FetchRequest
    ) -> BoundedFetchResult:
        urls = (source.endpoint_url, *source.fallback_urls)
        last_result: BoundedFetchResult | None = None
        for index, url in enumerate(urls):
            candidate = FetchRequest(
                request_id=request.request_id,
                source_id=request.source_id,
                url=url,
                policy_profile=request.policy_profile,
                credential_ref=request.credential_ref,
                accepted_content_types=request.accepted_content_types,
                deadline_ms=request.deadline_ms,
                max_response_bytes=request.max_response_bytes,
                max_redirects=request.max_redirects,
                request_headers=request.request_headers,
            )
            last_result = await self._fetcher.fetch(candidate)
            if last_result.outcome is FetchOutcome.SUCCESS:
                return last_result
            if last_result.outcome is FetchOutcome.REJECTED:
                return last_result
            failure = last_result.failure
            if failure is not None and failure.retry_after_seconds is not None:
                return last_result
            if index + 1 < len(urls) and source.fallback_semantics != "SAME_AUTHORITY_MIRROR":
                return last_result
        assert last_result is not None
        return last_result

    def _request(
        self,
        source: RegisteredSource,
        run_id: UUID,
        attempt: int,
        state: SourceFetchState | None,
    ) -> FetchRequest:
        headers = {
            "Accept": ", ".join(source.accepted_content_types),
            "User-Agent": "FRONTIER/0.1 (+https://github.com/CipherCuttle/frontier)",
        }
        if state is not None and state.etag:
            headers["If-None-Match"] = state.etag
        if state is not None and state.last_modified:
            headers["If-Modified-Since"] = state.last_modified
        return FetchRequest(
            request_id=f"{run_id.hex}:{attempt}",
            source_id=source.contract.source_id,
            url=source.endpoint_url,
            policy_profile=source.policy_profile,
            credential_ref=source.credential_ref,
            accepted_content_types=source.accepted_content_types,
            deadline_ms=self._policy.deadline_ms,
            max_response_bytes=self._policy.max_response_bytes,
            max_redirects=self._policy.max_redirects,
            request_headers=headers,
        )

    def _retry_delay(self, retry_after: int | None, attempt: int) -> float:
        base = self._policy.retry.base_delay_ms / 1000 * (2 ** max(0, attempt - 1))
        capped = min(base, self._policy.retry.max_delay_ms / 1000)
        if self._policy.retry.jitter:
            capped *= 0.5 + self._jitter()
        if retry_after is not None:
            capped = max(capped, float(retry_after))
        return min(float(self._policy.retry.max_retry_after_seconds), capped)

    def _next_retry_at(self, failure: FetchFailure | None, *, attempt: int) -> datetime | None:
        if failure is None or not failure.retryable:
            return None
        delay = self._retry_delay(failure.retry_after_seconds, attempt)
        return self._clock() + timedelta(seconds=delay)

    def _freshness(
        self,
        source: RegisteredSource,
        candidates: tuple[ObservationCandidate, ...],
        retrieved_at: datetime,
    ) -> HealthValue:
        timestamps = [
            candidate.source_published_at
            for candidate in candidates
            if candidate.source_published_at is not None
        ]
        if not timestamps:
            return HealthValue.UNKNOWN
        newest = max(timestamps)
        age = max(0.0, (retrieved_at - newest).total_seconds())
        return HealthValue.OK if age <= source.poll_interval_seconds * 2 else HealthValue.DEGRADED

    def _record_health(
        self,
        source_id: str,
        run_id: UUID,
        *,
        transport: HealthValue,
        freshness: HealthValue,
        completeness: HealthValue,
        schema: HealthValue,
        details: dict[str, CanonicalValue],
    ) -> None:
        self._repository.add_source_health(
            SourceHealthObservation(
                source_id=source_id,
                as_of=self._clock(),
                transport=transport,
                freshness=freshness,
                completeness=completeness,
                schema=schema,
                details=details,
            ),
            run_id,
        )

    def _fail_closed(
        self, run: CollectionRun, source: RegisteredSource, code: str
    ) -> AcquisitionResult:
        self._repository.record_fetch_failure(source.contract.source_id, next_retry_at=None)
        self._record_health(
            source.contract.source_id,
            run.run_id,
            transport=HealthValue.FAILED,
            freshness=HealthValue.UNKNOWN,
            completeness=HealthValue.DEGRADED,
            schema=HealthValue.FAILED,
            details={"failure_code": code, "fail_closed": True},
        )
        self._repository.complete_collection_run(
            run.run_id,
            status=CollectionRunStatus.FAILED,
            records_received=0,
            records_accepted=0,
            records_rejected=0,
            duplicates=0,
            failure_code=code,
        )
        return AcquisitionResult(
            run_id=run.run_id,
            source_id=source.contract.source_id,
            status=CollectionRunStatus.FAILED,
            inserted=0,
            duplicates=0,
            rejected=0,
            observation_ids=(),
            failure_code=code,
        )

    def _semantic_failure(
        self,
        run: CollectionRun,
        source: RegisteredSource,
        code: str,
        *,
        transport: HealthValue,
        schema: HealthValue,
        details: dict[str, CanonicalValue],
    ) -> AcquisitionResult:
        self._repository.record_fetch_failure(source.contract.source_id, next_retry_at=None)
        self._record_health(
            source.contract.source_id,
            run.run_id,
            transport=transport,
            freshness=HealthValue.UNKNOWN,
            completeness=HealthValue.DEGRADED,
            schema=schema,
            details={**details, "failure_code": code},
        )
        self._repository.complete_collection_run(
            run.run_id,
            status=CollectionRunStatus.FAILED,
            records_received=0,
            records_accepted=0,
            records_rejected=0,
            duplicates=0,
            failure_code=code,
        )
        return AcquisitionResult(
            run_id=run.run_id,
            source_id=source.contract.source_id,
            status=CollectionRunStatus.FAILED,
            inserted=0,
            duplicates=0,
            rejected=0,
            observation_ids=(),
            failure_code=code,
        )
