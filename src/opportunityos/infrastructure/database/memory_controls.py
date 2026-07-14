from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from opportunityos.domain.enums import MemoryAction, MemoryCategory, MemorySource, MemoryStatus
from opportunityos.domain.models import (
    Aspiration,
    Capability,
    Constraint,
    FeedbackEvent,
    MemoryAuditEvent,
    MemoryItem,
    MemoryMutationRequest,
    PersonalProfile,
    WeightedPreference,
)
from opportunityos.infrastructure.database.memory_errors import (
    MemoryConflictError,
    MemoryNotFoundError,
)
from opportunityos.infrastructure.database.models import (
    AnalysisRunRecord,
    BehaviourEventRecord,
    MemoryAuditRecord,
    MemoryItemRecord,
)
from opportunityos.infrastructure.database.store import AnalysisNotFoundError


class MemoryControlMixin:
    def list_memory(
        self,
        user_id: UUID,
        *,
        include_inactive: bool = False,
    ) -> list[MemoryItem]:
        query = select(MemoryItemRecord).where(MemoryItemRecord.user_id == str(user_id))
        if not include_inactive:
            query = query.where(MemoryItemRecord.active.is_(True))
        query = query.order_by(MemoryItemRecord.category, MemoryItemRecord.key)
        return [self._to_memory_item(item) for item in self._session.scalars(query).all()]

    def mutate_memory(
        self,
        user_id: UUID,
        memory_id: UUID,
        request: MemoryMutationRequest,
    ) -> MemoryItem:
        record = self._get_memory_record(user_id, memory_id)
        profile = self.get_profile(user_id)
        before = self._snapshot(record)
        original_category = MemoryCategory(record.category)
        original_key = record.key
        if (
            request.action == MemoryAction.REJECT
            and original_category == MemoryCategory.CAPABILITY
            and len(profile.capabilities) <= 1
        ):
            raise MemoryConflictError("A profile must retain at least one capability")

        if request.action == MemoryAction.CONFIRM:
            self._confirm(record)
        elif request.action == MemoryAction.REJECT:
            record.status = MemoryStatus.REJECTED.value
            record.active = False
            record.rejected_at = datetime.now(timezone.utc)
        else:
            self._apply_update(record, request)

        self._remove_profile_item(profile, original_category, original_key)
        if record.active:
            self._upsert_profile_item(
                profile,
                MemoryCategory(record.category),
                record.key,
                record.value_json,
            )
        self._persist_profile_payload(profile)
        self._audit(
            record,
            request.action.value,
            "user",
            before,
            self._snapshot(record),
            request.reason,
        )
        self._session.flush()
        return self._to_memory_item(record)

    def delete_memory(
        self,
        user_id: UUID,
        memory_id: UUID,
        *,
        reason: str | None = None,
    ) -> None:
        record = self._get_memory_record(user_id, memory_id)
        profile = self.get_profile(user_id)
        if record.category == MemoryCategory.CAPABILITY.value and len(profile.capabilities) <= 1:
            raise MemoryConflictError("A profile must retain at least one capability")
        before = self._snapshot(record)
        record.status = MemoryStatus.DELETED.value
        record.active = False
        record.rejected_at = datetime.now(timezone.utc)
        self._remove_profile_item(profile, MemoryCategory(record.category), record.key)
        self._persist_profile_payload(profile)
        self._audit(record, "deleted", "user", before, self._snapshot(record), reason)
        self._session.flush()

    def list_memory_audit(
        self,
        user_id: UUID,
        *,
        limit: int = 100,
    ) -> list[MemoryAuditEvent]:
        records = self._session.scalars(
            select(MemoryAuditRecord)
            .where(MemoryAuditRecord.user_id == str(user_id))
            .order_by(MemoryAuditRecord.created_at.desc())
            .limit(limit)
        ).all()
        return [
            MemoryAuditEvent(
                id=UUID(item.id),
                user_id=UUID(item.user_id),
                memory_item_id=(UUID(item.memory_item_id) if item.memory_item_id else None),
                action=item.action,
                actor=item.actor,
                before=item.before_json,
                after=item.after_json,
                reason=item.reason,
                created_at=item.created_at,
            )
            for item in records
        ]

    def record_feedback(
        self,
        profile: PersonalProfile,
        feedback: FeedbackEvent,
        applied_updates: list[str],
    ) -> None:
        analysis = self._session.scalar(
            select(AnalysisRunRecord).where(
                AnalysisRunRecord.id == str(feedback.analysis_id),
                AnalysisRunRecord.user_id == str(profile.user_id),
            )
        )
        if analysis is None:
            raise AnalysisNotFoundError(str(feedback.analysis_id))
        self._session.add(
            BehaviourEventRecord(
                id=str(feedback.event_id),
                user_id=str(profile.user_id),
                analysis_run_id=str(feedback.analysis_id),
                event_type=feedback.action.value,
                event_json={
                    **feedback.model_dump(mode="json"),
                    "applied_updates": applied_updates,
                },
                explicit=feedback.explicit,
            )
        )
        actor = "user_feedback" if feedback.explicit else "learning"
        self.save_profile(
            profile,
            actor=actor,
            reason=f"feedback:{feedback.action.value}",
        )

    def _confirm(self, record: MemoryItemRecord) -> None:
        record.source = MemorySource.EXPLICIT.value
        record.confidence = 1.0
        record.is_user_overridden = True
        record.status = MemoryStatus.CONFIRMED.value
        record.active = True
        record.confirmed_at = datetime.now(timezone.utc)
        record.rejected_at = None
        if record.category == MemoryCategory.PREFERENCE.value:
            value = dict(record.value_json)
            value["explicit"] = True
            value["confidence"] = 1.0
            record.value_json = value

    def _apply_update(
        self,
        record: MemoryItemRecord,
        request: MemoryMutationRequest,
    ) -> None:
        if request.value is None:
            raise MemoryConflictError("Update action requires a value")
        category = MemoryCategory(record.category)
        key, value, confidence = self._validate_memory_value(
            category,
            request.key,
            request.value,
        )
        if key != record.key:
            conflict = self._session.scalar(
                select(MemoryItemRecord).where(
                    MemoryItemRecord.user_id == record.user_id,
                    MemoryItemRecord.category == record.category,
                    MemoryItemRecord.key == key,
                    MemoryItemRecord.id != record.id,
                )
            )
            if conflict is not None:
                raise MemoryConflictError("A memory item with that category and key already exists")
        record.key = key
        record.value_json = value
        record.confidence = confidence
        record.source = MemorySource.EXPLICIT.value
        record.is_user_overridden = True
        record.status = MemoryStatus.CONFIRMED.value
        record.active = True
        record.confirmed_at = datetime.now(timezone.utc)
        record.rejected_at = None

    def _validate_memory_value(
        self,
        category: MemoryCategory,
        requested_key: str | None,
        value: dict[str, object],
    ) -> tuple[str, dict, float]:
        if category == MemoryCategory.CAPABILITY:
            model = Capability.model_validate(value)
            key = requested_key or model.name
            model.name = key
            return key, model.model_dump(mode="json"), model.proficiency
        if category == MemoryCategory.PREFERENCE:
            model = WeightedPreference.model_validate(value)
            key = requested_key or model.key
            model.key = key
            model.explicit = True
            model.confidence = 1.0
            return key, model.model_dump(mode="json"), 1.0
        if category == MemoryCategory.CONSTRAINT:
            model = Constraint.model_validate(value)
            key = requested_key or model.key
            model.key = key
            return key, model.model_dump(mode="json"), 1.0
        if category == MemoryCategory.ASPIRATION:
            model = Aspiration.model_validate(value)
            key = requested_key or model.name
            model.name = key
            return key, model.model_dump(mode="json"), model.weight
        name = requested_key or str(value.get("name", "")).strip()
        if len(name) < 2:
            raise MemoryConflictError("Problem area requires a name")
        return name, {"name": name}, 1.0

    def _get_memory_record(
        self,
        user_id: UUID,
        memory_id: UUID,
    ) -> MemoryItemRecord:
        record = self._session.scalar(
            select(MemoryItemRecord).where(
                MemoryItemRecord.id == str(memory_id),
                MemoryItemRecord.user_id == str(user_id),
            )
        )
        if record is None:
            raise MemoryNotFoundError(str(memory_id))
        return record

    def _upsert_profile_item(
        self,
        profile: PersonalProfile,
        category: MemoryCategory,
        key: str,
        value: dict,
    ) -> None:
        self._remove_profile_item(profile, category, key)
        if category == MemoryCategory.CAPABILITY:
            profile.capabilities.append(Capability.model_validate(value))
        elif category == MemoryCategory.PREFERENCE:
            profile.preferences.append(WeightedPreference.model_validate(value))
        elif category == MemoryCategory.CONSTRAINT:
            profile.constraints.append(Constraint.model_validate(value))
        elif category == MemoryCategory.ASPIRATION:
            profile.aspirations.append(Aspiration.model_validate(value))
        else:
            profile.target_problem_areas.append(str(value["name"]))

    def _remove_profile_item(
        self,
        profile: PersonalProfile,
        category: MemoryCategory,
        key: str,
    ) -> None:
        if category == MemoryCategory.CAPABILITY:
            profile.capabilities = [item for item in profile.capabilities if item.name != key]
        elif category == MemoryCategory.PREFERENCE:
            profile.preferences = [item for item in profile.preferences if item.key != key]
        elif category == MemoryCategory.CONSTRAINT:
            profile.constraints = [item for item in profile.constraints if item.key != key]
        elif category == MemoryCategory.ASPIRATION:
            profile.aspirations = [item for item in profile.aspirations if item.name != key]
        else:
            profile.target_problem_areas = [item for item in profile.target_problem_areas if item != key]

    def _to_memory_item(self, record: MemoryItemRecord) -> MemoryItem:
        return MemoryItem(
            id=UUID(record.id),
            user_id=UUID(record.user_id),
            category=MemoryCategory(record.category),
            key=record.key,
            value=record.value_json,
            source=MemorySource(record.source),
            confidence=record.confidence,
            status=MemoryStatus(record.status),
            active=record.active,
            is_user_overridden=record.is_user_overridden,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    def _snapshot(self, record: MemoryItemRecord) -> dict[str, object]:
        return {
            "category": record.category,
            "key": record.key,
            "value": record.value_json,
            "source": record.source,
            "confidence": record.confidence,
            "status": record.status,
            "active": record.active,
            "is_user_overridden": record.is_user_overridden,
        }

    def _audit(
        self,
        record: MemoryItemRecord,
        action: str,
        actor: str,
        before: dict[str, object] | None,
        after: dict[str, object] | None,
        reason: str | None,
    ) -> None:
        self._session.add(
            MemoryAuditRecord(
                user_id=record.user_id,
                memory_item_id=record.id,
                action=action,
                actor=actor,
                before_json=before,
                after_json=after,
                reason=reason,
            )
        )
