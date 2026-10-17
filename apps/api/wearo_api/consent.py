from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID, uuid4

ConsentPurpose = Literal["TRY_ON", "STORE_TRY_ON", "RESULT_SAVE"]


class ConsentError(ValueError):
    """Consent is absent, invalid, withdrawn, or outside the requested scope."""


@dataclass(frozen=True)
class ConsentAttestation:
    adult_confirmed: bool
    depicted_person_permission: bool
    transformation_approved: bool
    retention_notice_acknowledged: bool
    no_training_notice_acknowledged: bool


@dataclass(frozen=True)
class ConsentEvidence:
    consent_id: UUID
    account_id: UUID
    actor_principal_id: UUID
    asset_id: UUID
    purpose: ConsentPurpose
    consent_version: str
    accepted_at: datetime
    withdrawn_at: datetime | None = None


class ConsentStore(Protocol):
    def asset_belongs_to(self, asset_id: UUID, account_id: UUID) -> bool: ...

    def append(self, evidence: ConsentEvidence) -> None: ...

    def latest(
        self, account_id: UUID, actor_principal_id: UUID, asset_id: UUID, purpose: ConsentPurpose
    ) -> ConsentEvidence | None: ...


class ConsentService:
    def __init__(self, store: ConsentStore, *, current_version: str) -> None:
        if not current_version.strip():
            raise ValueError("consent version is required")
        self.store = store
        self.current_version = current_version

    def accept(
        self,
        *,
        account_id: UUID,
        actor_principal_id: UUID,
        asset_id: UUID,
        purpose: ConsentPurpose,
        attestation: ConsentAttestation,
        now: datetime | None = None,
    ) -> ConsentEvidence:
        if not all(
            (
                attestation.adult_confirmed,
                attestation.depicted_person_permission,
                attestation.transformation_approved,
                attestation.retention_notice_acknowledged,
                attestation.no_training_notice_acknowledged,
            )
        ):
            raise ConsentError("affirmative consent is required")
        if not self.store.asset_belongs_to(asset_id, account_id):
            raise ConsentError("affirmative consent is required")
        evidence = ConsentEvidence(
            consent_id=uuid4(),
            account_id=account_id,
            actor_principal_id=actor_principal_id,
            asset_id=asset_id,
            purpose=purpose,
            consent_version=self.current_version,
            accepted_at=now or datetime.now(UTC),
        )
        self.store.append(evidence)
        return evidence

    def require_current(
        self,
        *,
        account_id: UUID,
        actor_principal_id: UUID,
        asset_id: UUID,
        purpose: ConsentPurpose,
    ) -> ConsentEvidence:
        evidence = self.store.latest(account_id, actor_principal_id, asset_id, purpose)
        if (
            evidence is None
            or evidence.account_id != account_id
            or evidence.actor_principal_id != actor_principal_id
            or evidence.asset_id != asset_id
            or evidence.purpose != purpose
            or evidence.consent_version != self.current_version
            or evidence.withdrawn_at is not None
        ):
            raise ConsentError("affirmative consent is required")
        return evidence
