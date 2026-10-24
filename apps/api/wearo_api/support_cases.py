from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from .tenant_scope import TenantScopeError, require_tenant_scope

CaseType = Literal["SUPPORT", "PAYMENT", "QUALITY"]


class SupportCaseError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PostgresSupportCases:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _scope(connection: Connection, principal_id: UUID, tenant_id: UUID) -> UUID:
        try:
            return require_tenant_scope(connection, principal_id, tenant_id).account_id
        except TenantScopeError:
            raise SupportCaseError("CASE_UNAVAILABLE", "Resource unavailable.") from None

    def create(
        self, principal_id: UUID, tenant_id: UUID, case_type: CaseType, reason: str
    ) -> dict[str, object]:
        detail = reason.strip()
        if not detail or len(detail) > 2000:
            raise SupportCaseError("INVALID_CASE_REASON", "Describe the issue in 2000 characters.")
        now, case_id = datetime.now(UTC), uuid4()
        with self.engine.begin() as connection:
            account_id = self._scope(connection, principal_id, tenant_id)
            row = (
                connection.execute(
                    text("""INSERT INTO operation_cases
                (case_id, account_id, tenant_id, case_type, state, opened_by_type,
                 opened_by_id, reason, created_at)
                VALUES (:case, :account, :tenant, :type, 'SUBMITTED', 'PRINCIPAL',
                        :principal, :reason, :now)
                RETURNING case_id, case_type, state, reason, disposition,
                          resolved_at, created_at"""),
                    {
                        "case": case_id,
                        "account": account_id,
                        "tenant": tenant_id,
                        "type": case_type,
                        "principal": principal_id,
                        "reason": detail,
                        "now": now,
                    },
                )
                .mappings()
                .one()
            )
            connection.execute(
                text("""INSERT INTO operation_case_events
                (case_id, account_id, tenant_id, actor_type, actor_id, action,
                 reason, to_state, created_at)
                VALUES (:case, :account, :tenant, 'PRINCIPAL', :principal,
                        'CASE_SUBMITTED', :reason, 'SUBMITTED', :now)"""),
                {
                    "case": case_id,
                    "account": account_id,
                    "tenant": tenant_id,
                    "principal": principal_id,
                    "reason": detail,
                    "now": now,
                },
            )
            return dict(row)

    def list(self, principal_id: UUID, tenant_id: UUID) -> tuple[dict[str, object], ...]:
        with self.engine.connect() as connection:
            account_id = self._scope(connection, principal_id, tenant_id)
            rows = connection.execute(
                text("""SELECT case_id, case_type, state, reason,
                       disposition, resolved_at, created_at, updated_at
                FROM operation_cases WHERE account_id=:account AND tenant_id=:tenant
                ORDER BY created_at DESC"""),
                {"account": account_id, "tenant": tenant_id},
            ).mappings()
            return tuple(dict(row) for row in rows)

    def detail(self, principal_id: UUID, tenant_id: UUID, case_id: UUID) -> dict[str, object]:
        with self.engine.connect() as connection:
            account_id = self._scope(connection, principal_id, tenant_id)
            case = (
                connection.execute(
                    text("""SELECT case_id, case_type, state, reason,
                       disposition, resolved_at, created_at, updated_at
                FROM operation_cases WHERE case_id=:case AND account_id=:account
                  AND tenant_id=:tenant"""),
                    {"case": case_id, "account": account_id, "tenant": tenant_id},
                )
                .mappings()
                .one_or_none()
            )
            if case is None:
                raise SupportCaseError("CASE_UNAVAILABLE", "Resource unavailable.")
            events = tuple(
                dict(row)
                for row in connection.execute(
                    text("""
                SELECT action, actor_type, reason, from_state, to_state, created_at
                FROM operation_case_events WHERE case_id=:case AND account_id=:account
                ORDER BY created_at, case_event_id"""),
                    {"case": case_id, "account": account_id},
                ).mappings()
            )
            return {
                "case": dict(case),
                "events": events,
                "adjustments": tuple(
                    event for event in events if event["action"] == "ADJUSTMENT_GRANTED"
                ),
            }
