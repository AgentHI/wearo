#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ROOT / "apps" / "api" / "migrations" / "versions"
CLASSIFICATIONS = {"public", "private", "financial", "audit", "system"}
OWNER_COLUMNS = {"account_id", "consumer_id", "tenant_id"}
AUDIT_COLUMNS = {"created_at", "updated_at"}


class MigrationPolicyError(ValueError):
    """Raised when a migration violates Wearo ownership or audit conventions."""


def require(condition: object, message: str) -> None:
    if not condition:
        raise MigrationPolicyError(message)


def literal_assignment(tree: ast.Module, name: str) -> object:
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            target = node.targets[0] if isinstance(node, ast.Assign) else node.target
            if isinstance(target, ast.Name) and target.id == name:
                if node.value is None:
                    break
                return ast.literal_eval(node.value)
    raise MigrationPolicyError(f"Missing {name}")


def created_tables(tree: ast.Module) -> dict[str, set[str]]:
    tables: dict[str, set[str]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "create_table" or not node.args:
            continue
        table_name = ast.literal_eval(node.args[0])
        columns: set[str] = set()
        for argument in node.args[1:]:
            if (
                isinstance(argument, ast.Call)
                and isinstance(argument.func, ast.Attribute)
                and argument.func.attr == "Column"
                and argument.args
            ):
                columns.add(ast.literal_eval(argument.args[0]))
        tables[table_name] = columns
    return tables


def validate_revision(path: Path) -> str:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    revision = literal_assignment(tree, "revision")
    policies = literal_assignment(tree, "TABLE_POLICIES")
    require(isinstance(revision, str) and revision, f"{path}: invalid revision")
    require(isinstance(policies, dict), f"{path}: TABLE_POLICIES must be a dict")
    if not isinstance(revision, str) or not isinstance(policies, dict):
        raise MigrationPolicyError(f"{path}: invalid statically typed migration metadata")
    tables = created_tables(tree)
    require(
        set(tables) == set(policies),
        f"{path}: TABLE_POLICIES must exactly match created tables; "
        f"tables={sorted(tables)} policies={sorted(policies)}",
    )
    for table, columns in tables.items():
        policy = policies[table]
        require(isinstance(policy, dict), f"{path}: invalid policy for {table}")
        if not isinstance(policy, dict):
            raise MigrationPolicyError(f"{path}: invalid statically typed policy for {table}")
        classification = policy.get("classification")
        require(classification in CLASSIFICATIONS, f"{path}: invalid classification for {table}")
        owner_value = policy.get("owner_columns", [])
        require(isinstance(owner_value, list), f"{path}: owner_columns must be a list for {table}")
        declared_owners = set(owner_value) if isinstance(owner_value, list) else set()
        require(declared_owners <= columns, f"{path}: undeclared owner column on {table}")
        if classification in {"private", "financial"}:
            require(
                bool(declared_owners & OWNER_COLUMNS),
                f"{path}: {table} requires an owner column",
            )
        if classification == "financial":
            require(
                "account_id" in declared_owners,
                f"{path}: {table} requires account_id ownership",
            )
        if classification not in {"public", "system"}:
            require(
                AUDIT_COLUMNS <= columns,
                f"{path}: {table} requires created_at and updated_at",
            )
    return revision


def main() -> None:
    revisions = [validate_revision(path) for path in sorted(VERSIONS.glob("*.py"))]
    require(revisions, "At least one migration revision is required")
    require(len(revisions) == len(set(revisions)), "Migration revision IDs must be unique")
    print(f"Migration policy validation: PASS ({len(revisions)} revision(s))")


if __name__ == "__main__":
    main()
