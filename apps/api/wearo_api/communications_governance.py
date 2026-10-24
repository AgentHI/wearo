from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from .tenant_scope import TenantScopeError, require_tenant_scope

CommunicationChannel = Literal["EMAIL", "SMS"]
CommunicationTopic = Literal["PRODUCT", "BILLING", "LEGAL"]


class CommunicationsError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PostgresCommunicationsGovernance:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _owner(connection: Connection, principal_id: UUID, tenant_id: UUID) -> UUID:
        try:
            return require_tenant_scope(
                connection, principal_id, tenant_id, roles=frozenset({"OWNER"})
            ).account_id
        except TenantScopeError:
            raise CommunicationsError(
                "COMMUNICATIONS_UNAVAILABLE", "Resource unavailable."
            ) from None

    def overview(self, principal_id: UUID, tenant_id: UUID) -> dict[str, object]:
        now = datetime.now(UTC)
        with self.engine.connect() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            notices = tuple(
                dict(row)
                for row in connection.execute(
                    text("""
                SELECT n.notice_id, n.notice_type, n.offering, n.version, n.content_url,
                       n.effective_at, a.accepted_at
                FROM legal_notices n
                LEFT JOIN legal_notice_acceptances a ON a.notice_id=n.notice_id
                  AND a.account_id=:account AND a.tenant_id=:tenant AND a.principal_id=:principal
                WHERE n.effective_at <= :now AND (n.retired_at IS NULL OR n.retired_at > :now)
                ORDER BY n.offering, n.notice_type, n.effective_at DESC"""),
                    {
                        "account": account_id,
                        "tenant": tenant_id,
                        "principal": principal_id,
                        "now": now,
                    },
                ).mappings()
            )
            history = tuple(
                dict(row)
                for row in connection.execute(
                    text("""
                SELECT n.notice_type, n.offering, n.version, n.content_url, a.accepted_at
                FROM legal_notice_acceptances a JOIN legal_notices n ON n.notice_id=a.notice_id
                WHERE a.account_id=:account AND a.tenant_id=:tenant
                ORDER BY a.accepted_at DESC"""),
                    {"account": account_id, "tenant": tenant_id},
                ).mappings()
            )
            preferences = tuple(
                dict(row)
                for row in connection.execute(
                    text("""
                SELECT channel, topic, enabled, updated_at FROM communication_preferences
                WHERE account_id=:account AND tenant_id=:tenant AND principal_id=:principal
                ORDER BY channel, topic"""),
                    {"account": account_id, "tenant": tenant_id, "principal": principal_id},
                ).mappings()
            )
        return {
            "active_notices": notices,
            "acceptance_history": history,
            "communication_preferences": preferences,
        }

    def accept(self, principal_id: UUID, tenant_id: UUID, notice_id: UUID) -> dict[str, object]:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            notice = connection.execute(
                text("""SELECT notice_id FROM legal_notices
                WHERE notice_id=:notice AND effective_at <= :now
                  AND (retired_at IS NULL OR retired_at > :now)"""),
                {"notice": notice_id, "now": now},
            ).scalar_one_or_none()
            if notice is None:
                raise CommunicationsError("NOTICE_UNAVAILABLE", "Notice is unavailable.")
            row = (
                connection.execute(
                    text("""INSERT INTO legal_notice_acceptances
                (acceptance_id, notice_id, account_id, tenant_id, principal_id, accepted_at)
                VALUES (:acceptance, :notice, :account, :tenant, :principal, :now)
                ON CONFLICT (notice_id, principal_id, tenant_id) DO UPDATE
                  SET notice_id=EXCLUDED.notice_id
                RETURNING acceptance_id, notice_id, accepted_at"""),
                    {
                        "acceptance": uuid4(),
                        "notice": notice_id,
                        "account": account_id,
                        "tenant": tenant_id,
                        "principal": principal_id,
                        "now": now,
                    },
                )
                .mappings()
                .one()
            )
            return dict(row)

    def set_preference(
        self,
        principal_id: UUID,
        tenant_id: UUID,
        channel: CommunicationChannel,
        topic: CommunicationTopic,
        enabled: bool,
    ) -> dict[str, object]:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            account_id = self._owner(connection, principal_id, tenant_id)
            row = (
                connection.execute(
                    text("""INSERT INTO communication_preferences
                (preference_id, account_id, tenant_id, principal_id, channel, topic, enabled)
                VALUES (:preference, :account, :tenant, :principal, :channel, :topic, :enabled)
                ON CONFLICT (tenant_id, principal_id, channel, topic) DO UPDATE SET
                  enabled=EXCLUDED.enabled, updated_at=:now
                RETURNING channel, topic, enabled, updated_at"""),
                    {
                        "preference": uuid4(),
                        "account": account_id,
                        "tenant": tenant_id,
                        "principal": principal_id,
                        "channel": channel,
                        "topic": topic,
                        "enabled": enabled,
                        "now": now,
                    },
                )
                .mappings()
                .one()
            )
            return dict(row)
