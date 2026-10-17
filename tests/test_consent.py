from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from apps.api.wearo_api.consent import (
    ConsentAttestation,
    ConsentError,
    ConsentEvidence,
    ConsentPurpose,
    ConsentService,
)

NOW = datetime(2026, 10, 17, 12, tzinfo=UTC)


class MemoryConsentStore:
    def __init__(self, asset_id: UUID, account_id: UUID) -> None:
        self.assets = {(asset_id, account_id)}
        self.items: list[ConsentEvidence] = []

    def asset_belongs_to(self, asset_id: UUID, account_id: UUID) -> bool:
        return (asset_id, account_id) in self.assets

    def append(self, evidence: ConsentEvidence) -> None:
        self.items.append(evidence)

    def latest(
        self, account_id: UUID, actor_principal_id: UUID, asset_id: UUID, purpose: ConsentPurpose
    ) -> ConsentEvidence | None:
        matches = [
            item
            for item in self.items
            if item.account_id == account_id
            and item.actor_principal_id == actor_principal_id
            and item.asset_id == asset_id
            and item.purpose == purpose
        ]
        return matches[-1] if matches else None


def approved() -> ConsentAttestation:
    return ConsentAttestation(True, True, True, True, True)


def test_all_disclosures_must_be_affirmatively_accepted() -> None:
    account_id, principal_id, asset_id = uuid4(), uuid4(), uuid4()
    service = ConsentService(MemoryConsentStore(asset_id, account_id), current_version="beta-v1")
    values = list(approved().__dict__.values())
    for index in range(len(values)):
        candidate = values.copy()
        candidate[index] = False
        with pytest.raises(ConsentError, match="affirmative"):
            service.accept(
                account_id=account_id,
                actor_principal_id=principal_id,
                asset_id=asset_id,
                purpose="TRY_ON",
                attestation=ConsentAttestation(*candidate),
                now=NOW,
            )


def test_current_consent_is_owner_actor_asset_purpose_and_version_scoped() -> None:
    account_id, principal_id, asset_id = uuid4(), uuid4(), uuid4()
    store = MemoryConsentStore(asset_id, account_id)
    service = ConsentService(store, current_version="beta-v1")
    evidence = service.accept(
        account_id=account_id,
        actor_principal_id=principal_id,
        asset_id=asset_id,
        purpose="TRY_ON",
        attestation=approved(),
        now=NOW,
    )
    assert (
        service.require_current(
            account_id=account_id,
            actor_principal_id=principal_id,
            asset_id=asset_id,
            purpose="TRY_ON",
        )
        == evidence
    )
    invalid_scopes: tuple[tuple[UUID, UUID, UUID, ConsentPurpose], ...] = (
        (uuid4(), principal_id, asset_id, "TRY_ON"),
        (account_id, uuid4(), asset_id, "TRY_ON"),
        (account_id, principal_id, uuid4(), "TRY_ON"),
        (account_id, principal_id, asset_id, "RESULT_SAVE"),
    )
    for invalid_account, invalid_principal, invalid_asset, invalid_purpose in invalid_scopes:
        with pytest.raises(ConsentError):
            service.require_current(
                account_id=invalid_account,
                actor_principal_id=invalid_principal,
                asset_id=invalid_asset,
                purpose=invalid_purpose,
            )
    newer = ConsentService(store, current_version="beta-v2")
    with pytest.raises(ConsentError):
        newer.require_current(
            account_id=account_id,
            actor_principal_id=principal_id,
            asset_id=asset_id,
            purpose="TRY_ON",
        )


def test_foreign_asset_cannot_receive_consent_evidence() -> None:
    account_id, principal_id, asset_id = uuid4(), uuid4(), uuid4()
    service = ConsentService(MemoryConsentStore(asset_id, uuid4()), current_version="beta-v1")
    with pytest.raises(ConsentError):
        service.accept(
            account_id=account_id,
            actor_principal_id=principal_id,
            asset_id=asset_id,
            purpose="TRY_ON",
            attestation=approved(),
            now=NOW,
        )
