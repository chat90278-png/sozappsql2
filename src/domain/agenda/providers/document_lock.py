from __future__ import annotations

from src.domain.agenda.constants import AgendaLifecycleType, AgendaSeverity
from src.domain.agenda.keys import build_agenda_key
from src.domain.agenda.models import AgendaContext, AgendaItem
from src.domain.agenda.source_models import AgendaSourceBundle, DocumentLockAgendaSource


class DocumentLockAgendaProvider:
    code = "document_lock"

    def is_enabled(self, context: AgendaContext) -> bool:
        return (
            "unlock_own_documents" in context.permissions
            or "unlock_all_documents" in context.permissions
        )

    @staticmethod
    def _positive_staff_id(value: object) -> int | None:
        if value is None or isinstance(value, bool):
            return None
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _owner_relation(
        source: DocumentLockAgendaSource,
        staff_id: int | None,
    ) -> str:
        if source.locked_by_staff_id is None:
            return "UNKNOWN"
        if staff_id is not None and source.locked_by_staff_id == staff_id:
            return "OWN"
        return "OTHER"

    @staticmethod
    def _description(source: DocumentLockAgendaSource, owner_relation: str) -> str:
        if owner_relation == "OWN":
            return "Belgeler sizin tarafınızdan kilitlendi."
        if source.locked_by_full_name:
            return f"Belgeler {source.locked_by_full_name} tarafından kilitlendi."
        return "Belgeler başka bir personel tarafından kilitlendi."

    def build(
        self,
        context: AgendaContext,
        sources: AgendaSourceBundle,
    ) -> tuple[AgendaItem, ...]:
        can_unlock_own = "unlock_own_documents" in context.permissions
        can_unlock_all = "unlock_all_documents" in context.permissions
        staff_id = self._positive_staff_id(context.staff_id)
        items: list[AgendaItem] = []

        for source in sources.document_locks:
            if not source.is_locked or not source.locked_at:
                continue

            owner_relation = self._owner_relation(source, staff_id)
            if not can_unlock_all:
                if not can_unlock_own or owner_relation != "OWN":
                    continue

            contract_label = source.contract_no or "Sözleşme"
            owner_id = source.locked_by_staff_id or 0
            items.append(
                AgendaItem(
                    key=build_agenda_key(
                        provider_code=self.code,
                        entity_type="contract",
                        entity_id=source.contract_id,
                    ),
                    provider_code=self.code,
                    kind="document_lock",
                    lifecycle_type=AgendaLifecycleType.CONDITION,
                    title=f"{contract_label} belgeleri kilitli",
                    description=self._description(source, owner_relation),
                    priority=800,
                    severity=AgendaSeverity.ATTENTION,
                    version=f"LOCKED:{owner_id}:{source.locked_at}",
                    presentation_scope=context.presentation_profile.code,
                    contract_id=source.contract_id,
                    platform=source.platform,
                    contract_no=source.contract_no,
                    contract_type=source.contract_type,
                    actor_staff_id=source.locked_by_staff_id,
                    actor_name=source.locked_by_full_name,
                    event_at=source.locked_at,
                    effective_date=source.locked_at,
                    reason_code="DOCUMENT_LOCKED",
                    reason_text="OWN_LOCK" if owner_relation == "OWN" else "OTHER_LOCK",
                    detail_payload={
                        "source_type": "document_lock",
                        "contract_id": source.contract_id,
                        "is_locked": source.is_locked,
                        "locked_by_staff_id": source.locked_by_staff_id,
                        "locked_by_device_name": source.locked_by_device_name,
                        "locked_by_full_name": source.locked_by_full_name,
                        "locked_at": source.locked_at,
                        "updated_at": source.updated_at,
                        "owner_relation": owner_relation,
                        "can_unlock_own": can_unlock_own,
                        "can_unlock_all": can_unlock_all,
                    },
                    action_hints=("open_contract",),
                    supports_snooze=True,
                )
            )

        return tuple(items)
