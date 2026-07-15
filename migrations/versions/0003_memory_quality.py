"""Canonicalise personal memory and remove category contamination.

Revision ID: 0003_memory_quality
Revises: 0002_memory_guardrails
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "0003_memory_quality"
down_revision: str | None = "0002_memory_guardrails"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SPACE_RE = re.compile(r"\s+")

_PREFERENCE_ALIASES = {
    "recommendation:similar_profiles": "recommendation:similar_opportunities",
}

_PROBLEM_ALIASES = {
    "ai implementation": "AI implementation",
    "artificial intelligence implementation": "AI implementation",
    "ai operational systems": "AI operational systems that produce tangible outputs",
    "ai operational systems that can produce tangible outputs": "AI operational systems that produce tangible outputs",
    "ai operational systems that produce tangible outputs": "AI operational systems that produce tangible outputs",
    "analytics": "Product decision intelligence",
    "product analytics": "Product decision intelligence",
    "data unification": "Customer data unification",
    "customer data unification": "Customer data unification",
    "growth": "Growth optimisation",
    "growth optimization": "Growth optimisation",
    "growth optimisation": "Growth optimisation",
    "retention": "Retention improvement",
    "retention improvement": "Retention improvement",
    "experimentation": "Experimentation systems",
    "experimentation systems": "Experimentation systems",
    "forecasting": "Demand forecasting",
    "demand forecasting": "Demand forecasting",
    "delivery": "Cross-functional delivery",
    "cross functional delivery": "Cross-functional delivery",
    "cross-functional delivery": "Cross-functional delivery",
    "product strategy": "Product strategy",
    "business strategy": "Business strategy",
}

_CAPABILITY_ONLY = {
    "artificial intelligence",
    "data science",
    "growth analytics",
    "product management",
    "project management",
    "python",
    "retention analytics",
    "sql",
}

_ACRONYMS = {
    "ai": "AI",
    "b2b": "B2B",
    "b2c": "B2C",
    "cdp": "CDP",
    "llm": "LLM",
    "ml": "ML",
    "sql": "SQL",
}


def _clean(value: str) -> str:
    return _SPACE_RE.sub(" ", value.strip())


def _identity(value: str) -> str:
    return _clean(value).casefold()


def _preference_key(value: str) -> str:
    cleaned = _clean(value).casefold()
    if ":" in cleaned:
        namespace, item = cleaned.split(":", 1)
        cleaned = f"{namespace.strip().replace(' ', '_')}:{item.strip().replace(' ', '_')}"
    else:
        cleaned = cleaned.replace(" ", "_")
    return _PREFERENCE_ALIASES.get(cleaned, cleaned)


def _sentence_case(identity: str) -> str:
    words = identity.split()
    rendered = [_ACRONYMS.get(word, word) for word in words]
    for index, word in enumerate(rendered):
        if word not in _ACRONYMS.values():
            rendered[index] = word[:1].upper() + word[1:]
            break
    return " ".join(rendered)


def _problem_area(value: str) -> str | None:
    identity = _identity(value)
    if not identity or identity in _CAPABILITY_ONLY:
        return None
    return _PROBLEM_ALIASES.get(identity, _sentence_case(identity))


def _json_value(value: object) -> dict:
    if isinstance(value, str):
        return json.loads(value)
    return deepcopy(value) if isinstance(value, dict) else {}


def _canonical_profile(payload: dict) -> dict:
    updated = deepcopy(payload)

    preferences: list[dict] = []
    by_key: dict[str, dict] = {}
    for raw in updated.get("preferences", []):
        item = deepcopy(raw)
        item["key"] = _preference_key(str(item.get("key", "")))
        existing = by_key.get(item["key"])
        if existing is None:
            by_key[item["key"]] = item
            preferences.append(item)
            continue
        candidate_rank = (
            bool(item.get("explicit")),
            float(item.get("confidence", 0.0)),
            str(item.get("last_updated_at", "")),
        )
        existing_rank = (
            bool(existing.get("explicit")),
            float(existing.get("confidence", 0.0)),
            str(existing.get("last_updated_at", "")),
        )
        if candidate_rank > existing_rank:
            preferences[preferences.index(existing)] = item
            by_key[item["key"]] = item
    updated["preferences"] = preferences

    problem_areas: list[str] = []
    seen: set[str] = set()
    for raw in updated.get("target_problem_areas", []):
        canonical = _problem_area(str(raw))
        if canonical is None:
            continue
        identity = _identity(canonical)
        if identity in seen:
            continue
        seen.add(identity)
        problem_areas.append(canonical)
    updated["target_problem_areas"] = problem_areas
    return updated


def _snapshot(row: dict) -> dict:
    return {
        "category": row["category"],
        "key": row["key"],
        "value": _json_value(row["value_json"]),
        "source": row["source"],
        "confidence": row["confidence"],
        "status": row["status"],
        "active": row["active"],
        "is_user_overridden": row["is_user_overridden"],
    }


def _audit(bind: sa.Connection, audit: sa.Table, row: dict, action: str, before: dict, after: dict) -> None:
    now = datetime.now(timezone.utc)
    bind.execute(
        audit.insert().values(
            id=str(uuid4()),
            created_at=now,
            updated_at=now,
            user_id=row["user_id"],
            memory_item_id=row["id"],
            action=action,
            actor="migration",
            before_json=before,
            after_json=after,
            reason="Canonicalised by memory-quality migration",
        )
    )


def _rank(row: dict) -> tuple[bool, bool, bool, float, str]:
    return (
        bool(row["is_user_overridden"]),
        row["source"] == "explicit",
        row["status"] == "confirmed",
        float(row["confidence"]),
        str(row["updated_at"]),
    )


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    profiles = sa.Table("personal_profiles", metadata, autoload_with=bind)
    memory = sa.Table("memory_items", metadata, autoload_with=bind)
    audit = sa.Table("memory_audit_events", metadata, autoload_with=bind)

    now = datetime.now(timezone.utc)
    for row in bind.execute(sa.select(profiles)).mappings():
        payload = _json_value(row["profile_json"])
        canonical = _canonical_profile(payload)
        if canonical == payload:
            continue
        bind.execute(
            profiles.update()
            .where(profiles.c.id == row["id"])
            .values(
                profile_json=canonical,
                version=int(row["version"]) + 1,
                updated_at=now,
            )
        )

    rows = [dict(row) for row in bind.execute(sa.select(memory)).mappings()]
    groups: dict[tuple[str, str, str], list[dict]] = {}
    dropped: list[dict] = []

    for row in rows:
        category = row["category"]
        if category == "preference":
            canonical = _preference_key(row["key"])
        elif category == "problem_area":
            canonical = _problem_area(row["key"])
            if canonical is None:
                dropped.append(row)
                continue
        else:
            continue
        groups.setdefault((row["user_id"], category, canonical), []).append(row)

    for row in dropped:
        if not row["active"] and row["status"] == "deleted":
            continue
        before = _snapshot(row)
        after = {**before, "active": False, "status": "deleted"}
        bind.execute(
            memory.update()
            .where(memory.c.id == row["id"])
            .values(active=False, status="deleted", updated_at=now)
        )
        _audit(bind, audit, row, "removed_category_contamination", before, after)

    for (_, category, canonical), grouped_rows in groups.items():
        exact = [row for row in grouped_rows if row["key"] == canonical]
        primary = max(exact, key=_rank) if exact else max(grouped_rows, key=_rank)
        strongest = max(grouped_rows, key=_rank)
        before_primary = _snapshot(primary)

        merged_value = _json_value(strongest["value_json"])
        if category == "preference":
            merged_value["key"] = canonical
        else:
            merged_value = {"name": canonical}

        explicit = any(row["source"] == "explicit" or row["is_user_overridden"] for row in grouped_rows)
        active = any(row["active"] for row in grouped_rows)
        confidence = max(float(row["confidence"]) for row in grouped_rows)
        primary_after = {
            "category": category,
            "key": canonical,
            "value": merged_value,
            "source": "explicit" if explicit else strongest["source"],
            "confidence": confidence,
            "status": "confirmed" if explicit else ("active" if active else strongest["status"]),
            "active": active,
            "is_user_overridden": explicit,
        }

        for row in grouped_rows:
            if row["id"] == primary["id"]:
                continue
            before = _snapshot(row)
            after = {**before, "active": False, "status": "deleted"}
            bind.execute(
                memory.update()
                .where(memory.c.id == row["id"])
                .values(active=False, status="deleted", updated_at=now)
            )
            _audit(bind, audit, row, "merged_duplicate", before, after)

        bind.execute(
            memory.update()
            .where(memory.c.id == primary["id"])
            .values(
                key=canonical,
                value_json=merged_value,
                source=primary_after["source"],
                confidence=confidence,
                status=primary_after["status"],
                active=active,
                is_user_overridden=explicit,
                updated_at=now,
            )
        )
        if before_primary != primary_after:
            _audit(bind, audit, primary, "canonicalised", before_primary, primary_after)


def downgrade() -> None:
    # This data cleanup is intentionally irreversible. Audit events preserve
    # the prior values for inspection, while schema downgrade remains safe.
    pass
