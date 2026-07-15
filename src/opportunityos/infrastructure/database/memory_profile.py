from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from sqlalchemy import select

from opportunityos.domain.enums import MemoryCategory, MemorySource, MemoryStatus
from opportunityos.domain.models import PersonalProfile
from opportunityos.domain.taxonomy import canonicalise_profile
from opportunityos.infrastructure.database.models import (
    MemoryItemRecord,
    PersonalProfileRecord,
    User,
)


class ProfileMemoryMixin:
    def save_profile(
        self,
        profile: PersonalProfile,
        *,
        email: str | None = None,
        actor: str = "system",
        reason: str | None = None,
    ) -> PersonalProfile:
        profile = canonicalise_profile(profile)
        profile = self._respect_user_controls(profile, actor)
        profile = canonicalise_profile(profile)
        self._persist_profile_payload(profile, email=email)
        # User/profile and memory records do not have ORM relationships that
        # communicate insert ordering to SQLAlchemy. Flush the parent rows
        # before inserting memory so PostgreSQL foreign keys are satisfied.
        self._session.flush()
        self._sync_memory(profile, actor=actor, reason=reason)
        self._session.flush()
        return profile

    def _persist_profile_payload(
        self,
        profile: PersonalProfile,
        *,
        email: str | None = None,
    ) -> None:
        user_id = str(profile.user_id)
        user = self._session.get(User, user_id)
        if user is None:
            user = User(id=user_id, email=email, display_name=profile.display_name)
            self._session.add(user)
            # Flush the root aggregate before adding rows that reference it.
            # Raw foreign keys alone do not establish ORM unit-of-work order.
            self._session.flush()
        else:
            user.display_name = profile.display_name
            if email is not None:
                user.email = email

        record = self._session.scalar(select(PersonalProfileRecord).where(PersonalProfileRecord.user_id == user_id))
        payload = profile.model_dump(mode="json")
        if record is None:
            self._session.add(
                PersonalProfileRecord(
                    user_id=user_id,
                    headline=profile.headline,
                    profile_json=payload,
                    version=1,
                )
            )
        else:
            record.headline = profile.headline
            record.profile_json = payload
            record.version += 1

    def _respect_user_controls(
        self,
        profile: PersonalProfile,
        actor: str,
    ) -> PersonalProfile:
        if actor == "profile_user":
            return profile
        protected = self._session.scalars(
            select(MemoryItemRecord).where(
                MemoryItemRecord.user_id == str(profile.user_id),
                (MemoryItemRecord.is_user_overridden.is_(True))
                | (MemoryItemRecord.status.in_(["rejected", "deleted"])),
            )
        ).all()
        if not protected:
            return profile

        updated = deepcopy(profile)
        for record in protected:
            category = MemoryCategory(record.category)
            if record.status in {MemoryStatus.REJECTED.value, MemoryStatus.DELETED.value}:
                self._remove_profile_item(updated, category, record.key)
                continue
            if not record.is_user_overridden:
                continue
            if actor == "user_feedback" and category == MemoryCategory.PREFERENCE:
                current = next(
                    (item for item in updated.preferences if item.key == record.key),
                    None,
                )
                if current is not None and current.explicit:
                    continue
            self._upsert_profile_item(updated, category, record.key, record.value_json)
        return updated

    def _sync_memory(
        self,
        profile: PersonalProfile,
        *,
        actor: str,
        reason: str | None,
    ) -> None:
        user_id = str(profile.user_id)
        desired = self._profile_memory_payloads(profile)
        existing = {
            (item.category, item.key): item
            for item in self._session.scalars(select(MemoryItemRecord).where(MemoryItemRecord.user_id == user_id)).all()
        }

        for identity, payload in desired.items():
            category, key = identity
            record = existing.get(identity)
            if record is None:
                record = MemoryItemRecord(
                    user_id=user_id,
                    category=category,
                    key=key,
                    value_json=payload["value"],
                    source=payload["source"],
                    confidence=payload["confidence"],
                    expires_at=None,
                    is_user_overridden=payload["is_user_overridden"],
                    status=(
                        MemoryStatus.CONFIRMED.value
                        if payload["source"] == MemorySource.EXPLICIT.value
                        else MemoryStatus.ACTIVE.value
                    ),
                    active=True,
                    confirmed_at=(
                        datetime.now(timezone.utc) if payload["source"] == MemorySource.EXPLICIT.value else None
                    ),
                    rejected_at=None,
                )
                self._session.add(record)
                self._session.flush()
                self._audit(record, "created", actor, None, self._snapshot(record), reason)
                continue

            before = self._snapshot(record)
            if record.status in {MemoryStatus.REJECTED.value, MemoryStatus.DELETED.value}:
                if actor != "profile_user":
                    continue
            if record.is_user_overridden and payload["source"] == MemorySource.INFERRED.value:
                continue
            record.value_json = payload["value"]
            record.source = payload["source"]
            record.confidence = payload["confidence"]
            record.is_user_overridden = record.is_user_overridden or payload["is_user_overridden"]
            record.active = True
            record.status = MemoryStatus.CONFIRMED.value if record.is_user_overridden else MemoryStatus.ACTIVE.value
            after = self._snapshot(record)
            if before != after:
                self._audit(record, "updated", actor, before, after, reason)

        for identity, record in existing.items():
            if identity in desired or not record.active:
                continue
            before = self._snapshot(record)
            record.active = False
            record.status = MemoryStatus.DELETED.value
            self._audit(
                record,
                "deactivated",
                actor,
                before,
                self._snapshot(record),
                reason,
            )

    def _profile_memory_payloads(
        self,
        profile: PersonalProfile,
    ) -> dict[tuple[str, str], dict]:
        payloads: dict[tuple[str, str], dict] = {}
        for item in profile.capabilities:
            payloads[(MemoryCategory.CAPABILITY.value, item.name)] = {
                "value": item.model_dump(mode="json"),
                "source": MemorySource.INFERRED.value,
                "confidence": item.proficiency,
                "is_user_overridden": False,
            }
        for item in profile.preferences:
            payloads[(MemoryCategory.PREFERENCE.value, item.key)] = {
                "value": item.model_dump(mode="json"),
                "source": (MemorySource.EXPLICIT.value if item.explicit else MemorySource.INFERRED.value),
                "confidence": item.confidence,
                "is_user_overridden": item.explicit,
            }
        for item in profile.constraints:
            payloads[(MemoryCategory.CONSTRAINT.value, item.key)] = {
                "value": item.model_dump(mode="json"),
                "source": MemorySource.EXPLICIT.value,
                "confidence": 1.0,
                "is_user_overridden": True,
            }
        for item in profile.aspirations:
            payloads[(MemoryCategory.ASPIRATION.value, item.name)] = {
                "value": item.model_dump(mode="json"),
                "source": MemorySource.EXPLICIT.value,
                "confidence": item.weight,
                "is_user_overridden": True,
            }
        for name in profile.target_problem_areas:
            payloads[(MemoryCategory.PROBLEM_AREA.value, name)] = {
                "value": {"name": name},
                "source": MemorySource.INFERRED.value,
                "confidence": 0.65,
                "is_user_overridden": False,
            }
        return payloads
