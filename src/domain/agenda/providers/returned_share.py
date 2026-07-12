from __future__ import annotations

from src.domain.agenda.constants import AgendaLifecycleType, AgendaSeverity
from src.domain.agenda.keys import build_agenda_key
from src.domain.agenda.models import AgendaContext, AgendaItem
from src.domain.agenda.source_models import AgendaSourceBundle, ReturnedShareAgendaSource
from src.models.share_models import SHARE_STATUS_RETURNED


def _version(source: ReturnedShareAgendaSource) -> str:
    base_hash = " ".join(source.base_snapshot_sha256.split())
    return f"RETURNED:{source.source_contract_revision}:{base_hash}"


class ReturnedShareAgendaProvider:
    code = "returned_share"

    def build(
        self,
        context: AgendaContext,
        sources: AgendaSourceBundle,
    ) -> tuple[AgendaItem, ...]:
        items: list[AgendaItem] = []
        for source in sources.returned_shares:
            if source.status != SHARE_STATUS_RETURNED:
                continue
            if not source.share_package_id or source.contract_id <= 0:
                continue
            title = (
                f"{source.contract_no} paylaşımı geri döndü"
                if source.contract_no
                else "Paylaşım geri döndü"
            )
            items.append(
                AgendaItem(
                    key=build_agenda_key(
                        provider_code=self.code,
                        entity_type="share_package",
                        entity_id=source.share_package_id,
                    ),
                    provider_code=self.code,
                    kind="returned_share",
                    lifecycle_type=AgendaLifecycleType.CONDITION,
                    title=title,
                    description="Birleştirme için bekliyor.",
                    priority=850,
                    severity=AgendaSeverity.ATTENTION,
                    version=_version(source),
                    presentation_scope=context.presentation_profile.code,
                    contract_id=source.contract_id,
                    platform=source.platform,
                    contract_no=source.contract_no,
                    contract_type=source.contract_type,
                    system_id=None,
                    delivery_id=None,
                    effective_date=source.last_imported_at or source.created_at,
                    remaining_days=None,
                    reason_code="SHARE_RETURNED",
                    reason_text=(
                        "Kaynak paylaşım paketi ana STS kayıt defterinde RETURNED durumunda."
                    ),
                    detail_payload={
                        "source_type": "share_package",
                        "registry_id": source.registry_id,
                        "share_package_id": source.share_package_id,
                        "contract_merge_uid": source.contract_merge_uid,
                        "status": source.status,
                        "source_contract_revision": source.source_contract_revision,
                        "permission_mode": source.permission_mode,
                        "share_format_version": source.share_format_version,
                        "snapshot_format_version": source.snapshot_format_version,
                        "base_snapshot_sha256": source.base_snapshot_sha256,
                        "created_at": source.created_at,
                        "created_by_staff_id": source.created_by_staff_id,
                        "created_by_full_name": source.created_by_full_name,
                        "exported_filename": source.exported_filename,
                        "last_imported_at": source.last_imported_at,
                        "last_imported_by_staff_id": source.last_imported_by_staff_id,
                        "last_remote_snapshot_sha256": source.last_remote_snapshot_sha256,
                        "return_count": source.return_count,
                    },
                    action_hints=("open_contract",),
                    supports_snooze=True,
                )
            )
        return tuple(items)
